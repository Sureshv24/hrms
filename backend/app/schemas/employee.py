
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class EmployeeCreate(BaseModel):
    user_id: int = Field(gt=0)
    employee_code: str = Field(min_length=2, max_length=20)
    department: str = Field(min_length=2, max_length=100)
    designation: str = Field(min_length=2, max_length=100)
    joining_date: date
    salary: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)


class EmployeeUpdate(BaseModel):
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    joining_date: date | None = None
    salary: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    employee_code: str
    department: str
    designation: str
    joining_date: date
    salary: Decimal
    phone: str | None
    address: str | None
    is_active: bool
    created_at: datetime
