from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.user import User
from app.schemas.role_management import (
    RoleInfo,
    RoleName,
    RoleUpdateRequest,
    UserRoleResponse,
)
from app.utils.audit import record_audit_log


router = APIRouter(
    prefix="/role-management",
    tags=["Role Management"],
)


ROLE_DESCRIPTIONS = {
    "Admin": (
        "Manage users, employee records, permissions, "
        "and authorized administrative operations."
    ),
    "HR": (
        "Manage employee information, leave reviews, "
        "payroll operations, and permitted reports."
    ),
    "Employee": (
        "Access personal profile, attendance, leave, "
        "and salary information."
    ),
}


# ---------------------------------------------------------
# LIST AVAILABLE ROLES — ADMIN ONLY
# ---------------------------------------------------------

@router.get(
    "/roles",
    response_model=list[RoleInfo],
)
def list_roles(
    current_user: User = Depends(
        require_roles("Admin")
    ),
):
    return [
        {
            "role": role,
            "description": description,
        }
        for role, description in ROLE_DESCRIPTIONS.items()
    ]


# ---------------------------------------------------------
# LIST USERS AND THEIR ROLES — ADMIN ONLY
# ---------------------------------------------------------

@router.get(
    "/users",
    response_model=list[UserRoleResponse],
)
def list_users_with_roles(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin")
    ),
):
    return (
        db.query(User)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# UPDATE A USER'S ROLE — ADMIN ONLY
# ---------------------------------------------------------

@router.patch(
    "/users/{user_id}/role",
    response_model=UserRoleResponse,
)
def update_user_role(
    user_id: int,
    data: RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin")
    ),
):
    target_user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    old_role = target_user.role
    new_role: RoleName = data.role

    if old_role == new_role:
        return target_user

    # An administrator must not accidentally remove
    # their own administrative access.
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You cannot change your own role. "
                "Ask another administrator to make the change."
            ),
        )

    # Do not allow the last active Admin to be demoted.
    if (
        target_user.is_active
        and old_role == "Admin"
        and new_role != "Admin"
    ):
        active_admin_count = (
            db.query(User)
            .filter(
                User.role == "Admin",
                User.is_active.is_(True),
            )
            .count()
        )

        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot demote the last active Admin. "
                    "Assign another active Admin first."
                ),
            )

    try:
        target_user.role = new_role

        record_audit_log(
            db=db,
            actor=current_user,
            action="user.role_changed",
            entity_type="user",
            entity_id=target_user.id,
            details={
                "target_user_id": target_user.id,
                "previous_role": old_role,
                "new_role": new_role,
            },
        )

        # The role change and audit entry are committed together.
        db.commit()
        db.refresh(target_user)

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update user role",
        ) from exc

    return target_user