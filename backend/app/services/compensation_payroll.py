from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.compensation import (
    CompensationComponent,
    CompensationStructure,
)
from app.models.employee import Employee


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
DAILY_SALARY_BASIS = Decimal("30")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def as_text(value: Decimal) -> str:
    return format(money(value), ".2f")


def monthly_component_amount(
    component: CompensationComponent,
    basic_salary: Decimal,
) -> Decimal:
    configured_amount = Decimal(str(component.amount))

    if component.calculation_method == "Fixed":
        return configured_amount

    if component.calculation_method == "PercentOfBasic":
        return basic_salary * configured_amount / Decimal("100")

    # PerOvertimeHour is calculated against actual shift overtime,
    # not as part of a regular monthly salary.
    if component.calculation_method == "PerOvertimeHour":
        return ZERO

    raise ValueError(
        f"Unsupported compensation method: "
        f"{component.calculation_method}"
    )


def get_overtime_minutes_by_date(
    db: Session,
    employee_id: int,
    start_date: date,
    end_date: date,
) -> dict[date, int]:
    """
    Derive overtime from completed attendance and the shift assigned
    on each date. Attendance records themselves are not modified.
    """
    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= end_date,
            Attendance.check_out.is_not(None),
        )
        .order_by(Attendance.attendance_date.asc())
        .all()
    )

    if not records:
        return {}

    # Reuse the existing shift-aware attendance calculation so payroll
    # and attendance use the same shift timing rules.
    from app.routers.attendance import (
        calculate_shift_metrics,
        get_assigned_shift,
    )

    result: dict[date, int] = {}

    for record in records:
        shift = get_assigned_shift(
            db,
            record.employee_id,
            record.attendance_date,
        )
        metrics = calculate_shift_metrics(record, shift)
        minutes = metrics.get("overtime_minutes")

        if minutes is not None and minutes > 0:
            result[record.attendance_date] = int(minutes)

    return result


