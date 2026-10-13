
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.employee import Employee
from app.models.leave import LeaveRequest
from app.models.leave_balance import LeaveBalance
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.leave import (
    LeaveBalanceResponse,
    LeaveCreate,
    LeaveResponse,
    LeaveReviewRequest,
)

router = APIRouter(prefix="/leaves", tags=["Leave Management"])

# Example company policy. Adjust these values to match your requirements.
DEFAULT_BALANCES = {
    "Casual": 12,
    "Sick": 12,
    "Earned": 12,
    "Unpaid": 0,
}


def get_active_employee(db: Session, user_id: int) -> Employee:
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


def get_or_create_balance(
    db: Session,
    employee_id: int,
    leave_type: str,
) -> LeaveBalance:
    balance = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type == leave_type,
        )
        .with_for_update()
        .first()
    )

    if balance is None:
        balance = LeaveBalance(
            employee_id=employee_id,
            leave_type=leave_type,
            total_days=DEFAULT_BALANCES[leave_type],
            used_days=0,
        )
        db.add(balance)
        db.flush()

    return balance


def calculate_leave_days(start_date: date, end_date: date) -> int:
    # Counts calendar days, including the first and last day.
    # Weekend/holiday exclusions can be added using company policy.
    return (end_date - start_date).days + 1


@router.post(
    "/",
    response_model=LeaveResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_leave(
    data: LeaveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.end_date < data.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date",
        )

    if data.start_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Leave cannot start in the past",
        )

    employee = get_active_employee(db, current_user.id)

    overlapping = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee.id,
            LeaveRequest.status.in_(["Pending", "Approved"]),
            LeaveRequest.start_date <= data.end_date,
            LeaveRequest.end_date >= data.start_date,
        )
        .first()
    )

    if overlapping:
        raise HTTPException(
            status_code=409,
            detail="A pending or approved leave already overlaps these dates",
        )

    leave = LeaveRequest(
        employee_id=employee.id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason.strip(),
        status="Pending",
        lop_days=0,
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    return leave


@router.get("/me", response_model=list[LeaveResponse])
def my_leave_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_active_employee(db, current_user.id)

    return (
        db.query(LeaveRequest)
        .filter(LeaveRequest.employee_id == employee.id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )


@router.get(
    "/balances/me",
    response_model=list[LeaveBalanceResponse],
)
def my_leave_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_active_employee(db, current_user.id)

    # Initialize missing balance rows for this employee.
    for leave_type in DEFAULT_BALANCES:
        get_or_create_balance(db, employee.id, leave_type)

    db.commit()

    return (
        db.query(LeaveBalance)
        .filter(LeaveBalance.employee_id == employee.id)
        .order_by(LeaveBalance.leave_type)
        .all()
    )


@router.get("/", response_model=list[LeaveResponse])
def list_leave_requests(
    leave_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    query = db.query(LeaveRequest)

    if leave_status is not None:
        if leave_status not in ["Pending", "Approved", "Rejected"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid leave status",
            )

        query = query.filter(LeaveRequest.status == leave_status)

    return query.order_by(LeaveRequest.created_at.desc()).all()


@router.patch("/{leave_id}/review", response_model=LeaveResponse)
def review_leave(
    leave_id: int,
    data: LeaveReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    leave = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == leave_id)
        .with_for_update()
        .first()
    )

    if leave is None:
        raise HTTPException(
            status_code=404,
            detail="Leave request not found",
        )

    if leave.status != "Pending":
        raise HTTPException(
            status_code=409,
            detail="This leave request has already been reviewed",
        )

    leave.reviewed_by = current_user.id
    leave.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if data.action == "reject":
        leave.status = "Rejected"
        leave.lop_days = 0
    else:
        leave_days = calculate_leave_days(
            leave.start_date,
            leave.end_date,
        )

        if leave.leave_type == "Unpaid":
            leave.lop_days = leave_days
        else:
            balance = get_or_create_balance(
                db,
                leave.employee_id,
                leave.leave_type,
            )

            available_days = max(
                0,
                balance.total_days - balance.used_days,
            )

            paid_days = min(leave_days, available_days)
            balance.used_days += paid_days

            # Any approved days beyond the remaining allowance become LOP.
            leave.lop_days = leave_days - paid_days

        leave.status = "Approved"

    try:
        db.commit()
        db.refresh(leave)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process leave review",
        )

    return leave
