
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)

from app.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Store snapshots so the history remains useful if user details change.
    actor_name = Column(String(150), nullable=False)
    actor_role = Column(String(30), nullable=False)

    # Examples: employee.created, employee.updated, leave.approved.
    action = Column(String(100), nullable=False, index=True)

    # Examples: employee, leave, payroll.
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(50), nullable=True, index=True)

    details = Column(JSON, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        index=True,
    )
