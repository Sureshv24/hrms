
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.database import Base


class Payroll(Base):
    __tablename__ = "payroll"

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "month",
            "year",
            name="uq_employee_payroll_period",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer,
        ForeignKey("employees.id"),
        nullable=False,
        index=True,
    )

    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)

    # Snapshot of the employee's monthly salary at generation time.
    monthly_salary = Column(Numeric(12, 2), nullable=False)

    present_days = Column(Integer, nullable=False, default=0)
    lop_days = Column(Integer, nullable=False, default=0)

    gross_salary = Column(Numeric(12, 2), nullable=False)
    lop_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    net_salary = Column(Numeric(12, 2), nullable=False)

    status = Column(
        String(20),
        nullable=False,
        default="Generated",
        server_default="Generated",
    )

    is_locked = Column(Boolean, nullable=False, default=False)

    generated_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    locked_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
