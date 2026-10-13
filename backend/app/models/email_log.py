from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.db.database import Base


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    recipient_email = Column(
        String(255),
        nullable=False,
        index=True,
    )

    subject = Column(
        String(255),
        nullable=False,
    )

    template_name = Column(
        String(100),
        nullable=False,
    )

    status = Column(
        String(20),
        nullable=False,
        index=True,
    )

    related_entity_type = Column(
        String(50),
        nullable=True,
        index=True,
    )

    related_entity_id = Column(
        String(50),
        nullable=True,
    )

    error_message = Column(
        Text,
        nullable=True,
    )

    sent_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )