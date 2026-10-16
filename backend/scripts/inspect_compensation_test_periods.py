from calendar import monthrange
from datetime import date

from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.payroll import Payroll
from app.models.compensation import CompensationStructure

db = SessionLocal()

try:
    employee = db.query(Employee).filter(Employee.id == 3).first()

    if employee is None:
        raise RuntimeError("EMP003 not found.")

    print("Employee:", employee.employee_code)
    print("Joining date:", employee.joining_date)
    print("\n===== RECENT COMPLETED MONTHS =====")

    today = date.today()

    for offset in range(1, 25):
        index = today.year * 12 + today.month - 1 - offset
        year, month_zero = divmod(index, 12)
        month = month_zero + 1
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])

        payroll_exists = (
            db.query(Payroll.id)
            .filter(
                Payroll.employee_id == employee.id,
                Payroll.year == year,
                Payroll.month == month,
            )
            .first()
        ) is not None

        structure = (
            db.query(CompensationStructure.id)
            .filter(
                CompensationStructure.employee_id == employee.id,
                CompensationStructure.effective_from <= end,
                (
                    CompensationStructure.effective_to.is_(None)
                    | (CompensationStructure.effective_to >= start)
                ),
            )
            .first()
        )

        overlaps_structure = structure is not None
        employed_for_full_month = employee.joining_date <= start

        if payroll_exists:
            reason = "Payroll already exists"
        elif overlaps_structure:
            reason = "Compensation structure overlaps"
        elif not employed_for_full_month:
            reason = "Employee joined during or after this month"
        else:
            reason = "Candidate: no existing payroll or overlapping structure"

        print(
            f"{year}-{month:02d} | "
            f"payroll={payroll_exists} | "
            f"structure_overlap={overlaps_structure} | "
            f"joined_before_month={employed_for_full_month} | "
            f"{reason}"
        )

finally:
    db.close()
