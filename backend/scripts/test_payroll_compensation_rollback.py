from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import or_

from app.db.database import engine
from app.models.user import User
from app.models.employee import Employee
from app.models.payroll import Payroll
from app.models.compensation import CompensationStructure, CompensationComponent
from app.routers import payroll as payroll_router
from app.routers.payroll import PayrollAdjustmentRequest


EMPLOYEE_ID = 1
YEAR = 2026
MONTH = 8
START = date(2026, 8, 1)
END = date(2026, 8, 31)

connection = engine.connect()
outer_transaction = connection.begin()
db = None

try:
    from sqlalchemy.orm import Session

    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    employee = (
        db.query(Employee)
        .filter(
            Employee.id == EMPLOYEE_ID,
            Employee.is_active.is_(True),
        )
        .first()
    )
    admin = db.query(User).filter(User.role == "Admin").first()

    if employee is None or admin is None:
        raise RuntimeError("Test employee or Admin user not found.")

    if employee.joining_date > START:
        raise RuntimeError("Employee had not joined by the test period.")

    if db.query(Payroll.id).filter(
        Payroll.employee_id == EMPLOYEE_ID,
        Payroll.year == YEAR,
        Payroll.month == MONTH,
    ).first():
        raise RuntimeError("Payroll now exists for EMP001 in August 2026.")

    overlap = db.query(CompensationStructure.id).filter(
        CompensationStructure.employee_id == EMPLOYEE_ID,
        CompensationStructure.effective_from <= END,
        or_(
            CompensationStructure.effective_to.is_(None),
            CompensationStructure.effective_to >= START,
        ),
    ).first()

    if overlap:
        raise RuntimeError("A compensation structure now overlaps the test period.")

    suffix = uuid4().hex[:8]

    structure = CompensationStructure(
        employee_id=EMPLOYEE_ID,
        structure_name=f"ROLLBACK TEST AUG 2026 {suffix}",
        effective_from=START,
        effective_to=END,
        basic_salary=Decimal("30000.00"),
        currency="INR",
        notes="Temporary integration test. Rollback only.",
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

    # Disable external notifications for this rollback-only test.
    payroll_router.notify_payroll_owner_safely = lambda db, payroll: None

    generated = payroll_router.generate_payroll(
        employee_id=EMPLOYEE_ID,
        month=MONTH,
        year=YEAR,
        db=db,
        current_user=admin,
    )

    if generated.compensation_structure_id != structure.id:
        raise AssertionError("Generated payroll did not retain the test structure ID.")

    if not generated.compensation_breakdown:
        raise AssertionError("Generated payroll has no component breakdown.")

    if Decimal(str(generated.compensation_deductions)) <= 0:
        raise AssertionError("Expected a positive compensation deduction.")

    original_net = Decimal(str(generated.net_salary))

    print("===== GENERATION =====")
    print("Payroll ID (temporary):", generated.id)
    print("Period:", f"{YEAR}-{MONTH:02d}")
    print("Gross:", generated.gross_salary)
    print("LOP deduction:", generated.lop_deduction)
    print("Compensation deductions:", generated.compensation_deductions)
    print("Net:", generated.net_salary)
    print("Components:", [
        item["component_name"]
        for item in generated.compensation_breakdown
    ])

    adjusted = payroll_router.adjust_payroll(
        payroll_id=generated.id,
        data=PayrollAdjustmentRequest(
            adjustment_amount=Decimal("100.00"),
            reason="Rollback-only compensation regression test",
        ),
        db=db,
        current_user=admin,
    )

    if Decimal(str(adjusted.net_salary)) != original_net + Decimal("100.00"):
        raise AssertionError("Manual adjustment total is incorrect.")

    print("PASS: Manual adjustment retains compensation deductions.")

    locked = payroll_router.lock_payroll(
        payroll_id=generated.id,
        db=db,
        current_user=admin,
    )

    gross = Decimal(str(locked.gross_salary))
    lop = Decimal(str(locked.lop_deduction))
    deductions = Decimal(str(locked.compensation_deductions or 0))
    adjustment = Decimal(str(locked.manual_adjustment_amount or 0))
    net = Decimal(str(locked.net_salary))

    expected_net = (gross - lop - deductions + adjustment).quantize(
        Decimal("0.01")
    )

    print("===== LOCK =====")
    print("Status:", locked.status)
    print("Gross:", gross)
    print("LOP deduction:", lop)
    print("Compensation deductions:", deductions)
    print("Manual adjustment:", adjustment)
    print("Net:", net)

    if locked.status != "Locked":
        raise AssertionError(f"Unexpected final status: {locked.status}")

    if net != expected_net:
        raise AssertionError(f"Expected net {expected_net}; received {net}")

    if not locked.compensation_breakdown:
        raise AssertionError("Lock operation lost the compensation snapshot.")

    print("PASS: Generation, adjustment, and lock totals reconcile.")

finally:
    if db is not None:
        db.close()

    outer_transaction.rollback()
    connection.close()
    print("ROLLBACK: Temporary payroll, structure, components, and audit changes rolled back.")
