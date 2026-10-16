from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.employee import Employee
from app.models.notification import Notification, NotificationPreference
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.notification import (
    NotificationResponse,
    NotificationPreferenceUpdate,
    NotificationPreferenceResponse,
    NotificationBroadcastRequest,
)
from app.services.notification_service import create_in_app_notification
from app.utils.audit import record_audit_log


router = APIRouter(
    prefix="/notifications",
    tags=["In-app Notifications"],
)

CATEGORIES = (
    "leave",
    "payroll",
    "attendance",
    "announcement",
    "admin",
    "system",
)


@router.get("/me/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(
            Notification.recipient_user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .count()
    )

    return {"unread_count": count}


@router.get("/me", response_model=list[NotificationResponse])
def list_my_notifications(
    unread_only: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(
        Notification.recipient_user_id == current_user.id
    )

    if unread_only:
        query = query.filter(Notification.is_read.is_(False))

    return (
        query.order_by(
            Notification.created_at.desc(),
            Notification.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.patch("/me/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(Notification)
        .filter(
            Notification.recipient_user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .all()
    )

    now = datetime.now(timezone.utc)

    for record in records:
        record.is_read = True
        record.read_at = now

    db.commit()

    return {"updated_count": len(records)}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_user_id == current_user.id,
        )
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(notification)

    return notification


@router.get(
    "/preferences",
    response_model=list[NotificationPreferenceResponse],
)
def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved = {
        preference.category: preference.enabled
        for preference in (
            db.query(NotificationPreference)
            .filter(
                NotificationPreference.user_id == current_user.id
            )
            .all()
        )
    }

    return [
        {"category": category, "enabled": saved.get(category, True)}
        for category in CATEGORIES
    ]


@router.put(
    "/preferences",
    response_model=NotificationPreferenceResponse,
)
def update_notification_preference(
    payload: NotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preference = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == current_user.id,
            NotificationPreference.category == payload.category,
        )
        .first()
    )

    if preference is None:
        preference = NotificationPreference(
            user_id=current_user.id,
            category=payload.category,
            enabled=payload.enabled,
        )
        db.add(preference)
    else:
        preference.enabled = payload.enabled

    db.commit()
    db.refresh(preference)

    return {
        "category": preference.category,
        "enabled": preference.enabled,
    }


@router.post(
    "/broadcast",
    status_code=status.HTTP_201_CREATED,
)
def broadcast_notification(
    payload: NotificationBroadcastRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    department = (
        payload.department.strip()
        if payload.department is not None
        else None
    )

    if payload.department is not None and not department:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Department cannot be blank",
        )

    if department:
        user_rows = (
            db.query(User.id)
            .join(Employee, Employee.user_id == User.id)
            .filter(
                User.is_active.is_(True),
                Employee.is_active.is_(True),
                func.lower(func.trim(Employee.department))
                == department.lower(),
            )
            .distinct()
            .all()
        )
    else:
        user_rows = (
            db.query(User.id)
            .filter(User.is_active.is_(True))
            .all()
        )

    recipient_ids = [row[0] for row in user_rows]
    created_count = 0

    try:
        for recipient_id in recipient_ids:
            notification = create_in_app_notification(
                db=db,
                recipient_user_id=recipient_id,
                title=payload.title,
                message=payload.message,
                category=payload.category,
                created_by_user_id=current_user.id,
                source_entity_type="announcement",
            )

            if notification is not None:
                created_count += 1

        record_audit_log(
            db=db,
            actor=current_user,
            action="notification.broadcast",
            entity_type="notification_broadcast",
            details={
                "title": payload.title,
                "category": payload.category,
                "department": department,
                "eligible_users": len(recipient_ids),
                "notifications_created": created_count,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "message": "Broadcast processed successfully",
        "department": department,
        "eligible_users": len(recipient_ids),
        "notifications_created": created_count,
        "suppressed_by_preferences": len(recipient_ids) - created_count,
    }
