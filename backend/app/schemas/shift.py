from datetime import date, datetime, time
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


ShiftType = Literal["General", "Night", "Flexible", "Remote"]


class ShiftCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    shift_type: ShiftType
    start_time: time | None = None
    end_time: time | None = None

    grace_period_minutes: int = Field(
        default=10, ge=0, le=240
    )
    expected_work_minutes: int = Field(
        default=480, ge=1, le=1440
    )

    description: str | None = Field(
        default=None, max_length=2000
    )
    is_active: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.shift_type != "Flexible":
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    "Fixed shifts require start_time and end_time"
                )

        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time == self.end_time
        ):
            raise ValueError(
                "Shift start and end times cannot be identical"
            )

        return self


class ShiftUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=2, max_length=100
    )
    shift_type: ShiftType | None = None
    start_time: time | None = None
    end_time: time | None = None

    grace_period_minutes: int | None = Field(
        default=None, ge=0, le=240
    )
    expected_work_minutes: int | None = Field(
        default=None, ge=1, le=1440
    )

    description: str | None = Field(
        default=None, max_length=2000
    )
    is_active: bool | None = None


class ShiftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    shift_type: str
    start_time: time | None
    end_time: time | None
    grace_period_minutes: int
    expected_work_minutes: int
    description: str | None
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime


class ShiftAssignmentCreate(BaseModel):
    shift_id: int = Field(gt=0)
    employee_id: int | None = Field(default=None, gt=0)
    department: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_assignment(self):
        has_employee = self.employee_id is not None
        has_department = (
            self.department is not None
            and bool(self.department.strip())
        )

        if has_employee == has_department:
            raise ValueError(
                "Specify exactly one of employee_id or department"
            )

        if (
            self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError(
                "effective_to cannot precede effective_from"
            )

        if self.department is not None:
            self.department = self.department.strip()

        return self


class ShiftAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_id: int
    employee_id: int | None
    department: str | None
    effective_from: date
    effective_to: date | None
    assigned_by: int
    created_at: datetime
