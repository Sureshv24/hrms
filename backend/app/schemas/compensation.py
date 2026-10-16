from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


ComponentType = Literal["Earning", "Deduction"]

CalculationMethod = Literal[
    "Fixed",
    "PercentOfBasic",
    "PerOvertimeHour",
]


class CompensationComponentCreate(BaseModel):
    component_name: str = Field(min_length=2, max_length=100)
    component_type: ComponentType
    calculation_method: CalculationMethod
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    is_taxable: bool = False
    is_recurring: bool = True

    @field_validator("component_name")
    @classmethod
    def validate_component_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Component name must contain at least two characters")
        return value


class CompensationStructureCreate(BaseModel):
    employee_id: int = Field(gt=0)
    structure_name: str = Field(min_length=2, max_length=100)

    effective_from: date
    effective_to: date | None = None

    basic_salary: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")

    notes: str | None = Field(default=None, max_length=2000)

    components: list[CompensationComponentCreate] = Field(
        default_factory=list,
        max_length=100,
    )

    @field_validator("structure_name")
    @classmethod
    def validate_structure_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Structure name must contain at least two characters")
        return value

    @model_validator(mode="after")
    def validate_structure(self):
        if (
            self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError(
                "effective_to cannot precede effective_from"
            )

        names = [item.component_name.casefold() for item in self.components]
        if len(names) != len(set(names)):
            raise ValueError(
                "Component names must be unique within a structure"
            )

        return self


class CompensationComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    structure_id: int
    component_name: str
    component_type: str
    calculation_method: str
    amount: Decimal
    is_taxable: bool
    is_recurring: bool
    created_at: datetime


class CompensationStructureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    structure_name: str
    effective_from: date
    effective_to: date | None
    basic_salary: Decimal
    currency: str
    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class CompensationStructureDetailResponse(CompensationStructureResponse):
    components: list[CompensationComponentResponse] = Field(
        default_factory=list
    )
