import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.holiday import Holiday, EmployeeHolidaySelection
from app.models.shift import Shift, EmployeeShiftAssignment
from app.models.user import User
from app.services.notification_service import create_in_app_notification
from app.routers.auth import get_current_user
from app.schemas.attendance import (
    AttendanceResponse,
    AttendanceMonthlySummary,
)
from app.utils.audit import record_audit_log


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"],
)

# HRMS company-local calendar date.
COMPANY_TZ = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------
# ADMIN ATTENDANCE CORRECTION REQUEST
# ---------------------------------------------------------

class AttendanceOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attendance_date: date | None = None
    check_in: datetime | None = None
    check_out: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------
# COMMON HELPERS
# ---------------------------------------------------------

def get_employee(
    db: Session,
    user_id: int,
) -> Employee:
    employee = (
        db.query(Employee)
        .filter(
            Employee.user_id == user_id,
            Employee.is_active.is_(True),
        )
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active employee record not found",
        )

    return employee


def normalize_input_datetime(value: datetime) -> datetime:
    """
    Accept timezone-aware API timestamps.

    If the client submits a timestamp without a timezone,
    interpret it as Chennai local time, then convert to UTC.
    Store timestamps consistently in UTC.
    """

    if value.tzinfo is None:
        value = value.replace(tzinfo=COMPANY_TZ)

    return value.astimezone(timezone.utc)


def as_utc_datetime(value: datetime) -> datetime:
    """
    Normalize a timestamp read from the database.

    MySQL may return a naive datetime even when the SQLAlchemy
    model uses DateTime(timezone=True). Existing naive database
    values are treated as UTC.
    """

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def current_utc_time() -> datetime:
    return datetime.now(timezone.utc)


def current_company_date() -> date:
    return datetime.now(COMPANY_TZ).date()


def calculate_working_hours(
    check_in_value: datetime,
    check_out_value: datetime | None,
) -> float | None:
    if check_out_value is None:
        return None

    start = as_utc_datetime(check_in_value)
    end = as_utc_datetime(check_out_value)

    return round(
        max(0.0, (end - start).total_seconds() / 3600),
        2,
    )


def get_assigned_shift(
    db: Session,
    employee_id: int,
    attendance_date: date,
) -> Shift | None:
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        return None

    date_filters = [
        EmployeeShiftAssignment.effective_from <= attendance_date,
        or_(
            EmployeeShiftAssignment.effective_to.is_(None),
            EmployeeShiftAssignment.effective_to >= attendance_date,
        ),
    ]

    # Prefer an employee-specific assignment.
    shift = (
        db.query(Shift)
        .join(
            EmployeeShiftAssignment,
            EmployeeShiftAssignment.shift_id == Shift.id,
        )
        .filter(
            EmployeeShiftAssignment.employee_id == employee_id,
            *date_filters,
        )
        .order_by(
            EmployeeShiftAssignment.effective_from.desc(),
            EmployeeShiftAssignment.id.desc(),
        )
        .first()
    )

    if shift is not None:
        return shift

    # Fall back to a department assignment.
    department = (employee.department or "").strip().lower()
    if not department:
        return None

    return (
        db.query(Shift)
        .join(
            EmployeeShiftAssignment,
            EmployeeShiftAssignment.shift_id == Shift.id,
        )
        .filter(
            EmployeeShiftAssignment.employee_id.is_(None),
            func.lower(func.trim(EmployeeShiftAssignment.department))
            == department,
            *date_filters,
        )
        .order_by(
            EmployeeShiftAssignment.effective_from.desc(),
            EmployeeShiftAssignment.id.desc(),
        )
        .first()
    )


