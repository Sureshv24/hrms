import logging
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.leave import LeaveRequest
from app.models.payroll import Payroll
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.payroll import PayrollResponse
from app.services.email_service import send_payroll_notification_email
from app.utils.audit import record_audit_log


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payroll", tags=["Payroll"])

CENT = Decimal("0.01")
DAILY_SALARY_BASIS = Decimal("30")


class PayrollAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adjustment_amount: Decimal = Field(
        ...,
        max_digits=12,
        decimal_places=2,
    )
    reason: str = Field(..., min_length=5, max_length=500)


def money(value: Decimal) -> Decimal:
    """Round a monetary value to two decimal places."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def get_payroll_or_404(payroll_id: int, db: Session) -> Payroll:
    payroll = db.query(Payroll).filter(Payroll.id == payroll_id).first()
    if payroll is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll not found",
        )
    return payroll


def notify_payroll_owner_safely(db: Session, payroll: Payroll) -> None:
    """Send a payroll email after commit; email failures do not undo payroll."""
    try:
        employee = (
            db.query(Employee)
            .filter(Employee.id == payroll.employee_id)
            .first()
        )
        if employee is None:
            logger.warning(
                "Payroll notification skipped: employee not found for payroll_id=%s",
                payroll.id,
            )
            return

        user = db.query(User).filter(User.id == employee.user_id).first()
        if user is None or not user.email:
            logger.warning(
                "Payroll notification skipped: user or email missing for payroll_id=%s",
                payroll.id,
            )
            return

        email_status = send_payroll_notification_email(
            db=db,
            recipient_email=user.email,
            employee_name=user.full_name,
            month=payroll.month,
            year=payroll.year,
            net_salary=payroll.net_salary,
            payroll_status=payroll.status,
            payroll_id=payroll.id,
        )
        if email_status != "sent":
            logger.warning(
                "Payroll notification status=%s for payroll_id=%s",
                email_status,
                payroll.id,
            )
    except Exception:
        logger.exception(
            "Unable to process payroll notification for payroll_id=%s",
            payroll.id,
        )


def iter_dates(start_date: date, end_date: date):
    """Yield calendar dates inclusively."""
    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def get_working_dates(start_date: date, end_date: date) -> set[date]:
    """Return Monday-Friday dates; no company holiday calendar is configured."""
    if start_date > end_date:
        return set()
    return {
        current_date
        for current_date in iter_dates(start_date, end_date)
        if current_date.weekday() < 5
    }


def get_approved_leave_impact(
    db: Session,
    employee_id: int,
    period_start: date,
    period_end: date,
) -> tuple[set[date], set[date]]:
    """Return weekdays covered by approved leave and dates charged as LOP."""
    approved_leave_dates: set[date] = set()
    lop_leave_dates: set[date] = set()

    if period_start > period_end:
        return approved_leave_dates, lop_leave_dates

    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "Approved",
            LeaveRequest.start_date <= period_end,
            LeaveRequest.end_date >= period_start,
        )
        .all()
    )

    for leave in leaves:
        overlap_start = max(leave.start_date, period_start)
        overlap_end = min(leave.end_date, period_end)

        for current_date in iter_dates(overlap_start, overlap_end):
            if current_date.weekday() < 5:
                approved_leave_dates.add(current_date)

        leave_lop_days = max(0, int(leave.lop_days or 0))
        if leave_lop_days == 0:
            continue

        # The existing leave workflow treats LOP as the final calendar
        # days of an approved leave period.
        lop_start = leave.end_date - timedelta(days=leave_lop_days - 1)
        lop_overlap_start = max(leave.start_date, lop_start, period_start)
        lop_overlap_end = min(leave.end_date, period_end)
        if lop_overlap_start > lop_overlap_end:
            continue

        for current_date in iter_dates(lop_overlap_start, lop_overlap_end):
            if current_date.weekday() < 5:
                lop_leave_dates.add(current_date)

    return approved_leave_dates, lop_leave_dates


def calculate_payroll_attendance(
    db: Session,
    employee_id: int,
    period_start: date,
    period_end: date,
    month_is_complete: bool,
) -> tuple[int, int, int]:
    """Calculate present days, total LOP days, and unauthorized absences."""
    working_dates = get_working_dates(period_start, period_end)
    if not working_dates:
        return 0, 0, 0

    attendance_rows = (
        db.query(Attendance.attendance_date)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date >= period_start,
            Attendance.attendance_date <= period_end,
        )
        .all()
    )
    attendance_dates = {row[0] for row in attendance_rows if row[0] is not None}
    present_dates = attendance_dates.intersection(working_dates)
    present_days = len(present_dates)

    approved_leave_dates, lop_leave_dates = get_approved_leave_impact(
        db=db,
        employee_id=employee_id,
        period_start=period_start,
        period_end=period_end,
    )

    # Actual attendance takes precedence over leave LOP for the same date.
    lop_leave_dates.difference_update(attendance_dates)
    approved_leave_workdays = approved_leave_dates.intersection(working_dates)

    unauthorized_absence_dates: set[date] = set()
    # In an incomplete current month, do not treat future/missing weekdays
    # as absences. For a completed month, weekdays without attendance or
    # approved leave are counted as unauthorized absences.
    if month_is_complete:
        unauthorized_absence_dates = (
            working_dates - present_dates - approved_leave_workdays
        )

    approved_lop_days = len(lop_leave_dates)
    unauthorized_absence_days = len(unauthorized_absence_dates)
    total_lop_days = approved_lop_days + unauthorized_absence_days

    return present_days, total_lop_days, unauthorized_absence_days


@router.post(
    "/generate",
    response_model=PayrollResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_payroll(
    employee_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    today = date.today()

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])

    # Preserve the existing duplicate-first behavior.
    existing = (
        db.query(Payroll)
        .filter(
            Payroll.employee_id == employee_id,
            Payroll.month == month,
            Payroll.year == year,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payroll already exists for this employee and month",
        )

    if month_start > today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate payroll for a future month",
        )

    # IMPORTANT: Do not create payroll for a month that ended before
    # the employee's joining date. This validation must stay inside
    # generate_payroll(), at the same indentation level as the other checks.
    joining_date = employee.joining_date
    if joining_date > month_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot generate payroll for {year}-{month:02d}. "
                f"The employee joined on {joining_date.isoformat()}, "
                "after this payroll period ended."
            ),
        )

    if joining_date > today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate payroll before the employee's joining date",
        )

    period_start = max(month_start, joining_date)
    period_end = min(month_end, today)
    month_is_complete = month_end < today

    attendance_count, lop_days, unauthorized_absence_days = (
        calculate_payroll_attendance(
            db=db,
            employee_id=employee_id,
            period_start=period_start,
            period_end=period_end,
            month_is_complete=month_is_complete,
        )
    )

    monthly_salary = money(Decimal(str(employee.salary)))
    gross_salary = monthly_salary
    lop_deduction = money(
        monthly_salary * Decimal(lop_days) / DAILY_SALARY_BASIS
    )
    lop_deduction = min(lop_deduction, gross_salary)
    net_salary = money(gross_salary - lop_deduction)

    payroll = Payroll(
        employee_id=employee_id,
        month=month,
        year=year,
        monthly_salary=monthly_salary,
        present_days=attendance_count,
        lop_days=lop_days,
        gross_salary=gross_salary,
        lop_deduction=lop_deduction,
        net_salary=net_salary,
        manual_adjustment_amount=Decimal("0.00"),
        status="Generated",
        is_locked=False,
        generated_by=current_user.id,
    )

    try:
        db.add(payroll)
        db.flush()

        record_audit_log(
            db=db,
            actor=current_user,
            action="payroll.generated",
            entity_type="payroll",
            entity_id=payroll.id,
            details={
                "employee_id": employee_id,
                "month": month,
                "year": year,
                "present_days": attendance_count,
                "lop_days": lop_days,
                "unauthorized_absence_days": unauthorized_absence_days,
                "gross_salary": str(gross_salary),
                "lop_deduction": str(lop_deduction),
                "net_salary": str(net_salary),
                "status": "Generated",
                "absence_deduction_applied": month_is_complete,
            },
        )
        db.commit()
        db.refresh(payroll)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payroll already exists for this employee and month",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate payroll",
        ) from exc

    notify_payroll_owner_safely(db=db, payroll=payroll)
    return payroll


@router.get("/me", response_model=list[PayrollResponse])
def my_payroll_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.id)
        .first()
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )

    return (
        db.query(Payroll)
        .filter(Payroll.employee_id == employee.id)
        .order_by(Payroll.year.desc(), Payroll.month.desc())
        .all()
    )


@router.get("/", response_model=list[PayrollResponse])
def list_payroll(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    query = db.query(Payroll)
    if month is not None:
        query = query.filter(Payroll.month == month)
    if year is not None:
        query = query.filter(Payroll.year == year)
    return (
        query.order_by(
            Payroll.year.desc(),
            Payroll.month.desc(),
            Payroll.employee_id,
        )
        .all()
    )


@router.get("/{payroll_id}", response_model=PayrollResponse)
def get_payroll(
    payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payroll = get_payroll_or_404(payroll_id, db)

    if current_user.role not in ("Admin", "HR"):
        employee = (
            db.query(Employee)
            .filter(Employee.user_id == current_user.id)
            .first()
        )
        if employee is None or payroll.employee_id != employee.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payroll not found",
            )
    return payroll


@router.patch("/{payroll_id}/adjustment", response_model=PayrollResponse)
def adjust_payroll(
    payroll_id: int,
    data: PayrollAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    payroll = (
        db.query(Payroll)
        .filter(Payroll.id == payroll_id)
        .with_for_update()
        .first()
    )
    if payroll is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll not found",
        )

    if payroll.is_locked or payroll.status in ("Locked", "Paid"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot adjust locked or paid payroll. "
                "Only generated, unlocked payroll can be adjusted."
            ),
        )

    reason = data.reason.strip()
    if len(reason) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a meaningful adjustment reason",
        )

    try:
        requested_adjustment = money(data.adjustment_amount)
        if not requested_adjustment.is_finite():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adjustment amount must be a finite number",
            )

        previous_adjustment = money(
            Decimal(str(payroll.manual_adjustment_amount or "0.00"))
        )
        previous_net_salary = money(Decimal(str(payroll.net_salary)))
        gross_salary = Decimal(str(payroll.gross_salary))
        lop_deduction = Decimal(str(payroll.lop_deduction))

        # Submitted amount replaces the prior adjustment; positive is
        # an addition and negative is a deduction.
        new_net_salary = money(
            gross_salary - lop_deduction + requested_adjustment
        )
        if new_net_salary < Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adjustment cannot make net salary negative",
            )

        payroll.manual_adjustment_amount = requested_adjustment
        payroll.adjustment_reason = reason
        payroll.adjusted_by = current_user.id
        payroll.adjusted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        payroll.net_salary = new_net_salary

        record_audit_log(
            db=db,
            actor=current_user,
            action="payroll.manually_adjusted",
            entity_type="payroll",
            entity_id=payroll.id,
            details={
                "employee_id": payroll.employee_id,
                "month": payroll.month,
                "year": payroll.year,
                "previous_adjustment": str(previous_adjustment),
                "new_adjustment": str(requested_adjustment),
                "previous_net_salary": str(previous_net_salary),
                "new_net_salary": str(new_net_salary),
                "reason": reason,
            },
        )
        db.commit()
        db.refresh(payroll)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to adjust payroll",
        ) from exc

    notify_payroll_owner_safely(db=db, payroll=payroll)
    return payroll


@router.post("/{payroll_id}/lock", response_model=PayrollResponse)
def lock_payroll(
    payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    payroll = get_payroll_or_404(payroll_id, db)
    if payroll.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payroll is already locked",
        )

    payroll.is_locked = True
    payroll.status = "Locked"
    payroll.locked_at = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        record_audit_log(
            db=db,
            actor=current_user,
            action="payroll.locked",
            entity_type="payroll",
            entity_id=payroll.id,
            details={
                "employee_id": payroll.employee_id,
                "month": payroll.month,
                "year": payroll.year,
                "net_salary": str(payroll.net_salary),
                "status": "Locked",
            },
        )
        db.commit()
        db.refresh(payroll)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to lock payroll",
        ) from exc

    notify_payroll_owner_safely(db=db, payroll=payroll)
    return payroll


@router.post("/{payroll_id}/credit", response_model=PayrollResponse)
def simulate_salary_credit(
    payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    payroll = get_payroll_or_404(payroll_id, db)

    if not payroll.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lock payroll before simulating salary credit",
        )
    if payroll.status == "Paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Salary credit has already been simulated",
        )

    # Simulation only: this does not transfer money to a bank account.
    payroll.status = "Paid"
    payroll.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        record_audit_log(
            db=db,
            actor=current_user,
            action="payroll.credit_simulated",
            entity_type="payroll",
            entity_id=payroll.id,
            details={
                "employee_id": payroll.employee_id,
                "month": payroll.month,
                "year": payroll.year,
                "net_salary": str(payroll.net_salary),
                "status": "Paid",
                "payment_type": "simulation_only",
            },
        )
        db.commit()
        db.refresh(payroll)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to simulate salary credit",
        ) from exc

    notify_payroll_owner_safely(db=db, payroll=payroll)
    return payroll
