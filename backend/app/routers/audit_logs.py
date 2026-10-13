
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogResponse


router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"],
)


@router.get(
    "/",
    response_model=list[AuditLogResponse],
)
def list_audit_logs(
    actor_user_id: int | None = Query(
        default=None,
        ge=1,
    ),
    actor_name: str | None = Query(
        default=None,
        min_length=1,
        max_length=150,
    ),
    action: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
    ),
    entity_type: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    entity_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
    ),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    """
    Read-only audit log API.

    Access: Admin and HR.
    Filters: user ID, actor name, action, entity type,
    entity ID, and date range.
    Pagination: skip and limit.
    """

    # Validate date range.
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date",
        )

    query = db.query(AuditLog)

    # Filter by the user's ID.
    if actor_user_id is not None:
        query = query.filter(
            AuditLog.actor_user_id == actor_user_id
        )

    # Search actor names without requiring an exact match.
    if actor_name is not None:
        actor_name = actor_name.strip()

        if actor_name:
            query = query.filter(
                AuditLog.actor_name.ilike(
                    f"%{actor_name}%"
                )
            )

    # Filter by exact audit action.
    if action is not None:
        action = action.strip()

        if action:
            query = query.filter(
                AuditLog.action == action
            )

    # Filter by entity type, e.g. employee, leave, payroll.
    if entity_type is not None:
        entity_type = entity_type.strip().lower()

        if entity_type:
            query = query.filter(
                AuditLog.entity_type == entity_type
            )

    # Entity IDs are stored as strings in the audit table.
    if entity_id is not None:
        entity_id = entity_id.strip()

        if entity_id:
            query = query.filter(
                AuditLog.entity_id == entity_id
            )

    # Include the complete starting date.
    if start_date is not None:
        start_datetime = datetime.combine(
            start_date,
            time.min,
        )

        query = query.filter(
            AuditLog.created_at >= start_datetime
        )

    # Include the complete ending date using an exclusive
    # upper bound at midnight on the following day.
    if end_date is not None:
        end_datetime = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
        )

        query = query.filter(
            AuditLog.created_at < end_datetime
        )

    # Return newest audit events first.
    return (
        query
        .order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
