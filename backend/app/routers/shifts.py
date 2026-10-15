from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.shift import Shift, EmployeeShiftAssignment
from app.schemas.shift import (
    ShiftCreate,
    ShiftUpdate,
    ShiftResponse,
    ShiftAssignmentCreate,
    ShiftAssignmentResponse,
)

from app.utils.audit import record_audit_log

router = APIRouter(prefix="/shifts", tags=["Shift Management"])

admin_hr = Depends(require_roles("Admin", "HR"))


# --------------------------------------------------
# SHIFT ASSIGNMENTS
# --------------------------------------------------

@router.get("/assignments", response_model=list[ShiftAssignmentResponse])
def list_shift_assignments(
    employee_id: int | None = Query(default=None, gt=0),
    shift_id: int | None = Query(default=None, gt=0),
    department: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    query = db.query(EmployeeShiftAssignment)

    if employee_id is not None:
        query = query.filter(
            EmployeeShiftAssignment.employee_id == employee_id
        )

    if shift_id is not None:
        query = query.filter(
            EmployeeShiftAssignment.shift_id == shift_id
        )

    if department is not None:
        query = query.filter(
            func.lower(func.trim(EmployeeShiftAssignment.department))
            == department.strip().lower()
        )

    return query.order_by(
        EmployeeShiftAssignment.effective_from.desc(),
        EmployeeShiftAssignment.id.desc(),
    ).all()


@router.post(
    "/assignments",
    response_model=ShiftAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shift_assignment(
    payload: ShiftAssignmentCreate,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    shift = db.query(Shift).filter(
        Shift.id == payload.shift_id
    ).first()

    if not shift or not shift.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active shift not found",
        )

    if payload.employee_id is not None:
        employee = db.query(Employee).filter(
            Employee.id == payload.employee_id
        ).first()

        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found",
            )

        query = db.query(EmployeeShiftAssignment).filter(
            EmployeeShiftAssignment.employee_id == payload.employee_id
        )
    else:
        department_name = payload.department.strip()

        matching_employee = db.query(Employee.id).filter(
            func.lower(func.trim(Employee.department))
            == department_name.lower()
        ).first()

        if not matching_employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No employees found in this department",
            )

        query = db.query(EmployeeShiftAssignment).filter(
            EmployeeShiftAssignment.employee_id.is_(None),
            func.lower(func.trim(EmployeeShiftAssignment.department))
            == department_name.lower(),
        )

    query = query.filter(
        or_(
            EmployeeShiftAssignment.effective_to.is_(None),
            EmployeeShiftAssignment.effective_to >= payload.effective_from,
        )
    )

    if payload.effective_to is not None:
        query = query.filter(
            EmployeeShiftAssignment.effective_from <= payload.effective_to
        )

    if query.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An assignment already overlaps these effective dates",
        )

    assignment = EmployeeShiftAssignment(
        shift_id=payload.shift_id,
        employee_id=payload.employee_id,
        department=payload.department,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        assigned_by=current_user.id,
    )

    try:
        db.add(assignment)
        db.flush()

        record_audit_log(
            db=db,
            actor=current_user,
            action="shift.assignment.created",
            entity_type="shift_assignment",
            entity_id=assignment.id,
            details={
                "shift_id": assignment.shift_id,
                "employee_id": assignment.employee_id,
                "department": assignment.department,
                "effective_from": assignment.effective_from.isoformat(),
                "effective_to": (
                    assignment.effective_to.isoformat()
                    if assignment.effective_to else None
                ),
            },
        )

        db.commit()
        db.refresh(assignment)
        return assignment
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment could not be saved. Check the referenced IDs.",
        )


# --------------------------------------------------
# SHIFT CRUD
# --------------------------------------------------

