import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.holiday import Holiday, EmployeeHolidaySelection
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.holiday import (
    HolidayCreate,
    HolidayUpdate,
    HolidayResponse,
    HolidayCalendarItem,
    EmployeeHolidaySelectionResponse,
)


router = APIRouter(
    prefix="/holidays",
    tags=["Holiday & Calendar"],
)


def get_holiday_or_404(
    db: Session,
    holiday_id: int,
    active_only: bool = False,
) -> Holiday:
    query = db.query(Holiday).filter(Holiday.id == holiday_id)

    if active_only:
        query = query.filter(Holiday.is_active.is_(True))

    holiday = query.first()

    if not holiday:
        raise HTTPException(
            status_code=404,
            detail="Holiday not found",
        )

    return holiday


def add_holiday_audit(
    db: Session,
    actor: User,
    action: str,
    holiday: Holiday,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id,
            actor_name=actor.full_name,
            actor_role=actor.role,
            action=action,
            entity_type="holiday",
            entity_id=str(holiday.id),
            details=details or {},
        )
    )


def validate_holiday_data(
    name: str,
    holiday_type: str,
    region: str | None,
) -> None:
    if not name or len(name.strip()) < 2:
        raise HTTPException(
            status_code=422,
            detail="Holiday name must contain at least 2 characters",
        )

    if holiday_type == "Regional" and not (region and region.strip()):
        raise HTTPException(
            status_code=422,
            detail="Region is required for regional holidays",
        )


# ADMIN/HR: LIST HOLIDAYS
@router.get(
    "/",
    response_model=list[HolidayResponse],
)
def list_holidays(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    query = db.query(Holiday)

    if not include_inactive:
        query = query.filter(Holiday.is_active.is_(True))

    return query.order_by(Holiday.holiday_date.asc()).all()


# EMPLOYEE/ADMIN/HR: MONTHLY OR YEARLY CALENDAR
# Keep this route before /{holiday_id}.
@router.get(
    "/calendar",
    response_model=list[HolidayCalendarItem],
)
def holiday_calendar(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    region: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if month is not None:
        start_date = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day)
    else:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

    query = db.query(Holiday).filter(
        Holiday.is_active.is_(True),
        Holiday.holiday_date >= start_date,
        Holiday.holiday_date <= end_date,
    )

    # When a region is supplied, include company-wide holidays and
    # regional holidays matching that region.
    if region and region.strip():
        query = query.filter(
            or_(
                Holiday.region.is_(None),
                Holiday.region.ilike(region.strip()),
            )
        )

    holidays = query.order_by(Holiday.holiday_date.asc()).all()

    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.id)
        .first()
    )

    selected_ids: set[int] = set()

    if employee:
        selected_ids = {
            row.holiday_id
            for row in (
                db.query(EmployeeHolidaySelection.holiday_id)
                .filter(
                    EmployeeHolidaySelection.employee_id == employee.id
                )
                .all()
            )
        }

    return [
        HolidayCalendarItem(
            **{
                column.name: getattr(holiday, column.name)
                for column in Holiday.__table__.columns
            },
            is_selected=holiday.id in selected_ids,
        )
        for holiday in holidays
    ]


