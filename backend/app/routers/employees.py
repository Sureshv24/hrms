
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.employee import Employee
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
)

router = APIRouter(prefix="/employees", tags=["Employee Management"])


def get_employee_or_404(employee_id: int, db: Session) -> Employee:
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )

    return employee


# Admin/HR: create an employment record for an existing user.
@router.post(
    "/",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    user = db.query(User).filter(User.id == data.user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User account not found. Register the user first.",
        )

    if user.role != "Employee":
        raise HTTPException(
            status_code=400,
            detail="An employee record can only be linked to an Employee account",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot create an employee record for an inactive user",
        )

    if db.query(Employee).filter(
        Employee.user_id == data.user_id
    ).first():
        raise HTTPException(
            status_code=409,
            detail="This user already has an employee record",
        )

    if db.query(Employee).filter(
        Employee.employee_code == data.employee_code
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Employee code already exists",
        )

    employee = Employee(**data.model_dump())
    db.add(employee)

    try:
        db.commit()
        db.refresh(employee)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Employee code or user account already exists",
        )

    return employee


# Admin/HR: list employee records.
@router.get(
    "/",
    response_model=list[EmployeeResponse],
)
def list_employees(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    query = db.query(Employee)

    if not include_inactive:
        query = query.filter(Employee.is_active.is_(True))

    return query.order_by(Employee.id).offset(skip).limit(
        min(max(limit, 1), 100)
    ).all()


# Employee: view their own employment record.
@router.get(
    "/me",
    response_model=EmployeeResponse,
)
def get_my_employee_record(
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
            status_code=404,
            detail="Your employee record has not been created yet",
        )

    return employee


# Admin/HR: view a specific employee record.
@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    return get_employee_or_404(employee_id, db)


# Admin/HR: update employment details.
@router.patch(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    employee = get_employee_or_404(employee_id, db)

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update",
        )

    for field, value in changes.items():
        setattr(employee, field, value)

    try:
        db.commit()
        db.refresh(employee)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Unable to update employee record",
        )

    return employee


# Admin/HR: deactivate rather than permanently delete.
@router.patch(
    "/{employee_id}/deactivate",
    response_model=EmployeeResponse,
)
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin", "HR")),
):
    employee = get_employee_or_404(employee_id, db)

    if not employee.is_active:
        raise HTTPException(
            status_code=409,
            detail="Employee is already deactivated",
        )

    employee.is_active = False

    # Also disable login for this employee account.
    user = db.query(User).filter(
        User.id == employee.user_id
    ).first()

    if user:
        user.is_active = False

    db.commit()
    db.refresh(employee)

    return employee