@router.post(
    "/",
    response_model=ShiftResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shift(
    payload: ShiftCreate,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    shift = Shift(
        **payload.model_dump(),
        created_by=current_user.id,
    )

    try:
        db.add(shift)
        db.flush()

        record_audit_log(
            db=db,
            actor=current_user,
            action="shift.created",
            entity_type="shift",
            entity_id=shift.id,
            details={
                "name": shift.name,
                "shift_type": shift.shift_type,
                "start_time": str(shift.start_time) if shift.start_time else None,
                "end_time": str(shift.end_time) if shift.end_time else None,
            },
        )

        db.commit()
        db.refresh(shift)
        return shift
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A shift with this name may already exist",
        )


@router.get("/", response_model=list[ShiftResponse])
def list_shifts(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    query = db.query(Shift)

    if not include_inactive:
        query = query.filter(Shift.is_active.is_(True))

    return query.order_by(Shift.name.asc()).all()


@router.get("/{shift_id}", response_model=ShiftResponse)
def get_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    shift = db.query(Shift).filter(
        Shift.id == shift_id
    ).first()

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found",
        )

    return shift


@router.patch("/{shift_id}", response_model=ShiftResponse)
def update_shift(
    shift_id: int,
    payload: ShiftUpdate,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    shift = db.query(Shift).filter(
        Shift.id == shift_id
    ).first()

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found",
        )

    changes = payload.model_dump(exclude_unset=True)

    new_type = changes.get("shift_type", shift.shift_type)
    new_start = changes.get("start_time", shift.start_time)
    new_end = changes.get("end_time", shift.end_time)

    if new_type != "Flexible" and (
        new_start is None or new_end is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fixed shifts require start_time and end_time",
        )

    if (
        new_start is not None
        and new_end is not None
        and new_start == new_end
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Shift start and end times cannot be identical",
        )

    before = {
        field: (
            str(getattr(shift, field))
            if getattr(shift, field) is not None else None
        )
        for field in changes
    }

    for field, value in changes.items():
        setattr(shift, field, value)

    after = {
        field: (
            str(getattr(shift, field))
            if getattr(shift, field) is not None else None
        )
        for field in changes
    }

    record_audit_log(
        db=db,
        actor=current_user,
        action="shift.updated",
        entity_type="shift",
        entity_id=shift.id,
        details={
            "changed_fields": sorted(changes),
            "before": before,
            "after": after,
        },
    )

    try:
        db.commit()
        db.refresh(shift)
        return shift
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shift update failed. Check for a duplicate shift name.",
        )


@router.delete("/{shift_id}")
def deactivate_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    shift = db.query(Shift).filter(
        Shift.id == shift_id
    ).first()

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found",
        )

    if not shift.is_active:
        return {"message": "Shift is already inactive"}

    shift.is_active = False

    record_audit_log(
        db=db,
        actor=current_user,
        action="shift.deactivated",
        entity_type="shift",
        entity_id=shift.id,
        details={"name": shift.name, "is_active": False},
    )

    db.commit()

    return {
        "message": "Shift deactivated successfully",
        "shift_id": shift.id,
    }



# --------------------------------------------------
# ADMIN: OVERRIDE A SHIFT ASSIGNMENT
# --------------------------------------------------

class ShiftAssignmentOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_id: int = Field(gt=0)
    effective_from: date
    effective_to: date | None = None
    reason: str = Field(min_length=3, max_length=500)


@router.patch("/assignments/{assignment_id}/override",
              response_model=ShiftAssignmentResponse)