# ADMIN/HR: CREATE HOLIDAY
@router.post(
    "/",
    response_model=HolidayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_holiday(
    data: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    name = data.name.strip()
    region = data.region.strip() if data.region else None

    validate_holiday_data(name, data.holiday_type, region)

    if data.holiday_type != "Regional":
        region = None

    holiday = Holiday(
        name=name,
        holiday_date=data.holiday_date,
        holiday_type=data.holiday_type,
        region=region,
        description=data.description.strip() if data.description else None,
        is_active=data.is_active,
        created_by=current_user.id,
    )

    db.add(holiday)

    try:
        db.flush()
        add_holiday_audit(
            db,
            current_user,
            "holiday.created",
            holiday,
            {
                "name": holiday.name,
                "holiday_date": holiday.holiday_date.isoformat(),
                "holiday_type": holiday.holiday_type,
            },
        )
        db.commit()
        db.refresh(holiday)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create holiday",
        )

    return holiday


# ADMIN/HR: UPDATE HOLIDAY
@router.patch(
    "/{holiday_id}",
    response_model=HolidayResponse,
)
def update_holiday(
    holiday_id: int,
    data: HolidayUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    holiday = get_holiday_or_404(db, holiday_id)
    updates = data.model_dump(exclude_unset=True)

    # Reject explicit null values for required fields.
    for required_field in ("name", "holiday_date", "holiday_type", "is_active"):
        if required_field in updates and updates[required_field] is None:
            raise HTTPException(
                status_code=422,
                detail=f"{required_field} cannot be null",
            )

    new_name = updates.get("name", holiday.name)
    new_type = updates.get("holiday_type", holiday.holiday_type)
    new_region = updates.get("region", holiday.region)

    if new_name is not None:
        new_name = new_name.strip()

    if new_region:
        new_region = new_region.strip()

    validate_holiday_data(new_name, new_type, new_region)

    if new_type != "Regional":
        new_region = None

    for field, value in updates.items():
        if field == "name":
            value = new_name
        elif field == "region":
            value = new_region
        elif field == "description" and value is not None:
            value = value.strip()

        setattr(holiday, field, value)

    # Ensure non-regional holidays never retain a regional designation.
    holiday.region = new_region

    try:
        add_holiday_audit(
            db,
            current_user,
            "holiday.updated",
            holiday,
            {"changed_fields": sorted(updates.keys())},
        )
        db.commit()
        db.refresh(holiday)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to update holiday",
        )

    return holiday


# ADMIN/HR: SOFT-DELETE HOLIDAY
@router.delete(
    "/{holiday_id}",
    response_model=HolidayResponse,
)
def deactivate_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    holiday = get_holiday_or_404(db, holiday_id)

    holiday.is_active = False

    try:
        add_holiday_audit(
            db,
            current_user,
            "holiday.deactivated",
            holiday,
        )
        db.commit()
        db.refresh(holiday)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to deactivate holiday",
        )

    return holiday


# EMPLOYEE: SELECT AN OPTIONAL HOLIDAY
@router.post(
    "/{holiday_id}/select",
    response_model=EmployeeHolidaySelectionResponse,
)
def select_optional_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=403,
            detail="An employee profile is required",
        )

    holiday = get_holiday_or_404(
        db,
        holiday_id,
        active_only=True,
    )

    if holiday.holiday_type != "Optional":
        raise HTTPException(
            status_code=400,
            detail="Only optional holidays can be selected",
        )

    if holiday.holiday_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Past holidays cannot be selected",
        )

    existing = (
        db.query(EmployeeHolidaySelection)
        .filter(
            EmployeeHolidaySelection.holiday_id == holiday.id,
            EmployeeHolidaySelection.employee_id == employee.id,
        )
        .first()
    )

    if existing:
        return existing

    selection = EmployeeHolidaySelection(
        holiday_id=holiday.id,
        employee_id=employee.id,
    )

    db.add(selection)

    try:
        db.commit()
        db.refresh(selection)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to select optional holiday",
        )

    return selection


# EMPLOYEE: CANCEL OPTIONAL HOLIDAY SELECTION
@router.delete("/{holiday_id}/select")
def cancel_optional_holiday_selection(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=403,
            detail="An employee profile is required",
        )

    holiday = get_holiday_or_404(
        db,
        holiday_id,
        active_only=True,
    )

    if holiday.holiday_type != "Optional":
        raise HTTPException(
            status_code=400,
            detail="Only optional holidays can be deselected",
        )

    if holiday.holiday_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Past holiday selections cannot be changed",
        )

    selection = (
        db.query(EmployeeHolidaySelection)
        .filter(
            EmployeeHolidaySelection.holiday_id == holiday.id,
            EmployeeHolidaySelection.employee_id == employee.id,
        )
        .first()
    )

    if not selection:
        raise HTTPException(
            status_code=404,
            detail="Optional holiday selection not found",
        )

    db.delete(selection)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to cancel optional holiday selection",
        )

    return {"message": "Optional holiday selection cancelled"}