def calculate_shift_metrics(
    record: Attendance,
    shift: Shift | None,
) -> dict:
    metrics = {
        "assigned_shift_id": None,
        "assigned_shift_name": None,
        "shift_type": None,
        "is_late": None,
        "late_minutes": None,
        "is_early_checkout": None,
        "early_checkout_minutes": None,
        "overtime_minutes": None,
    }

    if shift is None:
        return metrics

    metrics.update({
        "assigned_shift_id": shift.id,
        "assigned_shift_name": shift.name,
        "shift_type": shift.shift_type,
    })

    # Flexible shifts use expected duration instead of fixed times.
    if shift.shift_type == "Flexible":
        if record.check_out is not None:
            start = as_utc_datetime(record.check_in)
            end = as_utc_datetime(record.check_out)
            worked_minutes = max(
                0, int((end - start).total_seconds() // 60)
            )
            metrics["overtime_minutes"] = max(
                0, worked_minutes - shift.expected_work_minutes
            )
        return metrics

    check_in_local = as_utc_datetime(
        record.check_in
    ).astimezone(COMPANY_TZ)

    if shift.start_time is not None:
        scheduled_start = datetime.combine(
            record.attendance_date,
            shift.start_time,
        ).replace(tzinfo=COMPANY_TZ)

        grace_deadline = scheduled_start + timedelta(
            minutes=shift.grace_period_minutes
        )
        late_seconds = (
            check_in_local - grace_deadline
        ).total_seconds()

        metrics["is_late"] = late_seconds > 0
        metrics["late_minutes"] = (
            int((late_seconds + 59) // 60)
            if late_seconds > 0 else 0
        )

    if record.check_out is None or shift.end_time is None:
        return metrics

    check_out_local = as_utc_datetime(
        record.check_out
    ).astimezone(COMPANY_TZ)

    end_date = record.attendance_date
    if (
        shift.start_time is not None
        and shift.end_time <= shift.start_time
    ):
        end_date += timedelta(days=1)

    scheduled_end = datetime.combine(
        end_date,
        shift.end_time,
    ).replace(tzinfo=COMPANY_TZ)

    early_seconds = (
        scheduled_end - check_out_local
    ).total_seconds()

    metrics["is_early_checkout"] = early_seconds > 0
    metrics["early_checkout_minutes"] = (
        int((early_seconds + 59) // 60)
        if early_seconds > 0 else 0
    )

    overtime_seconds = (
        check_out_local - scheduled_end
    ).total_seconds()

    metrics["overtime_minutes"] = max(
        0, int(overtime_seconds // 60)
    )

    return metrics


def to_response(record: Attendance, db: Session) -> dict:
    response = {
        "id": record.id,
        "employee_id": record.employee_id,
        "attendance_date": record.attendance_date,
        "check_in": as_utc_datetime(record.check_in),
        "check_out": (
            as_utc_datetime(record.check_out)
            if record.check_out is not None
            else None
        ),
        "working_hours": calculate_working_hours(
            record.check_in,
            record.check_out,
        ),
    }

    shift = get_assigned_shift(
        db,
        record.employee_id,
        record.attendance_date,
    )
    response.update(calculate_shift_metrics(record, shift))
    return response


def notify_attendance_in_app_safely(
    db: Session,
    user: User,
    record: Attendance,
    event: str,
) -> None:
    try:
        if event == "check-in":
            event_time = record.check_in
            title = "Attendance check-in recorded"
            action_text = "checked in"
        else:
            event_time = record.check_out
            title = "Attendance check-out recorded"
            action_text = "checked out"

        if event_time is None:
            return

        local_time = (
            as_utc_datetime(event_time)
            .astimezone(COMPANY_TZ)
            .strftime("%H:%M")
        )

        notification = create_in_app_notification(
            db=db,
            recipient_user_id=user.id,
            title=title,
            message=(
                f"Your attendance for {record.attendance_date.isoformat()} "
                f"was {action_text} at {local_time}."
            ),
            category="attendance",
            created_by_user_id=user.id,
            source_entity_type="attendance",
            source_entity_id=record.id,
        )
        if notification is not None:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to create attendance notification for attendance_id=%s",
            record.id,
        )


def get_attendance_or_404(
    db: Session,
    attendance_id: int,
    lock: bool = False,
) -> Attendance:
    query = db.query(Attendance).filter(
        Attendance.id == attendance_id
    )

    if lock:
        query = query.with_for_update()

    record = query.first()

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found",
        )

    return record


# ---------------------------------------------------------
# EMPLOYEE CHECK-IN
# ---------------------------------------------------------

@router.post(
    "/check-in",
    response_model=AttendanceResponse,
)
def check_in(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_employee(db, current_user.id)

    now = current_utc_time()
    today = now.astimezone(COMPANY_TZ).date()

    # Prevent a second attendance record for the same local day.
    existing_today = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date == today,
        )
        .first()
    )

    if existing_today is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already exists for today",
        )

    # Also prevent another check-in when an earlier attendance
    # record has not been checked out (e.g. an overnight shift).
    open_record = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.check_out.is_(None),
        )
        .order_by(
            Attendance.attendance_date.desc(),
            Attendance.id.desc(),
        )
        .first()
    )

    if open_record is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You have an unfinished attendance record. "
                "Check out before starting another attendance."
            ),
        )

    record = Attendance(
        employee_id=employee.id,
        attendance_date=today,
        check_in=now,
        check_out=None,
    )

    try:
        db.add(record)

        # Obtain the generated ID for the audit entry.
        db.flush()

        record_audit_log(
            db=db,
            actor=current_user,
            action="attendance.checked_in",
            entity_type="attendance",
            entity_id=record.id,
            details={
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
                "attendance_date": today.isoformat(),
                "check_in": now.isoformat(),
            },
        )

        # Attendance and audit log commit together.
        db.commit()
        db.refresh(record)

    except IntegrityError as exc:
        db.rollback()

        # Handles concurrent requests protected by the
        # unique employee_id + attendance_date constraint.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already exists for this date",
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to record check-in",
        ) from exc

    notify_attendance_in_app_safely(
        db=db, user=current_user, record=record, event="check-in"
    )
    return to_response(record, db)


