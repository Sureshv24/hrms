from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.db.database import Base


class CompensationStructure(Base):
    """
    A versioned employee compensation structure.

    To preserve history, create a new structure when compensation changes
    instead of overwriting older salary details.
    """
    __tablename__ = "compensation_structures"

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_compensation_structure_dates",
        ),
        CheckConstraint(
            "basic_salary >= 0",
            name="ck_compensation_basic_nonnegative",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer,
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    )

    structure_name = Column(String(100), nullable=False)

    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)

    basic_salary = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")

    notes = Column(Text, nullable=True)

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


class CompensationComponent(Base):
    """
    Earnings or deductions belonging to one compensation version.

    Fixed: amount is a fixed monthly amount.
    PercentOfBasic: amount is a percentage of basic salary.
    PerOvertimeHour: amount is the overtime rate per hour.

    Components are tied to a versioned structure for historical accuracy.
    """
    __tablename__ = "compensation_components"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_compensation_component_amount_nonnegative",
        ),
        CheckConstraint(
            "component_type IN ('Earning', 'Deduction')",
            name="ck_compensation_component_type",
        ),
        CheckConstraint(
            "calculation_method IN "
            "('Fixed', 'PercentOfBasic', 'PerOvertimeHour')",
            name="ck_compensation_component_method",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    structure_id = Column(
        Integer,
        ForeignKey("compensation_structures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    component_name = Column(String(100), nullable=False)
    component_type = Column(String(20), nullable=False)
    calculation_method = Column(String(30), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)

    is_taxable = Column(Boolean, nullable=False, default=False)
    is_recurring = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
