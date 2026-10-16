
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
    compensation_structure_id: int | None = None
    compensation_deductions: Decimal = Decimal("0.00")
    compensation_breakdown: list[dict] | None = None
    present_days: int
    lop_days: int

    gross_salary: Decimal
    lop_deduction: Decimal
    net_salary: Decimal

    # Manual payroll adjustment details.
    manual_adjustment_amount: Decimal
    adjustment_reason: str | None = None
    adjusted_by: int | None = None
    adjusted_at: datetime | None = None

    status: str
    is_locked: bool
    generated_by: int

    locked_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime

