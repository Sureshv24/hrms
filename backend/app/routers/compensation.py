from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.compensation import (
    CompensationStructure,
    CompensationComponent,
)
from app.models.employee import Employee
from app.models.audit_log import AuditLog
from app.routers.auth import get_current_user
from app.schemas.compensation import (
    CompensationStructureCreate,
    CompensationStructureResponse,
    CompensationStructureDetailResponse,
)
from app.utils.audit import record_audit_log


router = APIRouter(
    prefix="/compensation",
    tags=["Compensation Management"],
)

admin_hr = Depends(require_roles("Admin", "HR"))


class CompensationCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_to: date
    reason: str = Field(min_length=3, max_length=500)


def structure_detail(db: Session, structure: CompensationStructure) -> dict:
    components = (
        db.query(CompensationComponent)
        .filter(CompensationComponent.structure_id == structure.id)
        .order_by(CompensationComponent.id.asc())
        .all()
    )

    return {
        "id": structure.id,
        "employee_id": structure.employee_id,
        "structure_name": structure.structure_name,
        "effective_from": structure.effective_from,
        "effective_to": structure.effective_to,
        "basic_salary": structure.basic_salary,
        "currency": structure.currency,
        "notes": structure.notes,
        "created_by": structure.created_by,
        "created_at": structure.created_at,
        "updated_at": structure.updated_at,
        "components": components,
    }


def find_structure_or_404(
    db: Session,
    structure_id: int,
) -> CompensationStructure:
    structure = (
        db.query(CompensationStructure)
        .filter(CompensationStructure.id == structure_id)
        .first()
    )

    if structure is None:
        raise HTTPException(
            status_code=404,
            detail="Compensation structure not found",
        )

    return structure


def check_date_overlap(
    db: Session,
    employee_id: int,
    effective_from: date,
    effective_to: date | None,
    exclude_id: int | None = None,
) -> bool:
    query = db.query(CompensationStructure).filter(
        CompensationStructure.employee_id == employee_id,
        CompensationStructure.effective_from <= (
            effective_to or date.max
        ),
        or_(
            CompensationStructure.effective_to.is_(None),
            CompensationStructure.effective_to >= effective_from,
        ),
    )

    if exclude_id is not None:
        query = query.filter(
            CompensationStructure.id != exclude_id
        )

    return query.first() is not None


