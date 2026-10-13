
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.db.database import Base


class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "leave_type",
            name="uq_employee_leave_type",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    employee_id = Column(
        Integer,
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    )

    # Must match the leave type strings used by the leave API.
    leave_type = Column(
        String(20),
        nullable=False,
    )

    total_days = Column(
        Integer,
        nullable=False,
        default=12,
    )

    used_days = Column(
        Integer,
        nullable=False,
        default=0,
    )
