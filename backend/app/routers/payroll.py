
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
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

router = APIRouter(prefix="/payroll", tags=["Payroll"])

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def get_payroll_or_404(payroll_id: int, db: Session) -> Payroll:
    payroll = (
        db.query(Payroll)
        .filter(Payroll.id == payroll_id)
        .first()
    )

    if payroll is None:
        raise HTTPException(status_code=404, detail="Payroll not found")

    return payroll


def calculate_lop_for_month(
    db: Session,
    employee_id: int,
    month_start: date,
    month_end: date,
) -> int:
    # Only approved leave requests contribute to payroll LOP.
    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "Approved",
            LeaveRequest.lop_days > 0,
            LeaveRequest.start_date <= month_end,
            LeaveRequest.end_date >= month_start,
        )
        .all()
    )

    total_lop = 0

    for leave in leaves:
        days = int(leave.lop_days or 0)

        if days <= 0:
            continue

        # The leave workflow consumes paid leave first.
        # Therefore, LOP days are treated as the last days of the request.
        lop_start = leave.end_date - timedelta(days=days - 1)

        overlap_start = max(lop_start, month_start)
        overlap_end = min(leave.end_date, month_end)

        if overlap_start <= overlap_end:
            total_lop += (overlap_end - overlap_start).days + 1

    return total_lop


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
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

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
            status_code=409,
            detail="Payroll already exists for this employee and month",
        )

    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])

    attendance_count = (
        db.query(func.count(Attendance.id))
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date >= month_start,
            Attendance.attendance_date <= month_end,
        )
        .scalar()
        or 0
    )

    lop_days = calculate_lop_for_month(
        db,
        employee_id,
        month_start,
        month_end,
    )

    monthly_salary = money(Decimal(str(employee.salary)))

    # Demo policy: fixed monthly salary and a 30-day LOP basis.
    gross_salary = monthly_salary

    lop_deduction = money(
        monthly_salary * Decimal(lop_days) / Decimal("30")
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
        status="Generated",
        is_locked=False,
        generated_by=current_user.id,
    )

    db.add(payroll)

    try:
        db.commit()
        db.refresh(payroll)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Payroll already exists for this employee and month",
        )

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
            status_code=404,
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

    return query.order_by(
        Payroll.year.desc(),
        Payroll.month.desc(),
        Payroll.employee_id,
    ).all()


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
            raise HTTPException(status_code=404, detail="Payroll not found")

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
            status_code=409,
            detail="Payroll is already locked",
        )

    payroll.is_locked = True
    payroll.status = "Locked"
    payroll.locked_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(payroll)

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
            status_code=409,
            detail="Lock payroll before simulating salary credit",
        )

    if payroll.status == "Paid":
        raise HTTPException(
            status_code=409,
            detail="Salary credit has already been simulated",
        )

    # Simulation only: no bank transfer or payment gateway is used.
    payroll.status = "Paid"
    payroll.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(payroll)

    return payroll
