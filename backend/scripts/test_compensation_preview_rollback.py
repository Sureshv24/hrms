from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import User
from app.models.employee import Employee
from app.models.compensation import CompensationStructure
from app.schemas.compensation import (
    CompensationStructureCreate,
    CompensationComponentCreate,
)
from app.routers import compensation as compensation_router


START = date(2095, 1, 1)
END = date(2095, 1, 31)
test_name = f"ROLLBACK PREVIEW TEST {uuid4().hex[:10]}"

connection = engine.connect()
outer_transaction = connection.begin()
db = Session(bind=connection, join_transaction_mode="create_savepoint")

try:
    admin = (
        db.query(User)
        .filter(User.role == "Admin", User.is_active.is_(True))
        .first()
    )
    if admin is None:
        raise RuntimeError("No active Admin user found.")

    # Pick an employee whose compensation dates do not overlap
    # this test's temporary 2095 period.
    employee = None
    for candidate in (
        db.query(Employee)
        .filter(Employee.is_active.is_(True))
        .order_by(Employee.id.asc())
        .all()
    ):
        overlap = (
            db.query(CompensationStructure.id)
            .filter(
                CompensationStructure.employee_id == candidate.id,
                CompensationStructure.effective_from <= END,
                or_(
                    CompensationStructure.effective_to.is_(None),
                    CompensationStructure.effective_to >= START,
                ),
            )
            .first()
        )
        if overlap is None:
            employee = candidate
            break

    if employee is None:
        raise RuntimeError(
            "No active employee is available for the temporary test period."
        )

    print("===== COMPENSATION PREVIEW ROLLBACK TEST =====")
    print(f"Temporary structure: {test_name}")
    print(f"Employee: {employee.employee_code}, ID {employee.id}")
    print(f"Period: {START} to {END}")

    # Create through the actual route function. Its commit uses a
    # savepoint, while the surrounding transaction remains rollback-only.
    structure_payload = CompensationStructureCreate(
        employee_id=employee.id,
        structure_name=test_name,
        effective_from=START,
        effective_to=END,
        basic_salary=Decimal("30000.00"),
        currency="INR",
        notes="Temporary preview test; must be rolled back.",
        components=[
            CompensationComponentCreate(
                component_name="HRA",
                component_type="Earning",
                calculation_method="PercentOfBasic",
                amount=Decimal("40.00"),
                is_taxable=True,
                is_recurring=True,
            ),
            CompensationComponentCreate(
                component_name="Transport",
                component_type="Earning",
                calculation_method="Fixed",
                amount=Decimal("2000.00"),
                is_taxable=False,
                is_recurring=True,
            ),
            CompensationComponentCreate(
                component_name="Performance Bonus",
                component_type="Earning",
                calculation_method="Fixed",
                amount=Decimal("5000.00"),
                is_taxable=True,
                is_recurring=False,
            ),
            CompensationComponentCreate(
                component_name="PF",
                component_type="Deduction",
                calculation_method="PercentOfBasic",
                amount=Decimal("12.00"),
                is_taxable=False,
                is_recurring=True,
            ),
            CompensationComponentCreate(
                component_name="Overtime Rate",
                component_type="Earning",
                calculation_method="PerOvertimeHour",
                amount=Decimal("250.00"),
                is_taxable=False,
                is_recurring=True,
            ),
        ],
    )

    created = compensation_router.create_compensation_structure(
        payload=structure_payload,
        db=db,
        current_user=admin,
    )
    structure_id = created["id"]
    print(f"PASS: Temporary structure created via route (ID {structure_id}).")

    # Preview recurring items plus two hours of overtime.
    ordinary_preview = compensation_router.preview_compensation(
        structure_id=structure_id,
        payload=compensation_router.CompensationPreviewRequest(
            overtime_hours=Decimal("2.00"),
            include_non_recurring=False,
        ),
        db=db,
        current_user=admin,
    )

    print("\n===== RECURRING COMPONENT PREVIEW =====")
    print("Gross earnings:", ordinary_preview["gross_earnings"])
    print("Total deductions:", ordinary_preview["total_deductions"])
    print("Estimated net:", ordinary_preview["estimated_net_salary"])
    print("Preview only:", ordinary_preview["preview_only"])
    print("Payroll record created:", ordinary_preview["payroll_record_created"])

    assert ordinary_preview["preview_only"] is True
    assert ordinary_preview["payroll_record_created"] is False
    assert Decimal(str(ordinary_preview["gross_earnings"])) == Decimal("44500.00")
    assert Decimal(str(ordinary_preview["total_deductions"])) == Decimal("3600.00")
    assert Decimal(str(ordinary_preview["estimated_net_salary"])) == Decimal("40900.00")
    print("PASS: Recurring earnings, overtime and deduction totals match.")

    # Include the non-recurring bonus explicitly.
    bonus_preview = compensation_router.preview_compensation(
        structure_id=structure_id,
        payload=compensation_router.CompensationPreviewRequest(
            overtime_hours=Decimal("2.00"),
            include_non_recurring=True,
        ),
        db=db,
        current_user=admin,
    )

    print("\n===== BONUS-INCLUDED PREVIEW =====")
    print("Gross earnings:", bonus_preview["gross_earnings"])
    print("Total deductions:", bonus_preview["total_deductions"])
    print("Estimated net:", bonus_preview["estimated_net_salary"])

    assert Decimal(str(bonus_preview["gross_earnings"])) == Decimal("49500.00")
    assert Decimal(str(bonus_preview["estimated_net_salary"])) == Decimal("45900.00")
    print("PASS: Non-recurring bonus is included only when requested.")

    component_names = {
        item["component_name"] for item in ordinary_preview["components"]
    }
    assert {
        "HRA", "Transport", "Performance Bonus", "PF", "Overtime Rate"
    }.issubset(component_names)
    print("PASS: Component breakdown contains every configured component.")

    print("\nPASS: Compensation preview route checks completed.")

finally:
    db.rollback()
    if outer_transaction.is_active:
        outer_transaction.rollback()
    db.close()
    connection.close()
    print("ROLLBACK: Temporary compensation structure, components and audit changes rolled back.")

with Session(engine) as verify_db:
    leaked = (
        verify_db.query(CompensationStructure.id)
        .filter(CompensationStructure.structure_name == test_name)
        .first()
    )
    if leaked:
        raise AssertionError("Temporary compensation structure persisted.")
    print("PASS: No temporary compensation structure persisted.")