# ---------------------------------------------------------
# EMPLOYEE CHECK-OUT
# ---------------------------------------------------------

@router.post(
    "/check-out",
    response_model=AttendanceResponse,
)
def check_out(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_employee(db, current_user.id)
    today = current_company_date()

    # Select the latest unfinished record. This permits an
    # overnight shift to check out after midnight.
    record = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.check_out.is_(None),
        )
        .order_by(
            Attendance.attendance_date.desc(),
            Attendance.id.desc(),
        )
        .with_for_update()
        .first()
    )

    if record is None:
        completed_today = (
            db.query(Attendance)
            .filter(
                Attendance.employee_id == employee.id,
                Attendance.attendance_date == today,
            )
            .first()
        )

        if (
            completed_today is not None
            and completed_today.check_out is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already checked out today",
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check in before checking out",
        )

    now = current_utc_time()
    check_in_time = as_utc_datetime(record.check_in)

    if now < check_in_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-out cannot be earlier than check-in",
        )

    record.check_out = now

    try:
        record_audit_log(
            db=db,
            actor=current_user,
            action="attendance.checked_out",
            entity_type="attendance",
            entity_id=record.id,
            details={
                "employee_id": employee.id,
                "attendance_date": (
                    record.attendance_date.isoformat()
                ),
                "check_in": check_in_time.isoformat(),
                "check_out": now.isoformat(),
                "working_hours": calculate_working_hours(
                    check_in_time,
                    now,
                ),
            },
        )

        db.commit()
        db.refresh(record)

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to record check-out",
        ) from exc

    notify_attendance_in_app_safely(
        db=db, user=current_user, record=record, event="check-out"
    )
    return to_response(record, db)


# ---------------------------------------------------------
# EMPLOYEE: VIEW OWN ATTENDANCE HISTORY
# ---------------------------------------------------------

