from pathlib import Path
import re
import shutil

path = Path("app/routers/payroll.py")
backup = Path("app/routers/payroll.py.before_compensation_integration.bak")

content = path.read_text(encoding="utf-8-sig")
content = content.replace("\r\n", "\n")

if not backup.exists():
    shutil.copy2(path, backup)

def replace_one(text, pattern, replacement, label, flags=0):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(
            f"Could not uniquely match {label}; found {count} matches. "
            "File was not written."
        )
    print(f"PASS: matched {label}")
    return updated

# 1. Import the calculation service.
if "from app.services.compensation_payroll import calculate_compensation_for_period" not in content:
    content = replace_one(
        content,
        r"(?m)^from app\.models\.payroll import Payroll$",
        "from app.models.payroll import Payroll\n"
        "from app.services.compensation_payroll import "
        "calculate_compensation_for_period",
        "payroll imports",
    )
else:
    print("PASS: compensation service import already exists")

# 2. Integrate compensation into generation.
content = replace_one(
    content,
    r"(?m)^    monthly_salary = money\(Decimal\(str\(employee\.salary\)\)\)\n"
    r"    values = calculate_payroll_values\(\n"
    r"        db=db,\n"
    r"        employee=employee,\n"
    r"        year=year,\n"
    r"        month=month,\n"
    r"        monthly_salary=monthly_salary,\n"
    r"        as_of_date=today,\n"
    r"    \)\n\n"
    r"    payroll = Payroll\(",
    '''    monthly_salary = money(Decimal(str(employee.salary)))
    values = calculate_payroll_values(
        db=db,
        employee=employee,
        year=year,
        month=month,
        monthly_salary=monthly_salary,
        as_of_date=today,
    )

    compensation_structure_id = None
    compensation_deductions = ZERO_MONEY
    compensation_breakdown = None

    compensation_values = calculate_compensation_for_period(
        db=db,
        employee=employee,
        year=year,
        month=month,
        as_of_date=today,
        lop_days=int(values["lop_days"]),
    )

    # Existing employees without a structure retain the legacy policy.
    if compensation_values is not None:
        monthly_salary = money(
            Decimal(str(compensation_values["monthly_salary"]))
        )
        values["gross_salary"] = compensation_values["gross_salary"]
        values["lop_deduction"] = compensation_values["lop_deduction"]
        values["net_salary"] = compensation_values["net_salary"]

        compensation_structure_id = (
            compensation_values["compensation_structure_id"]
        )
        compensation_deductions = money(
            Decimal(str(compensation_values["compensation_deductions"]))
        )
        compensation_breakdown = (
            compensation_values["compensation_breakdown"]
        )

    payroll = Payroll(''',
    "payroll generation calculation",
)

# 3. Store the compensation snapshot in the new payroll record.
content = replace_one(
    content,
    r'(?m)^        net_salary=values\["net_salary"\],\n'
    r"        manual_adjustment_amount=ZERO_MONEY,$",
    '''        net_salary=values["net_salary"],
        compensation_structure_id=compensation_structure_id,
        compensation_deductions=compensation_deductions,
        compensation_breakdown=compensation_breakdown,
        manual_adjustment_amount=ZERO_MONEY,''',
    "payroll constructor",
)

# 4. Include compensation metadata in the generation audit.
content = replace_one(
    content,
    r'(?m)^                "net_salary": str\(values\["net_salary"\]\),\n'
    r'                "status": "Generated",$',
    '''                "net_salary": str(values["net_salary"]),
                "compensation_structure_id": compensation_structure_id,
                "compensation_deductions": str(compensation_deductions),
                "status": "Generated",''',
    "generation audit",
)

# 5. Preserve configured deductions when making a manual adjustment.
content = replace_one(
    content,
    r"(?m)^        new_net_salary = money\(\n"
    r"            gross_salary - lop_deduction \+ requested_adjustment\n"
    r"        \)$",
    '''        compensation_deductions = money(
            Decimal(str(payroll.compensation_deductions or ZERO_MONEY))
        )
        new_net_salary = money(
            gross_salary
            - lop_deduction
            - compensation_deductions
            + requested_adjustment
        )''',
    "manual adjustment calculation",
)

# 6. Recalculate compensation drafts correctly when locking.
content = replace_one(
    content,
    r"(?ms)^        monthly_salary = money\(Decimal\(str\(payroll\.monthly_salary\)\)\)\n"
    r"        values = calculate_payroll_values\(.*?"
    r"^        recomputed_net = money\(\n"
    r'            Decimal\(str\(values\["gross_salary"\]\)\)\n'
    r'            - Decimal\(str\(values\["lop_deduction"\]\)\)\n'
    r"            \+ manual_adjustment\n"
    r"        \)",
    '''        today = date.today()

        if payroll.compensation_structure_id is not None:
            attendance_values = calculate_payroll_values(
                db=db,
                employee=employee,
                year=payroll.year,
                month=payroll.month,
                monthly_salary=money(Decimal(str(employee.salary))),
                as_of_date=today,
            )

            compensation_values = calculate_compensation_for_period(
                db=db,
                employee=employee,
                year=payroll.year,
                month=payroll.month,
                as_of_date=today,
                lop_days=int(attendance_values["lop_days"]),
            )

            if compensation_values is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Compensation structure is unavailable for this "
                        "payroll period. Payroll was not locked."
                    ),
                )

            values = dict(attendance_values)
            values["gross_salary"] = compensation_values["gross_salary"]
            values["lop_deduction"] = compensation_values["lop_deduction"]
            values["net_salary"] = compensation_values["net_salary"]

            payroll.monthly_salary = money(
                Decimal(str(compensation_values["monthly_salary"]))
            )
            payroll.compensation_structure_id = (
                compensation_values["compensation_structure_id"]
            )
            payroll.compensation_deductions = money(
                Decimal(str(compensation_values["compensation_deductions"]))
            )
            payroll.compensation_breakdown = (
                compensation_values["compensation_breakdown"]
            )
        else:
            # Preserve the legacy lock calculation for older payroll.
            monthly_salary = money(Decimal(str(payroll.monthly_salary)))
            values = calculate_payroll_values(
                db=db,
                employee=employee,
                year=payroll.year,
                month=payroll.month,
                monthly_salary=monthly_salary,
                as_of_date=today,
            )

        manual_adjustment = money(
            Decimal(str(payroll.manual_adjustment_amount or ZERO_MONEY))
        )
        compensation_deductions = money(
            Decimal(str(payroll.compensation_deductions or ZERO_MONEY))
        )
        recomputed_net = money(
            Decimal(str(values["gross_salary"]))
            - Decimal(str(values["lop_deduction"]))
            - compensation_deductions
            + manual_adjustment
        )''',
    "payroll lock calculation",
)

# Write only after every expected code section was matched.
path.write_text(content, encoding="utf-8")
print("PASS: All changes written to payroll.py")
print(f"Backup: {backup}")
