
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    attendance_date: date
    check_in: datetime
    check_out: datetime | None
    working_hours: float | None = None

    model_config = ConfigDict(from_attributes=True)


class AttendanceMonthlySummary(BaseModel):
    month: int
    year: int
    total_days_present: int
    total_working_hours: float