@router.get(
    "/me",
    response_model=list[AttendanceResponse],
)
def my_attendance(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_employee(db, current_user.id)

    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id
        )
        .order_by(
            Attendance.attendance_date.desc(),
            Attendance.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [to_response(record, db) for record in records]


# ---------------------------------------------------------
# EMPLOYEE: MONTHLY ATTENDANCE SUMMARY
# ---------------------------------------------------------

def get_monthly_holiday_metrics(
    db: Session,
    employee: Employee,
    start_date: date,
    end_date_exclusive: date,
) -> dict[str, int]:
    """Count weekdays and applicable holidays for a monthly summary."""
    weekdays = set()
    current_date = start_date

    while current_date < end_date_exclusive:
        if current_date.weekday() < 5:
            weekdays.add(current_date)
        current_date += timedelta(days=1)

    if not weekdays:
        return {"scheduled_working_days": 0, "holidays_excluded": 0}

    applicable_filters = [Holiday.holiday_type == "Company"]

    if employee.region and employee.region.strip():
        applicable_filters.append(
            and_(
                Holiday.holiday_type == "Regional",
                func.lower(func.trim(Holiday.region))
                == employee.region.strip().lower(),
            )
        )

    selected_holiday_ids = (
        db.query(EmployeeHolidaySelection.holiday_id)
        .filter(EmployeeHolidaySelection.employee_id == employee.id)
    )
    applicable_filters.append(
        and_(
            Holiday.holiday_type == "Optional",
            Holiday.id.in_(selected_holiday_ids),
        )
    )

    holiday_rows = (
        db.query(Holiday.holiday_date)
        .filter(
            Holiday.is_active.is_(True),
            Holiday.holiday_date >= start_date,
            Holiday.holiday_date < end_date_exclusive,
            or_(*applicable_filters),
        )
        .all()
    )

    # A holiday on a weekend does not reduce scheduled weekdays.
    holiday_dates = {
        row[0] for row in holiday_rows if row[0] in weekdays
    }

    return {
        "scheduled_working_days": len(weekdays - holiday_dates),
        "holidays_excluded": len(holiday_dates),
    }


@router.get(
    "/summary",
    response_model=AttendanceMonthlySummary,
)
def monthly_summary(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
        .order_by(Attendance.attendance_date)
        .all()
    )

    total_hours = 0.0

    for record in records:
        hours = calculate_working_hours(
            record.check_in,
            record.check_out,
        )

        # An open attendance record has no completed working-hours
        # value, so it is excluded from the hours total.
        if hours is not None:
            total_hours += hours

    calendar_metrics = get_monthly_holiday_metrics(
        db, employee, start_date, end_date
    )

    return {
        "month": month,
        "year": year,
        "total_days_present": len(records),
        "total_working_hours": round(total_hours, 2),
        **calendar_metrics,
    }


# ---------------------------------------------------------
# ADMIN/HR: LIST ATTENDANCE RECORDS
# ---------------------------------------------------------

@router.get(
    "/",
    response_model=list[AttendanceResponse],
)
def list_attendance(
    employee_id: int | None = Query(default=None, ge=1),
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    if (
        start_date is not None
        and end_date is not None
        and end_date < start_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date cannot be before start date",
        )

    query = db.query(Attendance)

    if employee_id is not None:
        query = query.filter(
            Attendance.employee_id == employee_id
        )

    if start_date is not None:
        query = query.filter(
            Attendance.attendance_date >= start_date
        )

    if end_date is not None:
        query = query.filter(
            Attendance.attendance_date <= end_date
        )

    records = (
        query
        .order_by(
            Attendance.attendance_date.desc(),
            Attendance.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [to_response(record, db) for record in records]


# ---------------------------------------------------------
# ADMIN ONLY: CORRECT ATTENDANCE
# ---------------------------------------------------------

@router.patch(
    "/{attendance_id}/override",
    response_model=AttendanceResponse,
)
def override_attendance(
    attendance_id: int,
    data: AttendanceOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin")
    ),
):
    record = get_attendance_or_404(
        db=db,
        attendance_id=attendance_id,
        lock=True,
    )

    fields_set = data.model_fields_set
    changed_fields = sorted(fields_set - {"reason"})

    if not changed_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Provide attendance_date, check_in, "
                "or check_out to correct"
            ),
        )

    if "attendance_date" in fields_set:
        if data.attendance_date is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attendance date cannot be null",
            )

    if "check_in" in fields_set and data.check_in is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in time cannot be null",
        )

    reason = data.reason.strip()

    if len(reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a meaningful correction reason",
        )

    # Capture the original state for audit history.
    before = {
        "attendance_date": record.attendance_date.isoformat(),
        "check_in": as_utc_datetime(
            record.check_in
        ).isoformat(),
        "check_out": (
            as_utc_datetime(record.check_out).isoformat()
            if record.check_out is not None
            else None
        ),
    }

    new_check_in = as_utc_datetime(record.check_in)
    new_check_out = (
        as_utc_datetime(record.check_out)
        if record.check_out is not None
        else None
    )
    new_attendance_date = record.attendance_date

    if "check_in" in fields_set:
        new_check_in = normalize_input_datetime(
            data.check_in
        )

        # If the check-in timestamp changes and a date was not
        # separately supplied, derive the new company-local date.
        if "attendance_date" not in fields_set:
            new_attendance_date = (
                new_check_in.astimezone(COMPANY_TZ).date()
            )

    if "attendance_date" in fields_set:
        new_attendance_date = data.attendance_date

    if "check_out" in fields_set:
        new_check_out = (
            normalize_input_datetime(data.check_out)
            if data.check_out is not None
            else None
        )

    if (
        new_check_out is not None
        and new_check_out < new_check_in
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-out cannot be earlier than check-in",
        )

    try:
        record.attendance_date = new_attendance_date
        record.check_in = new_check_in
        record.check_out = new_check_out

        after = {
            "attendance_date": (
                record.attendance_date.isoformat()
            ),
            "check_in": new_check_in.isoformat(),
            "check_out": (
                new_check_out.isoformat()
                if new_check_out is not None
                else None
            ),
        }

        record_audit_log(
            db=db,
            actor=current_user,
            action="attendance.admin_overridden",
            entity_type="attendance",
            entity_id=record.id,
            details={
                "employee_id": record.employee_id,
                "changed_fields": changed_fields,
                "reason": reason,
                "before": before,
                "after": after,
            },
        )

        # Correction and audit entry commit together.
        db.commit()
        db.refresh(record)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The correction conflicts with an existing "
                "attendance record for this employee and date"
            ),
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to correct attendance record",
        ) from exc

    return to_response(record, db)