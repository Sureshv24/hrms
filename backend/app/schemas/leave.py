
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LeaveType = Literal["Casual", "Sick", "Earned", "Unpaid"]


class LeaveCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str = Field(min_length=3, max_length=1000)


class LeaveReviewRequest(BaseModel):
    action: Literal["approve", "reject"]


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    leave_type: str
    start_date: date
    end_date: date
    reason: str
    status: str
    lop_days: int
    reviewed_by: int | None
    reviewed_at: datetime | None
    created_at: datetime


class LeaveBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    leave_type: str
    total_days: int
    used_days: int
