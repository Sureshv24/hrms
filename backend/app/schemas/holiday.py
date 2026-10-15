from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HolidayType = Literal["Company", "Regional", "Optional"]


class HolidayCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    holiday_date: date
    holiday_type: HolidayType
    region: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class HolidayUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    holiday_date: date | None = None
    holiday_type: HolidayType | None = None
    region: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class HolidayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    holiday_date: date
    holiday_type: str
    region: str | None
    description: str | None
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime


class HolidayCalendarItem(HolidayResponse):
    is_selected: bool = False


class EmployeeHolidaySelectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    holiday_id: int
    employee_id: int
    selected_at: datetime
