from calendar import monthrange
from datetime import date

from sqlalchemy import or_
from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.payroll import Payroll
from app.models.compensation import CompensationStructure

db = SessionLocal()

try:
    today = date.today()
    employees = (
        db.query(Employee)
        .filter(Employee.is_active.is_(True))
        .order_by(Employee.id)
        .all()
    )

    found = False
    print("===== SAFE HISTORICAL TEST PERIODS =====")

    for employee in employees:
        print(
            f"\nEmployee: {employee.employee_code} "
            f"(ID {employee.id}), joining date: {employee.joining_date}"
        )

        for offset in range(1, 37):
            index = today.year * 12 + today.month - 1 - offset
            year, month_zero = divmod(index, 12)
            month = month_zero + 1
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])

            if employee.joining_date > start or end >= today:
                continue

            payroll_exists = (
                db.query(Payroll.id)
                .filter(
                    Payroll.employee_id == employee.id,
                    Payroll.year == year,
                    Payroll.month == month,
                )
                .first()
            )

            if payroll_exists:
                continue

            structure_exists = (
                db.query(CompensationStructure.id)
                .filter(
                    CompensationStructure.employee_id == employee.id,
                    CompensationStructure.effective_from <= end,
                    or_(
                        CompensationStructure.effective_to.is_(None),
                        CompensationStructure.effective_to >= start,
                    ),
                )
                .first()
            )

            if structure_exists:
                continue

            print(
                f"CANDIDATE: employee_id={employee.id}, "
                f"employee_code={employee.employee_code}, "
                f"year={year}, month={month}"
            )
            found = True
            break

    if not found:
        print(
            "\nNo safe completed period found. "
            "No database records were changed."
        )

finally:
    db.close()