def override_shift_assignment(
    assignment_id: int,
    payload: ShiftAssignmentOverrideRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    assignment = db.query(EmployeeShiftAssignment).filter(
        EmployeeShiftAssignment.id == assignment_id
    ).first()

    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail="Shift assignment not found",
        )

    if (
        payload.effective_to is not None
        and payload.effective_to < payload.effective_from
    ):
        raise HTTPException(
            status_code=422,
            detail="effective_to cannot precede effective_from",
        )

    new_shift = db.query(Shift).filter(
        Shift.id == payload.shift_id,
        Shift.is_active.is_(True),
    ).first()

    if new_shift is None:
        raise HTTPException(
            status_code=404,
            detail="Active replacement shift not found",
        )

    # Check for another overlapping assignment to the same target.
    conflicts = db.query(EmployeeShiftAssignment).filter(
        EmployeeShiftAssignment.id != assignment_id
    )

    if assignment.employee_id is not None:
        conflicts = conflicts.filter(
            EmployeeShiftAssignment.employee_id == assignment.employee_id
        )
    else:
        conflicts = conflicts.filter(
            EmployeeShiftAssignment.employee_id.is_(None),
            func.lower(func.trim(EmployeeShiftAssignment.department))
            == (assignment.department or "").strip().lower(),
        )

    conflicts = conflicts.filter(
        EmployeeShiftAssignment.effective_from
        <= (payload.effective_to or date.max),
        or_(
            EmployeeShiftAssignment.effective_to.is_(None),
            EmployeeShiftAssignment.effective_to >= payload.effective_from,
        ),
    )

    if conflicts.first():
        raise HTTPException(
            status_code=409,
            detail="The override overlaps another assignment for this target",
        )

    before = {
        "shift_id": assignment.shift_id,
        "effective_from": assignment.effective_from.isoformat(),
        "effective_to": (
            assignment.effective_to.isoformat()
            if assignment.effective_to else None
        ),
    }

    assignment.shift_id = payload.shift_id
    assignment.effective_from = payload.effective_from
    assignment.effective_to = payload.effective_to

    after = {
        "shift_id": assignment.shift_id,
        "effective_from": assignment.effective_from.isoformat(),
        "effective_to": (
            assignment.effective_to.isoformat()
            if assignment.effective_to else None
        ),
    }

    record_audit_log(
        db=db,
        actor=current_user,
        action="shift.assignment.overridden",
        entity_type="shift_assignment",
        entity_id=assignment.id,
        details={
            "reason": payload.reason.strip(),
            "before": before,
            "after": after,
        },
    )

    try:
        db.commit()
        db.refresh(assignment)
        return assignment
    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# SHIFT ASSIGNMENT: AUDIT HISTORY
# --------------------------------------------------

@router.get("/assignments/{assignment_id}/history")
def get_shift_assignment_history(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    assignment = db.query(EmployeeShiftAssignment).filter(
        EmployeeShiftAssignment.id == assignment_id
    ).first()

    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail="Shift assignment not found",
        )

    entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "shift_assignment",
            AuditLog.entity_id == str(assignment_id),
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


# --------------------------------------------------
# SHIFT ATTENDANCE REPORT
# --------------------------------------------------

@router.get("/reports/attendance")
def shift_attendance_report(
    start_date: date,
    end_date: date,
    employee_id: int | None = Query(default=None, gt=0),
    shift_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user=admin_hr,
):
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date cannot precede start_date",
        )

    query = db.query(Attendance).filter(
        Attendance.attendance_date >= start_date,
        Attendance.attendance_date <= end_date,
    )

    if employee_id is not None:
        query = query.filter(Attendance.employee_id == employee_id)

    attendance_rows = (
        query.order_by(
            Attendance.attendance_date.desc(),
            Attendance.id.desc(),
        )
        .limit(limit)
        .all()
    )

    # Reuse the existing response calculation without writing attendance.
    from app.routers.attendance import to_response

    records = [to_response(row, db) for row in attendance_rows]

    if shift_id is not None:
        records = [
            record for record in records
            if record["assigned_shift_id"] == shift_id
        ]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "returned_records": len(records),
        "late_count": sum(
            record["is_late"] is True for record in records
        ),
        "early_checkout_count": sum(
            record["is_early_checkout"] is True for record in records
        ),
        "overtime_count": sum(
            (record["overtime_minutes"] or 0) > 0 for record in records
        ),
        "total_overtime_minutes": sum(
            record["overtime_minutes"] or 0 for record in records
        ),
        "records": records,
    }

