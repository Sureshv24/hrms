from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.database import Base


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False, unique=True)
    shift_type = Column(String(20), nullable=False)

    # Flexible shifts may omit fixed start/end times.
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    grace_period_minutes = Column(
        Integer, nullable=False, default=10
    )
    expected_work_minutes = Column(
        Integer, nullable=False, default=480
    )

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


class EmployeeShiftAssignment(Base):
    __tablename__ = "employee_shift_assignments"

    __table_args__ = (
        CheckConstraint(
            """
            (
                employee_id IS NOT NULL
                AND department IS NULL
            )
            OR
            (
                employee_id IS NULL
                AND department IS NOT NULL
            )
            """,
            name="ck_shift_assignment_target",
        ),
        CheckConstraint(
            """
            effective_to IS NULL
            OR effective_to >= effective_from
            """,
            name="ck_shift_assignment_dates",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    shift_id = Column(
        Integer,
        ForeignKey("shifts.id"),
        nullable=False,
        index=True,
    )

    # Exactly one target: employee OR department.
    employee_id = Column(
        Integer,
        ForeignKey("employees.id"),
        nullable=True,
        index=True,
    )

    department = Column(String(100), nullable=True, index=True)

    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)

    assigned_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

