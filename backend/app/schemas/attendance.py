
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    attendance_date: date
    check_in: datetime
    check_out: datetime | None
    working_hours: float | None = None
    assigned_shift_id: int | None = None
    assigned_shift_name: str | None = None
    shift_type: str | None = None
    is_late: bool | None = None
    late_minutes: int | None = None
    is_early_checkout: bool | None = None
    early_checkout_minutes: int | None = None
    overtime_minutes: int | None = None

    model_config = ConfigDict(from_attributes=True)


class AttendanceMonthlySummary(BaseModel):
    month: int
    year: int
    total_days_present: int
    total_working_hours: float
