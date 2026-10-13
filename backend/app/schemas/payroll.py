
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PayrollResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    month: int
    year: int
    monthly_salary: Decimal
    present_days: int
    lop_days: int
    gross_salary: Decimal
    lop_deduction: Decimal
    net_salary: Decimal
    status: str
    is_locked: bool
    generated_by: int
    locked_at: datetime | None
    paid_at: datetime | None
    created_at: datetime
