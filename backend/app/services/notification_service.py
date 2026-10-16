from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationPreference


def create_in_app_notification(
    db: Session,
    recipient_user_id: int,
    title: str,
    message: str,
    category: str,
    created_by_user_id: int | None = None,
    source_entity_type: str | None = None,
    source_entity_id: int | str | None = None,
) -> Notification | None:
    """
    Add a notification to the current DB transaction.

    An explicitly disabled preference suppresses delivery.
    Missing preferences default to enabled.
    This helper does not commit; the caller controls the transaction.
    """
    preference = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == recipient_user_id,
            NotificationPreference.category == category,
        )
        .first()
    )

    if preference is not None and not preference.enabled:
        return None

    notification = Notification(
        recipient_user_id=recipient_user_id,
        title=title,
        message=message,
        category=category,
        created_by_user_id=created_by_user_id,
        source_entity_type=source_entity_type,
        source_entity_id=(
            str(source_entity_id)
            if source_entity_id is not None
            else None
        ),
    )

    db.add(notification)
    return notification
