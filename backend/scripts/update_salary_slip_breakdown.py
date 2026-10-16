from pathlib import Path
import re
import shutil

path = Path("app/routers/salary_slips.py")
backup = Path("app/routers/salary_slips.py.before_compensation_breakdown.bak")

content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")

if not backup.exists():
    shutil.copy2(path, backup)

pattern = (
    r"(?s)    salary_data = \[\n"
    r".*?"
    r"\n    \]\n\n"
    r"    salary_table = Table\("
)

replacement = '''    salary_data = [["Description", "Amount"]]

    # Use the saved snapshot so historical payslips do not recalculate
    # compensation from a later employee salary structure.
    compensation_breakdown = payroll.compensation_breakdown or []

    for component in compensation_breakdown:
        component_name = str(
            component.get("component_name") or "Compensation component"
        )
        component_type = component.get("component_type")
        period_amount = component.get("period_amount", "0.00")
        amount_text = format_amount(period_amount)

        if component_type == "Deduction":
            salary_data.append(
                [f"Deduction: {component_name}", f"- {amount_text}"]
            )
        else:
            salary_data.append(
                [f"Earning: {component_name}", amount_text]
            )

    salary_data.extend([
        ["Gross Earnings", format_amount(payroll.gross_salary)],
        ["Loss of Pay Days", str(payroll.lop_days)],
        ["LOP Deduction", format_amount(payroll.lop_deduction)],
        [
            "Total Compensation Deductions",
            format_amount(
                getattr(payroll, "compensation_deductions", 0) or 0
            ),
        ],
    ])

    adjustment_value = float(payroll.manual_adjustment_amount or 0)
    adjustment_amount = format_amount(abs(adjustment_value))

    if adjustment_value > 0:
        adjustment_text = f"+ {adjustment_amount}"
    elif adjustment_value < 0:
        adjustment_text = f"- {adjustment_amount}"
    else:
        adjustment_text = format_amount(0)

    salary_data.extend([
        ["Manual Adjustment", adjustment_text],
        ["Net Salary", format_amount(payroll.net_salary)],
    ])

    salary_table = Table('''

updated, count = re.subn(
    pattern,
    lambda match: replacement,
    content,
    count=1,
)

if count != 1:
    raise RuntimeError(
        f"Could not uniquely locate the PDF salary table: {count} matches. "
        "No file changes were saved."
    )

# Write only after the expected salary table was found.
path.write_text(updated, encoding="utf-8")
print("PASS: PDF salary table updated.")
print(f"Backup: {backup}")
