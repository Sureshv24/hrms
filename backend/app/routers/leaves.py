import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
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
from app.services.email_service import (
    send_leave_notification_email,
)
from app.services.notification_service import create_in_app_notification
from app.utils.audit import record_audit_log


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/leaves",
    tags=["Leave Management"],
)


def _notify_leave_owner_in_app_safely(
    db, recipient, leave, title: str, message: str,
    created_by_user_id: int | None = None,
) -> None:
    if recipient is None:
        return
    try:
        notification = create_in_app_notification(
            db=db,
            recipient_user_id=recipient.id,
            title=title,
            message=message,
            category="leave",
            created_by_user_id=created_by_user_id,
            source_entity_type="leave",
            source_entity_id=leave.id,
        )
        if notification is not None:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to create in-app notification for leave_id=%s",
            leave.id,
        )


# Example company policy. Adjust these values as needed.
DEFAULT_BALANCES = {
    "Casual": 12,
    "Sick": 12,
    "Earned": 12,
    "Unpaid": 0,
}


def get_active_employee(
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

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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


def calculate_leave_days(
    start_date: date,
    end_date: date,
) -> int:
    # Counts calendar days, including both the first and last day.
    # Weekend and holiday exclusions depend on company policy.
    return (end_date - start_date).days + 1


def notify_leave_owner_safely(
    db: Session,
    recipient: User,
    leave: LeaveRequest,
) -> None:
    """
    Notify the employee after the leave transaction is committed.

    Email delivery failure must not undo an already-saved leave
    application, approval, rejection, or leave balance update.
    """

    if not recipient.email:
        logger.warning(
            "Leave notification skipped: recipient email missing "
            "for leave_id=%s",
            leave.id,
        )
        return

    try:
        email_status = send_leave_notification_email(
            db=db,
            recipient_email=recipient.email,
            employee_name=recipient.full_name,
            leave_type=leave.leave_type,
            start_date=leave.start_date,
            end_date=leave.end_date,
            leave_status=leave.status,
            leave_id=leave.id,
        )

        if email_status != "sent":
            logger.warning(
                "Leave notification status=%s for leave_id=%s",
                email_status,
                leave.id,
            )

    except Exception:
        logger.exception(
            "Unable to process leave notification for leave_id=%s",
            leave.id,
        )


def get_leave_owner(
    db: Session,
    employee_id: int,
) -> User | None:
    """Find the user account linked to a leave request's employee."""

    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        return None

    return (
        db.query(User)
        .filter(User.id == employee.user_id)
        .first()
    )


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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date cannot be before start date",
        )

    if data.start_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave cannot start in the past",
        )

    employee = get_active_employee(
        db,
        current_user.id,
    )

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
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A pending or approved leave already overlaps "
                "these dates"
            ),
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

    try:
        db.add(leave)
        db.flush()

        # Record leave application in the same transaction.
        record_audit_log(
            db=db,
            actor=current_user,
            action="leave.applied",
            entity_type="leave",
            entity_id=leave.id,
            details={
                "employee_id": employee.id,
                "leave_type": leave.leave_type,
                "start_date": leave.start_date.isoformat(),
                "end_date": leave.end_date.isoformat(),
                "status": "Pending",
            },
        )

        # Save leave request and audit entry atomically.
        db.commit()
        db.refresh(leave)

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to submit leave request",
        ) from exc

    # Send application confirmation only after the leave has
    # been successfully saved.
    notify_leave_owner_safely(
        db=db,
        recipient=current_user,
        leave=leave,
    )

    _notify_leave_owner_in_app_safely(
        db=db,
        recipient=current_user,
        leave=leave,
        title="Leave application submitted",
        message=(
            f"Your {leave.leave_type} leave request from "
            f"{leave.start_date.isoformat()} to "
            f"{leave.end_date.isoformat()} was submitted and is pending review."
        ),
        created_by_user_id=current_user.id,
    )

    return leave


@router.get(
    "/me",
    response_model=list[LeaveResponse],
)
def my_leave_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = get_active_employee(
        db,
        current_user.id,
    )

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
    employee = get_active_employee(
        db,
        current_user.id,
    )

    # Initialize missing balance rows for this employee.
    for leave_type in DEFAULT_BALANCES:
        get_or_create_balance(
            db,
            employee.id,
            leave_type,
        )

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve leave balances",
        ) from exc

    return (
        db.query(LeaveBalance)
        .filter(LeaveBalance.employee_id == employee.id)
        .order_by(LeaveBalance.leave_type)
        .all()
    )


@router.get(
    "/",
    response_model=list[LeaveResponse],
)
def list_leave_requests(
    leave_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    query = db.query(LeaveRequest)

    if leave_status is not None:
        if leave_status not in [
            "Pending",
            "Approved",
            "Rejected",
        ]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid leave status",
            )

        query = query.filter(
            LeaveRequest.status == leave_status
        )

    return query.order_by(
        LeaveRequest.created_at.desc()
    ).all()


@router.patch(
    "/{leave_id}/review",
    response_model=LeaveResponse,
)
def review_leave(
    leave_id: int,
    data: LeaveReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    leave = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == leave_id)
        .with_for_update()
        .first()
    )

    if leave is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found",
        )

    if leave.status != "Pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This leave request has already been reviewed",
        )

    if data.action not in ["approve", "reject"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be approve or reject",
        )

    # Find the employee's account before making the decision.
    # The notification will be sent only after commit succeeds.
    leave_owner = get_leave_owner(
        db=db,
        employee_id=leave.employee_id,
    )

    leave.reviewed_by = current_user.id
    leave.reviewed_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
    )

    try:
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

                paid_days = min(
                    leave_days,
                    available_days,
                )

                balance.used_days += paid_days

                # Approved leave above the available paid balance
                # becomes Loss of Pay.
                leave.lop_days = leave_days - paid_days

            leave.status = "Approved"

        # Preserve the existing audit workflow.
        record_audit_log(
            db=db,
            actor=current_user,
            action=(
                "leave.approved"
                if data.action == "approve"
                else "leave.rejected"
            ),
            entity_type="leave",
            entity_id=leave.id,
            details={
                "employee_id": leave.employee_id,
                "leave_type": leave.leave_type,
                "start_date": leave.start_date.isoformat(),
                "end_date": leave.end_date.isoformat(),
                "status": leave.status,
                "lop_days": leave.lop_days,
            },
        )

        # Leave decision, balance updates, and audit log are
        # committed together.
        db.commit()
        db.refresh(leave)

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process leave review",
        ) from exc

    # Notify the employee about the final decision.
    # Notification failures must not undo the decision.
    if leave_owner is not None:
        notify_leave_owner_safely(
            db=db,
            recipient=leave_owner,
            leave=leave,
        )
        _notify_leave_owner_in_app_safely(
            db=db,
            recipient=leave_owner,
            leave=leave,
            title=f"Leave request {leave.status.lower()}",
            message=(
                f"Your {leave.leave_type} leave request from "
                f"{leave.start_date.isoformat()} to "
                f"{leave.end_date.isoformat()} is now {leave.status}."
            ),
            created_by_user_id=current_user.id,
        )
    else:
        logger.warning(
            "Leave decision saved but employee account was not "
            "found for leave_id=%s",
            leave.id,
        )

    return leave