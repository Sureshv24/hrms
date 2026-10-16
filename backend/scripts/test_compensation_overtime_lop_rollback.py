from calendar import monthrange
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.database import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.shift import Shift, EmployeeShiftAssignment
from app.models.compensation import CompensationStructure, CompensationComponent
from app.services.compensation_payroll import calculate_compensation_for_period


db = SessionLocal()

try:
    db.begin()

    employee = (
        db.query(Employee)
        .filter(Employee.id == 3, Employee.is_active.is_(True))
        .first()
    )
    admin = db.query(User).filter(User.role == "Admin").first()

    if employee is None or admin is None:
        raise RuntimeError("Test employee or admin account not found.")

    year = date.today().year + 1
    start = date(year, 1, 1)
    end = date(year, 1, monthrange(year, 1)[1])

    if employee.joining_date > end:
        raise RuntimeError("Employee joins after the test period.")

    existing_structure = (
        db.query(CompensationStructure)
        .filter(
            CompensationStructure.employee_id == employee.id,
            CompensationStructure.effective_from <= end,
            (CompensationStructure.effective_to.is_(None))
            | (CompensationStructure.effective_to >= start),
        )
        .first()
    )

    if existing_structure is not None:
        raise RuntimeError(
            "An existing structure overlaps the test period. "
            "No temporary test records were created."
        )

    used_dates = {
        row[0]
        for row in db.query(Attendance.attendance_date)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date >= start,
            Attendance.attendance_date <= end,
        )
        .all()
    }
    test_date = next(
        (date(year, 1, day) for day in range(1, end.day + 1)
         if date(year, 1, day) not in used_dates),
        None,
    )

    if test_date is None:
        raise RuntimeError("No free attendance date found in test month.")

    suffix = uuid4().hex[:8]

    structure = CompensationStructure(
        employee_id=employee.id,
        structure_name=f"ROLLBACK OT TEST {suffix}",
        effective_from=start,
        effective_to=None,
        basic_salary=Decimal("30000.00"),
        currency="INR",
        notes="Temporary rollback-only validation.",
        created_by=admin.id,
    )
    db.add(structure)
    db.flush()

    components = [
        ("HRA", "Earning", "PercentOfBasic", "40.00", True, True),
        ("Transport", "Earning", "Fixed", "2000.00", False, True),
        ("Performance Bonus", "Earning", "Fixed", "5000.00", True, False),
        ("PF", "Deduction", "PercentOfBasic", "12.00", False, True),
        ("Overtime Rate", "Earning", "PerOvertimeHour", "250.00", False, True),
    ]

    for name, kind, method, amount, taxable, recurring in components:
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

    shift = Shift(
        name=f"ROLLBACK OT TEST {suffix}",
        shift_type="General",
        start_time=time(9, 0),
        end_time=time(18, 0),
        grace_period_minutes=10,
        expected_work_minutes=480,
        description="Temporary test shift; transaction rolled back.",
        is_active=True,
        created_by=admin.id,
    )
    db.add(shift)
    db.flush()

    db.add(
        EmployeeShiftAssignment(
            shift_id=shift.id,
            employee_id=employee.id,
            department=None,
            effective_from=test_date,
            effective_to=test_date,
            assigned_by=admin.id,
        )
    )

    # India 09:00 = UTC 03:30; India 19:00 = UTC 13:30.
    check_in_utc = datetime.combine(
        test_date, time(3, 30), tzinfo=timezone.utc
    )
    check_out_utc = datetime.combine(
        test_date, time(13, 30), tzinfo=timezone.utc
    )

    db.add(
        Attendance(
            employee_id=employee.id,
            attendance_date=test_date,
            check_in=check_in_utc,
            check_out=check_out_utc,
        )
    )
    db.flush()

    result = calculate_compensation_for_period(
        db=db,
        employee=employee,
        year=year,
        month=1,
        as_of_date=end,
        lop_days=2,
    )

    print("===== OVERTIME + LOP TEST =====")
    print("Test date:", test_date)
    print("Monthly salary rate:", result["monthly_salary"])
    print("Overtime minutes:", result["overtime_minutes"])
    print("Gross earnings:", result["gross_salary"])
    print("LOP deduction:", result["lop_deduction"])
    print("Compensation deductions:", result["compensation_deductions"])
    print("Estimated net:", result["net_salary"])

    assert result["overtime_minutes"] == 60, (
        f"Expected 60 overtime minutes, got {result['overtime_minutes']}"
    )
    assert result["gross_salary"] == Decimal("49250.00"), (
        f"Unexpected gross: {result['gross_salary']}"
    )
    assert result["lop_deduction"] == Decimal("2933.33"), (
        f"Unexpected LOP: {result['lop_deduction']}"
    )
    assert result["compensation_deductions"] == Decimal("3600.00"), (
        f"Unexpected deductions: {result['compensation_deductions']}"
    )
    assert result["net_salary"] == Decimal("42716.67"), (
        f"Unexpected net: {result['net_salary']}"
    )

    print("PASS: Overtime and LOP calculations match expected values.")

finally:
    db.rollback()
    db.close()
    print("ROLLBACK: All temporary test data was rolled back.")
