from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.sql import func

from app.db.database import Base


class EmployeeDocument(Base):
    __tablename__ = "employee_documents"

    __table_args__ = (
        Index(
            "ix_employee_documents_employee_created",
            "employee_id",
            "created_at",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    employee_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Original sanitized filename, shown to authorized users.
    original_filename = Column(
        String(255),
        nullable=False,
    )

    # Randomly generated storage name; never accept this from clients.
    stored_filename = Column(
        String(100),
        unique=True,
        nullable=False,
    )

    content_type = Column(
        String(100),
        nullable=False,
    )

    size_bytes = Column(
        Integer,
        nullable=False,
    )

    uploaded_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )