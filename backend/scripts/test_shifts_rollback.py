from datetime import date, time
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import User
from app.models.employee import Employee
from app.models.shift import Shift, EmployeeShiftAssignment
from app.routers import shifts as shifts_router
from app.schemas.shift import ShiftCreate, ShiftAssignmentCreate


START = date(2026, 10, 1)
END = date(2026, 10, 10)
test_name = f"ROLLBACK SHIFT TEST {uuid4().hex[:10]}"

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

    replacement_shift = (
        db.query(Shift)
        .filter(Shift.id == 1, Shift.is_active.is_(True))
        .first()
    )
    if replacement_shift is None:
        raise RuntimeError(
            "The expected active replacement shift ID 1 was not found. "
            "No permanent data has been changed."
        )

    # Find an employee with no individual assignment overlapping the
    # rollback test interval.
    employee = None
    employees = (
        db.query(Employee)
        .filter(Employee.is_active.is_(True))
        .order_by(Employee.id.asc())
        .all()
    )

    for candidate in employees:
        overlap = (
            db.query(EmployeeShiftAssignment.id)
            .filter(
                EmployeeShiftAssignment.employee_id == candidate.id,
                EmployeeShiftAssignment.effective_from <= END,
                or_(
                    EmployeeShiftAssignment.effective_to.is_(None),
                    EmployeeShiftAssignment.effective_to >= START,
                ),
            )
            .first()
        )
        if overlap is None:
            employee = candidate
            break

    if employee is None:
        raise RuntimeError(
            "No active employee is free in the test interval. "
            "No assignment has been changed."
        )

    print("===== SHIFT ROLLBACK INTEGRATION TEST =====")
    print(f"Temporary shift name: {test_name}")
    print(f"Test employee: {employee.employee_code}, ID {employee.id}")
    print(f"Replacement shift: {replacement_shift.name}, ID {replacement_shift.id}")
    print(f"Test interval: {START} to {END}")

    # 1. Create a temporary shift through the real route function.
    created_shift = shifts_router.create_shift(
        payload=ShiftCreate(
            name=test_name,
            shift_type="General",
            start_time=time(8, 0),
            end_time=time(16, 30),
            grace_period_minutes=5,
            expected_work_minutes=480,
            description="Temporary rollback-only integration test",
            is_active=True,
        ),
        db=db,
        current_user=admin,
    )
    assert created_shift.id is not None
    assert created_shift.name == test_name
    print("PASS: Shift creation route.")

    # 2. Assign it over a checked interval with no conflicting
    # individual assignment.
    assignment = shifts_router.create_shift_assignment(
        payload=ShiftAssignmentCreate(
            shift_id=created_shift.id,
            employee_id=employee.id,
            effective_from=START,
            effective_to=END,
        ),
        db=db,
        current_user=admin,
    )
    assert assignment.id is not None
    assert assignment.shift_id == created_shift.id
    assert assignment.employee_id == employee.id
    print("PASS: Employee assignment route.")

    # 3. Use the real Admin override function to replace the shift
    # on the temporary assignment. The assignment is inside this test
    # transaction and will be rolled back.
    override_payload = shifts_router.ShiftAssignmentOverrideRequest(
        shift_id=replacement_shift.id,
        effective_from=START,
        effective_to=END,
        reason="Rollback-only test of Admin shift override",
    )
    overridden = shifts_router.override_shift_assignment(
        assignment_id=assignment.id,
        payload=override_payload,
        db=db,
        current_user=admin,
    )
    assert overridden.shift_id == replacement_shift.id
    assert overridden.employee_id == employee.id
    print("PASS: Admin override route.")

    # 4. Confirm the audit-history route can read the override event.
    history = shifts_router.get_shift_assignment_history(
        assignment_id=assignment.id,
        db=db,
        current_user=admin,
    )
    print("History actions:", [entry["action"] for entry in history])

    if not any(
        entry["action"] == "shift.assignment.overridden"
        for entry in history
    ):
        raise AssertionError(
            "Expected override audit event was not returned by history API."
        )
    print("PASS: Assignment history includes the override event.")

    print("\nPASS: Shift create, assignment, override and history verified.")

finally:
    db.rollback()
    if outer_transaction.is_active:
        outer_transaction.rollback()
    db.close()
    connection.close()
    print("ROLLBACK: Temporary shift, assignment and audit changes rolled back.")

# Verify the temporary shift did not persist after transaction rollback.
with Session(engine) as verify_db:
    leaked = (
        verify_db.query(Shift.id)
        .filter(Shift.name == test_name)
        .first()
    )
    if leaked:
        raise AssertionError("Temporary test shift remained after rollback.")
    print("PASS: No temporary shift persisted after rollback.")