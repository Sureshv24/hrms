
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.sql import func

from app.db.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )

    employee_code = Column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )

    department = Column(String(100), nullable=False)
    region = Column(String(100), nullable=True, index=True)
    designation = Column(String(100), nullable=False)
    joining_date = Column(Date, nullable=False)
    salary = Column(Numeric(12, 2), nullable=False)

    phone = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

