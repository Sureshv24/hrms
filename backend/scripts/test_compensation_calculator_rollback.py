from datetime import date
from calendar import monthrange
from decimal import Decimal

from app.db.database import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.models.compensation import (
    CompensationStructure,
    CompensationComponent,
)
from app.services.compensation_payroll import (
    calculate_compensation_for_period,
)


db = SessionLocal()

try:
    # Start a transaction that is explicitly rolled back in finally.
    db.begin()

    employee = (
        db.query(Employee)
        .filter(Employee.id == 3, Employee.is_active.is_(True))
        .first()
    )
    admin = db.query(User).filter(User.role == "Admin").first()

    if employee is None:
        raise RuntimeError("Active test employee EMP003 was not found.")
    if admin is None:
        raise RuntimeError("Admin account was not found.")

    year = date.today().year + 1
    start = date(year, 1, 1)
    end = date(year, 1, monthrange(year, 1)[1])

    if employee.joining_date > end:
        raise RuntimeError(
            "EMP003 joins after the test period; no test was run."
        )

    structure = CompensationStructure(
        employee_id=employee.id,
        structure_name=f"TEST ONLY ROLLBACK {year}-01",
        effective_from=start,
        effective_to=None,
        basic_salary=Decimal("30000.00"),
        currency="INR",
        notes="Temporary calculator test; transaction will roll back.",
        created_by=admin.id,
    )
    db.add(structure)
    db.flush()

    test_components = [
        ("HRA", "Earning", "PercentOfBasic", "40.00", True, True),
        ("Transport", "Earning", "Fixed", "2000.00", False, True),
        ("Performance Bonus", "Earning", "Fixed", "5000.00", True, False),
        ("PF", "Deduction", "PercentOfBasic", "12.00", False, True),
        ("Overtime Rate", "Earning", "PerOvertimeHour", "250.00", False, True),
    ]

    for name, kind, method, amount, taxable, recurring in test_components:
        db.add(
            CompensationComponent(
                structure_id=structure.id,
                component_name=name,
                component_type=kind,
                calculation_method=method,
                amount=Decimal(amount),
                is_taxable=taxable,
                is_recurring=recurring,
            )
        )

    db.flush()

    result = calculate_compensation_for_period(
        db=db,
        employee=employee,
        year=year,
        month=1,
        as_of_date=end,
        lop_days=0,
    )

    if result is None:
        raise AssertionError("Calculator did not find the test structure.")

    print("===== TEMPORARY CALCULATION RESULT =====")
    print("Test period:", f"{year}-01")
    print("Monthly salary rate:", result["monthly_salary"])
    print("Gross earnings:", result["gross_salary"])
    print("LOP deduction:", result["lop_deduction"])
    print("Compensation deductions:", result["compensation_deductions"])
    print("Estimated net:", result["net_salary"])
    print("Breakdown items:", len(result["compensation_breakdown"]))
    for item in result["compensation_breakdown"]:
        print(
            item["component_name"],
            item["component_type"],
            item["period_amount"],
        )

    # With a full January of employment and no future attendance:
    # recurring gross rate = 30,000 + 12,000 + 2,000 = 44,000
    # gross including one-time bonus = 49,000
    # PF = 3,600; net = 45,400.
    assert result["monthly_salary"] == Decimal("44000.00"), (
        f"Unexpected monthly rate: {result['monthly_salary']}"
    )
    assert result["gross_salary"] == Decimal("49000.00"), (
        f"Unexpected gross: {result['gross_salary']}"
    )
    assert result["compensation_deductions"] == Decimal("3600.00"), (
        f"Unexpected deductions: {result['compensation_deductions']}"
    )
    assert result["net_salary"] == Decimal("45400.00"), (
        f"Unexpected net: {result['net_salary']}"
    )

    print("PASS: Sample calculations match expected values.")

finally:
    db.rollback()
    db.close()
    print("ROLLBACK: Temporary test records were not committed.")
