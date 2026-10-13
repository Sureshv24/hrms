
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit_log(
    db: Session,
    actor,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=getattr(actor, "id", None),
        actor_name=getattr(actor, "full_name", None) or "System",
        actor_role=getattr(actor, "role", None) or "System",
        action=action,
        entity_type=entity_type,
        entity_id=(
            str(entity_id) if entity_id is not None else None
        ),
        details=details,
    )

    db.add(entry)
    return entry