def calculate_compensation_for_period(
    db: Session,
    employee: Employee,
    year: int,
    month: int,
    as_of_date: date,
    lop_days: int,
) -> dict | None:
    """
    Build a compensation snapshot for one payroll period.

    Returns None when no compensation structure applies during the
    employed portion of the period. The caller can then retain the
    existing legacy payroll calculation.

    Calendar-day proration follows the existing payroll policy.
    Non-recurring fixed/percentage components are included only in the
    month in which their structure becomes effective, preventing the
    same configured bonus from being paid every month.
    """
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    employed_start = max(month_start, employee.joining_date)
    # Salary is calculated for the full payroll month, matching the
    # existing payroll policy. Attendance/overtime use only available
    # data up to the calculation date.
    period_end = month_end
    overtime_end = min(month_end, as_of_date)
    recognition_cutoff = overtime_end

    if employed_start > period_end:
        return None

    structures = (
        db.query(CompensationStructure)
        .filter(
            CompensationStructure.employee_id == employee.id,
            CompensationStructure.effective_from <= period_end,
            or_(
                CompensationStructure.effective_to.is_(None),
                CompensationStructure.effective_to >= employed_start,
            ),
        )
        .order_by(
            CompensationStructure.effective_from.asc(),
            CompensationStructure.id.asc(),
        )
        .all()
    )

    if not structures:
        return None

    components_by_structure: dict[int, list[CompensationComponent]] = {}
    for structure in structures:
        components_by_structure[structure.id] = (
            db.query(CompensationComponent)
            .filter(
                CompensationComponent.structure_id == structure.id
            )
            .order_by(CompensationComponent.id.asc())
            .all()
        )

    # Map each employed calendar date to its effective compensation
    # version. API validation prevents overlapping versions; choosing
    # the latest effective version also protects against legacy data.
    active_structure_by_date: dict[date, CompensationStructure | None] = {}
    structure_days: dict[int, int] = {
        structure.id: 0 for structure in structures
    }

    cursor = employed_start
    while cursor <= period_end:
        active = None

        for structure in reversed(structures):
            if (
                structure.effective_from <= cursor
                and (
                    structure.effective_to is None
                    or structure.effective_to >= cursor
                )
            ):
                active = structure
                break

        active_structure_by_date[cursor] = active

        if active is not None:
            structure_days[active.id] += 1

        cursor = date.fromordinal(cursor.toordinal() + 1)

    if not any(structure_days.values()):
        return None

    month_calendar_days = Decimal(monthrange(year, month)[1])
    period_calendar_days = Decimal(
        (period_end - employed_start).days + 1
    )
    legacy_salary = Decimal(str(employee.salary or ZERO))

    # Precompute recurring monthly gross rates per version.
    monthly_gross_by_structure: dict[int, Decimal] = {}

    for structure in structures:
        monthly_gross = Decimal(str(structure.basic_salary))

        for component in components_by_structure[structure.id]:
            if (
                component.component_type == "Earning"
                and component.is_recurring
                and component.calculation_method != "PerOvertimeHour"
            ):
                monthly_gross += monthly_component_amount(
                    component,
                    Decimal(str(structure.basic_salary)),
                )

        monthly_gross_by_structure[structure.id] = monthly_gross

    # The stored monthly_salary is the weighted monthly gross rate
    # across the employed dates covered by this calculation.
    weighted_monthly_gross = ZERO

    for day, structure in active_structure_by_date.items():
        if structure is None:
            weighted_monthly_gross += legacy_salary / period_calendar_days
        else:
            weighted_monthly_gross += (
                monthly_gross_by_structure[structure.id]
                / period_calendar_days
            )

    monthly_salary = money(weighted_monthly_gross)

    earnings = ZERO
    compensation_deductions = ZERO
    breakdown: list[dict] = []

    # Basic salary and recurring components accrue only over the
    # number of employed days for which each version was effective.
    for structure in structures:
        active_days = structure_days[structure.id]
        if active_days <= 0:
            continue

        basic = Decimal(str(structure.basic_salary))
        basic_period_amount = money(
            basic * Decimal(active_days) / month_calendar_days
        )
        earnings += basic_period_amount

        breakdown.append({
            "structure_id": structure.id,
            "component_id": None,
            "component_name": "Basic Salary",
            "component_type": "Earning",
            "calculation_method": "ProratedMonthly",
            "monthly_amount": as_text(basic),
            "period_amount": as_text(basic_period_amount),
            "active_days": active_days,
            "is_taxable": True,
            "is_recurring": True,
        })

        for component in components_by_structure[structure.id]:
            configured_amount = Decimal(str(component.amount))
            method = component.calculation_method

            if method == "PerOvertimeHour":
                # Calculated separately from actual shift overtime below.
                continue

            monthly_amount = monthly_component_amount(
                component,
                basic,
            )

            included_as_one_time = (
                not component.is_recurring
                and employed_start <= structure.effective_from <= recognition_cutoff
                and structure.effective_from.year == year
                and structure.effective_from.month == month
            )

            if component.is_recurring:
                period_amount = money(
                    monthly_amount
                    * Decimal(active_days)
                    / month_calendar_days
                )
            elif included_as_one_time:
                period_amount = money(monthly_amount)
            else:
                # Don't pay a configured one-time bonus repeatedly.
                continue

            if component.component_type == "Earning":
                earnings += period_amount
            else:
                compensation_deductions += period_amount

            breakdown.append({
                "structure_id": structure.id,
                "component_id": component.id,
                "component_name": component.component_name,
                "component_type": component.component_type,
                "calculation_method": method,
                "configured_amount": as_text(configured_amount),
                "monthly_amount": as_text(monthly_amount),
                "period_amount": as_text(period_amount),
                "active_days": active_days,
                "is_taxable": bool(component.is_taxable),
                "is_recurring": bool(component.is_recurring),
            })

    # Preserve the existing Employee.salary behavior for dates that
    # have no active compensation structure.
    legacy_days = sum(
        1 for structure in active_structure_by_date.values()
        if structure is None
    )

    if legacy_days:
        legacy_period_amount = money(
            legacy_salary * Decimal(legacy_days) / month_calendar_days
        )
        earnings += legacy_period_amount
        breakdown.append({
            "structure_id": None,
            "component_id": None,
            "component_name": "Legacy Salary",
            "component_type": "Earning",
            "calculation_method": "ProratedMonthly",
            "monthly_amount": as_text(legacy_salary),
            "period_amount": as_text(legacy_period_amount),
            "active_days": legacy_days,
            "is_taxable": True,
            "is_recurring": True,
        })

    # Compute overtime only where a structure and hourly rate applied
    # on the corresponding attendance date.
    overtime_minutes_by_date = get_overtime_minutes_by_date(
        db=db,
        employee_id=employee.id,
        start_date=employed_start,
        end_date=overtime_end,
    )

    overtime_minutes_by_structure: dict[int, int] = {}

    for overtime_date, minutes in overtime_minutes_by_date.items():
        structure = active_structure_by_date.get(overtime_date)

        if structure is not None:
            overtime_minutes_by_structure[structure.id] = (
                overtime_minutes_by_structure.get(structure.id, 0)
                + minutes
            )

    for structure in structures:
        active_minutes = overtime_minutes_by_structure.get(
            structure.id, 0
        )
        if active_minutes <= 0:
            continue

        overtime_hours = Decimal(active_minutes) / Decimal("60")

        for component in components_by_structure[structure.id]:
            if component.calculation_method != "PerOvertimeHour":
                continue

            rate = Decimal(str(component.amount))
            period_amount = money(rate * overtime_hours)

            if component.component_type == "Earning":
                earnings += period_amount
            else:
                compensation_deductions += period_amount

            breakdown.append({
                "structure_id": structure.id,
                "component_id": component.id,
                "component_name": component.component_name,
                "component_type": component.component_type,
                "calculation_method": "PerOvertimeHour",
                "configured_amount": as_text(rate),
                "overtime_minutes": active_minutes,
                "overtime_hours": str(overtime_hours),
                "period_amount": as_text(period_amount),
                "is_taxable": bool(component.is_taxable),
                "is_recurring": bool(component.is_recurring),
            })

    gross_salary = money(earnings)
    compensation_deductions = money(compensation_deductions)

    # Preserve the project's fixed 30-day loss-of-pay policy.
    lop_deduction = money(
        monthly_salary * Decimal(max(0, lop_days)) / DAILY_SALARY_BASIS
    )
    lop_deduction = min(lop_deduction, gross_salary)

    net_salary = money(
        max(
            ZERO,
            gross_salary - lop_deduction - compensation_deductions,
        )
    )

    # This field is a convenient pointer. The breakdown retains all
    # structure IDs used if the effective structure changed mid-month.
    applicable_structure_id = None
    for day in sorted(active_structure_by_date, reverse=True):
        structure = active_structure_by_date[day]
        if structure is not None:
            applicable_structure_id = structure.id
            break

    return {
        "compensation_structure_id": applicable_structure_id,
        "monthly_salary": monthly_salary,
        "gross_salary": gross_salary,
        "lop_deduction": lop_deduction,
        "compensation_deductions": compensation_deductions,
        "net_salary": net_salary,
        "compensation_breakdown": breakdown,
        "present_days": None,
        "lop_days": max(0, lop_days),
        "overtime_minutes": sum(overtime_minutes_by_date.values()),
    }

