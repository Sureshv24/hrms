from datetime import date
from decimal import Decimal
from pydantic import ValidationError

from app.schemas.compensation import CompensationStructureCreate


base = {
    "employee_id": 3,
    "structure_name": "Validation Test Only",
    "effective_from": "2026-11-01",
    "effective_to": "2026-11-30",
    "basic_salary": "30000.00",
    "currency": "INR",
    "components": [
        {
            "component_name": "HRA",
            "component_type": "Earning",
            "calculation_method": "PercentOfBasic",
            "amount": "40.00",
        },
        {
            "component_name": "PF",
            "component_type": "Deduction",
            "calculation_method": "PercentOfBasic",
            "amount": "12.00",
        },
    ],
}

# A valid structure should pass.
valid = CompensationStructureCreate.model_validate(base)
print("PASS: Valid structure accepted:", valid.structure_name)

# End date before start date must be rejected.
bad_dates = {
    **base,
    "effective_from": "2026-11-30",
    "effective_to": "2026-11-01",
}
try:
    CompensationStructureCreate.model_validate(bad_dates)
    raise AssertionError("Invalid date range was accepted")
except ValidationError:
    print("PASS: Invalid date range rejected")

# Duplicate component names must be rejected case-insensitively.
duplicate_components = {
    **base,
    "components": [
        base["components"][0],
        {
            **base["components"][1],
            "component_name": "hra",
        },
    ],
}
try:
    CompensationStructureCreate.model_validate(duplicate_components)
    raise AssertionError("Duplicate component names were accepted")
except ValidationError:
    print("PASS: Duplicate component names rejected")

# Negative component amount must be rejected.
negative_amount = {
    **base,
    "components": [
        {
            **base["components"][0],
            "amount": "-10.00",
        }
    ],
}
try:
    CompensationStructureCreate.model_validate(negative_amount)
    raise AssertionError("Negative component amount was accepted")
except ValidationError:
    print("PASS: Negative component amount rejected")

print("PASS: Schema validation tests completed.")