@router.post(
    "/structures",
    response_model=CompensationStructureDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_compensation_structure(
    payload: CompensationStructureCreate,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    employee = (
        db.query(Employee)
        .filter(
            Employee.id == payload.employee_id,
            Employee.is_active.is_(True),
        )
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Active employee not found",
        )

    if check_date_overlap(
        db,
        payload.employee_id,
        payload.effective_from,
        payload.effective_to,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Compensation dates overlap an existing structure. "
                "Close the old structure before creating a new version."
            ),
        )

    structure = CompensationStructure(
        employee_id=payload.employee_id,
        structure_name=payload.structure_name,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        basic_salary=payload.basic_salary,
        currency=payload.currency,
        notes=payload.notes,
        created_by=current_user.id,
    )

    try:
        db.add(structure)
        db.flush()

        for item in payload.components:
            db.add(
                CompensationComponent(
                    structure_id=structure.id,
                    component_name=item.component_name,
                    component_type=item.component_type,
                    calculation_method=item.calculation_method,
                    amount=item.amount,
                    is_taxable=item.is_taxable,
                    is_recurring=item.is_recurring,
                )
            )

        record_audit_log(
            db=db,
            actor=current_user,
            action="compensation.structure.created",
            entity_type="compensation_structure",
            entity_id=structure.id,
            details={
                "employee_id": structure.employee_id,
                "structure_name": structure.structure_name,
                "effective_from": structure.effective_from.isoformat(),
                "effective_to": (
                    structure.effective_to.isoformat()
                    if structure.effective_to else None
                ),
                "basic_salary": str(structure.basic_salary),
                "component_count": len(payload.components),
            },
        )

        db.commit()
        db.refresh(structure)
        return structure_detail(db, structure)

    except Exception:
        db.rollback()
        raise


@router.get(
    "/structures",
    response_model=list[CompensationStructureDetailResponse],
)
def list_compensation_structures(
    employee_id: int | None = Query(default=None, gt=0),
    effective_on: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    query = db.query(CompensationStructure)

    if employee_id is not None:
        query = query.filter(
            CompensationStructure.employee_id == employee_id
        )

    if effective_on is not None:
        query = query.filter(
            CompensationStructure.effective_from <= effective_on,
            or_(
                CompensationStructure.effective_to.is_(None),
                CompensationStructure.effective_to >= effective_on,
            ),
        )

    structures = (
        query.order_by(
            CompensationStructure.employee_id.asc(),
            CompensationStructure.effective_from.desc(),
            CompensationStructure.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return [
        structure_detail(db, structure)
        for structure in structures
    ]


@router.get(
    "/structures/{structure_id}",
    response_model=CompensationStructureDetailResponse,
)
def get_compensation_structure(
    structure_id: int,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    structure = find_structure_or_404(db, structure_id)
    return structure_detail(db, structure)


@router.get(
    "/employees/{employee_id}/current",
    response_model=CompensationStructureDetailResponse,
)
def get_current_compensation(
    employee_id: int,
    on_date: date | None = None,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    target_date = on_date or date.today()

    structure = (
        db.query(CompensationStructure)
        .filter(
            CompensationStructure.employee_id == employee_id,
            CompensationStructure.effective_from <= target_date,
            or_(
                CompensationStructure.effective_to.is_(None),
                CompensationStructure.effective_to >= target_date,
            ),
        )
        .order_by(
            CompensationStructure.effective_from.desc(),
            CompensationStructure.id.desc(),
        )
        .first()
    )

    if structure is None:
        raise HTTPException(
            status_code=404,
            detail="No compensation structure is effective on this date",
        )

    return structure_detail(db, structure)


@router.patch("/structures/{structure_id}/close")
def close_compensation_structure(
    structure_id: int,
    payload: CompensationCloseRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    structure = find_structure_or_404(db, structure_id)

    if payload.effective_to < structure.effective_from:
        raise HTTPException(
            status_code=422,
            detail="Effective end date cannot precede the start date",
        )

    if structure.effective_to is not None:
        raise HTTPException(
            status_code=409,
            detail="This structure already has an end date",
        )

    next_structure = (
        db.query(CompensationStructure)
        .filter(
            CompensationStructure.employee_id == structure.employee_id,
            CompensationStructure.id != structure.id,
            CompensationStructure.effective_from
            > structure.effective_from,
        )
        .order_by(CompensationStructure.effective_from.asc())
        .first()
    )

    if (
        next_structure is not None
        and payload.effective_to >= next_structure.effective_from
    ):
        raise HTTPException(
            status_code=409,
            detail="End date overlaps a later compensation version",
        )

    old_end = structure.effective_to
    structure.effective_to = payload.effective_to

    record_audit_log(
        db=db,
        actor=current_user,
        action="compensation.structure.closed",
        entity_type="compensation_structure",
        entity_id=structure.id,
        details={
            "employee_id": structure.employee_id,
            "previous_effective_to": (
                old_end.isoformat() if old_end else None
            ),
            "effective_to": payload.effective_to.isoformat(),
            "reason": payload.reason.strip(),
        },
    )

    try:
        db.commit()
        db.refresh(structure)
        return {
            "message": "Compensation structure closed successfully",
            "structure_id": structure.id,
            "effective_to": structure.effective_to,
        }
    except Exception:
        db.rollback()
        raise


@router.get("/structures/{structure_id}/history")
def get_compensation_audit_history(
    structure_id: int,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    find_structure_or_404(db, structure_id)

    entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "compensation_structure",
            AuditLog.entity_id == str(structure_id),
        )
        .order_by(AuditLog.created_at.desc())
        .all()
    )

    return [
        {
            "id": entry.id,
            "actor_user_id": entry.actor_user_id,
            "actor_name": entry.actor_name,
            "actor_role": entry.actor_role,
            "action": entry.action,
            "details": entry.details,
            "created_at": entry.created_at,
        }
        for entry in entries
    ]

# ==========================================
# READ-ONLY COMPENSATION PREVIEW
# ==========================================

from decimal import Decimal, ROUND_HALF_UP


class CompensationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overtime_hours: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=8,
        decimal_places=2,
    )
    include_non_recurring: bool = False


def _preview_money(value: Decimal) -> Decimal:
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


@router.post("/structures/{structure_id}/preview")
def preview_compensation(
    structure_id: int,
    payload: CompensationPreviewRequest,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    """
    Calculate an estimated compensation breakdown.
    This endpoint does not create or update payroll records.
    """
    structure = find_structure_or_404(db, structure_id)

    basic_salary = _preview_money(
        Decimal(str(structure.basic_salary))
    )

    components = (
        db.query(CompensationComponent)
        .filter(
            CompensationComponent.structure_id == structure.id
        )
        .order_by(CompensationComponent.id.asc())
        .all()
    )

    earnings = Decimal("0.00")
    deductions = Decimal("0.00")
    component_breakdown = []

    for component in components:
        configured_amount = Decimal(str(component.amount))
        included = (
            bool(component.is_recurring)
            or payload.include_non_recurring
        )

        if not included:
            calculated_amount = Decimal("0.00")
            formula = (
                "Excluded because this is non-recurring; "
                "set include_non_recurring to true to include it"
            )
        elif component.calculation_method == "Fixed":
            calculated_amount = configured_amount
            formula = "Fixed configured amount"
        elif component.calculation_method == "PercentOfBasic":
            calculated_amount = (
                basic_salary * configured_amount / Decimal("100")
            )
            formula = (
                f"{configured_amount}% of basic salary "
                f"({basic_salary})"
            )
        elif component.calculation_method == "PerOvertimeHour":
            calculated_amount = (
                configured_amount * payload.overtime_hours
            )
            formula = (
                f"{configured_amount} per overtime hour "
                f"x {payload.overtime_hours} hours"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Unsupported calculation method for "
                    f"component {component.id}"
                ),
            )

        calculated_amount = _preview_money(calculated_amount)

        if included and component.component_type == "Earning":
            earnings += calculated_amount
        elif included and component.component_type == "Deduction":
            deductions += calculated_amount

        component_breakdown.append(
            {
                "component_id": component.id,
                "component_name": component.component_name,
                "component_type": component.component_type,
                "calculation_method": component.calculation_method,
                "configured_amount": configured_amount,
                "calculated_amount": calculated_amount,
                "is_taxable": component.is_taxable,
                "is_recurring": component.is_recurring,
                "included_in_preview": included,
                "formula": formula,
            }
        )

    gross_earnings = _preview_money(basic_salary + earnings)
    deductions = _preview_money(deductions)
    estimated_net = _preview_money(gross_earnings - deductions)

    return {
        "preview_only": True,
        "payroll_record_created": False,
        "structure_id": structure.id,
        "employee_id": structure.employee_id,
        "structure_name": structure.structure_name,
        "effective_from": structure.effective_from,
        "effective_to": structure.effective_to,
        "currency": structure.currency,
        "basic_salary": basic_salary,
        "additional_earnings": _preview_money(earnings),
        "gross_earnings": gross_earnings,
        "total_deductions": deductions,
        "estimated_net_salary": estimated_net,
        "overtime_hours": payload.overtime_hours,
        "include_non_recurring": payload.include_non_recurring,
        "components": component_breakdown,
        "note": (
            "Preview only. Attendance, leave without pay, "
            "mid-month proration and payroll adjustments are "
            "not included. No payroll records were changed."
        ),
    }
