
from datetime import datetime, date, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.routers.auth import get_current_user
from app.schemas.attendance import (
    AttendanceResponse,
    AttendanceMonthlySummary,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def get_employee(db: Session, user_id: int) -> Employee:
    employee = (
        db.query(Employee)
        .filter(
            Employee.user_id == user_id,
            Employee.is_active.is_(True),
        )
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Active employee record not found",
        )

    return employee


def to_response(record: Attendance) -> dict:
    hours = None

    if record.check_out:
        start = record.check_in
        end = record.check_out

        # MySQL drivers may return naive datetimes for timezone columns.
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        hours = round((end - start).total_seconds() / 3600, 2)

    return {
        "id": record.id,
        "employee_id": record.employee_id,
        "attendance_date": record.attendance_date,
        "check_in": record.check_in,
        "check_out": record.check_out,
        "working_hours": hours,
    }


@router.post("/check-in", response_model=AttendanceResponse)
def check_in(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    employee = get_employee(db, current_user.id)

    now = datetime.now(timezone.utc)
    today = now.date()

    existing = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date == today,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already exists for today",
        )

    record = Attendance(
        employee_id=employee.id,
        attendance_date=today,
        check_in=now,
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Attendance could not be created; check for an existing record",
        )

    return to_response(record)


@router.post("/check-out", response_model=AttendanceResponse)
def check_out(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    employee = get_employee(db, current_user.id)

    today = datetime.now(timezone.utc).date()

    record = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date == today,
        )
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Check in before checking out",
        )

    if record.check_out:
        raise HTTPException(
            status_code=409,
            detail="You have already checked out today",
        )

    now = datetime.now(timezone.utc)

    if record.check_in.tzinfo is None:
        check_in_time = record.check_in.replace(tzinfo=timezone.utc)
    else:
        check_in_time = record.check_in

    if now < check_in_time:
        raise HTTPException(
            status_code=400,
            detail="Check-out cannot be earlier than check-in",
        )

    record.check_out = now
    db.commit()
    db.refresh(record)

    return to_response(record)


@router.get("/me", response_model=list[AttendanceResponse])
def my_attendance(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    employee = get_employee(db, current_user.id)

    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee.id)
        .order_by(Attendance.attendance_date.desc())
        .all()
    )

    return [to_response(record) for record in records]


@router.get("/summary", response_model=AttendanceMonthlySummary)
def monthly_summary(
    month: int,
    year: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(
            status_code=400,
            detail="Provide a valid month and year",
        )

    employee = get_employee(db, current_user.id)

    start_date = date(year, month, 1)

    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date < end_date,
        )
        .all()
    )

    total_hours = 0.0

    for record in records:
        if record.check_out:
            start = record.check_in
            end = record.check_out

            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)

            total_hours += (end - start).total_seconds() / 3600

    return {
        "month": month,
        "year": year,
        "total_days_present": len(records),
        "total_working_hours": round(total_hours, 2),
    }
