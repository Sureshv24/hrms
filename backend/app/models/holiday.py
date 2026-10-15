from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.database import Base


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    holiday_date = Column(Date, nullable=False, index=True)

    # Company, Regional, or Optional
    holiday_type = Column(String(20), nullable=False, index=True)

    # Required for regional holidays; optional for other types.
    region = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class EmployeeHolidaySelection(Base):
    __tablename__ = "employee_holiday_selections"

    __table_args__ = (
        UniqueConstraint(
            "holiday_id",
            "employee_id",
            name="uq_employee_holiday_selection",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    holiday_id = Column(
        Integer,
        ForeignKey("holidays.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    employee_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    selected_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
