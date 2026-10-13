import csv
from decimal import Decimal
from html import escape
from io import BytesIO, StringIO
from typing import Literal
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.leave import LeaveRequest
from app.models.payroll import Payroll
from app.models.user import User


router = APIRouter(
    prefix="/reports",
    tags=["Reports & Analytics"],
)


def money(value) -> str:
    return f"INR {Decimal(str(value or 0)):,.2f}"


def display_datetime(value) -> str:
    if value is None:
        return ""

    return value.strftime("%Y-%m-%d %H:%M")


def working_hours(check_in, check_out) -> str:
    if check_in is None or check_out is None:
        return ""

    # Normalize values for compatibility with database drivers
    # that return naive datetimes for timezone-aware columns.
    start = check_in.replace(tzinfo=None)
    end = check_out.replace(tzinfo=None)

    seconds = (end - start).total_seconds()

    if seconds < 0:
        return ""

    return f"{seconds / 3600:.2f}"


def validate_date_range(
    start_date,
    end_date,
) -> None:
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=400,
            detail="Start date cannot be after end date",
        )


def get_report_data(
    report_type: str,
    db: Session,
    start_date,
    end_date,
    department: str | None,
):
    """
    Build filtered report data from existing HRMS database tables.

    Returns a title, column headings, report rows, and summary.
    """

    validate_date_range(start_date, end_date)

    if department is not None:
        department = department.strip() or None

    # -----------------------------------------------------
    # Attendance report
    # -----------------------------------------------------

    if report_type == "attendance":
        query = (
            db.query(Attendance, Employee, User)
            .join(
                Employee,
                Employee.id == Attendance.employee_id,
            )
            .join(
                User,
                User.id == Employee.user_id,
            )
        )

        if start_date is not None:
            query = query.filter(
                Attendance.attendance_date >= start_date,
            )

        if end_date is not None:
            query = query.filter(
                Attendance.attendance_date <= end_date,
            )

        if department:
            query = query.filter(
                Employee.department == department,
            )

        records = query.order_by(
            Attendance.attendance_date.desc(),
            Attendance.id.desc(),
        ).all()

        columns = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Designation",
            "Check In",
            "Check Out",
            "Working Hours",
        ]

        rows = []

        for attendance, employee, user in records:
            rows.append([
                attendance.attendance_date.isoformat(),
                employee.employee_code,
                user.full_name,
                employee.department,
                employee.designation,
                display_datetime(attendance.check_in),
                display_datetime(attendance.check_out),
                working_hours(
                    attendance.check_in,
                    attendance.check_out,
                ),
            ])

        total_hours = sum(
            Decimal(row[7])
            for row in rows
            if row[7]
        )

        summary = [
            f"Attendance records: {len(rows)}",
            (
                "Employees represented: "
                f"{len(set(row[1] for row in rows))}"
            ),
            f"Recorded working hours: {total_hours:.2f}",
        ]

        return "Attendance Report", columns, rows, summary

    # -----------------------------------------------------
    # Leave report
    # -----------------------------------------------------

    if report_type == "leave":
        query = (
            db.query(LeaveRequest, Employee, User)
            .join(
                Employee,
                Employee.id == LeaveRequest.employee_id,
            )
            .join(
                User,
                User.id == Employee.user_id,
            )
        )

        # Include leave requests that overlap the selected range.
        if start_date is not None:
            query = query.filter(
                LeaveRequest.end_date >= start_date,
            )

        if end_date is not None:
            query = query.filter(
                LeaveRequest.start_date <= end_date,
            )

        if department:
            query = query.filter(
                Employee.department == department,
            )

        records = query.order_by(
            LeaveRequest.created_at.desc(),
            LeaveRequest.id.desc(),
        ).all()

        columns = [
            "Leave ID",
            "Employee Code",
            "Employee Name",
            "Department",
            "Leave Type",
            "Start Date",
            "End Date",
            "Status",
            "LOP Days",
        ]

        rows = []

        for leave, employee, user in records:
            rows.append([
                leave.id,
                employee.employee_code,
                user.full_name,
                employee.department,
                leave.leave_type,
                leave.start_date.isoformat(),
                leave.end_date.isoformat(),
                leave.status,
                leave.lop_days or 0,
            ])

        summary = [
            f"Leave requests: {len(rows)}",
            (
                "Pending: "
                f"{sum(row[7] == 'Pending' for row in rows)}"
            ),
            (
                "Approved: "
                f"{sum(row[7] == 'Approved' for row in rows)}"
            ),
            (
                "Rejected: "
                f"{sum(row[7] == 'Rejected' for row in rows)}"
            ),
        ]

        return "Leave Report", columns, rows, summary

    # -----------------------------------------------------
    # Payroll report
    # -----------------------------------------------------

    if report_type == "payroll":
        query = (
            db.query(Payroll, Employee, User)
            .join(
                Employee,
                Employee.id == Payroll.employee_id,
            )
            .join(
                User,
                User.id == Employee.user_id,
            )
        )

        # Payroll periods are filtered by their calendar month.
        if start_date is not None:
            start_period = start_date.year * 12 + start_date.month

            query = query.filter(
                Payroll.year * 12 + Payroll.month >= start_period,
            )

        if end_date is not None:
            end_period = end_date.year * 12 + end_date.month

            query = query.filter(
                Payroll.year * 12 + Payroll.month <= end_period,
            )

        if department:
            query = query.filter(
                Employee.department == department,
            )

        records = query.order_by(
            Payroll.year.desc(),
            Payroll.month.desc(),
            Payroll.id.desc(),
        ).all()

        columns = [
            "Payroll ID",
            "Employee Code",
            "Employee Name",
            "Department",
            "Period",
            "Present Days",
            "LOP Days",
            "Gross Salary",
            "LOP Deduction",
            "Net Salary",
            "Status",
        ]

        rows = []

        for payroll, employee, user in records:
            rows.append([
                payroll.id,
                employee.employee_code,
                user.full_name,
                employee.department,
                f"{payroll.month:02d}/{payroll.year}",
                payroll.present_days,
                payroll.lop_days,
                money(payroll.gross_salary),
                money(payroll.lop_deduction),
                money(payroll.net_salary),
                payroll.status,
            ])

        total_gross = sum(
            (
                Decimal(str(record[0].gross_salary or 0))
                for record in records
            ),
            Decimal("0.00"),
        )

        total_deduction = sum(
            (
                Decimal(str(record[0].lop_deduction or 0))
                for record in records
            ),
            Decimal("0.00"),
        )

        total_net = sum(
            (
                Decimal(str(record[0].net_salary or 0))
                for record in records
            ),
            Decimal("0.00"),
        )

        summary = [
            f"Payroll records: {len(rows)}",
            f"Total gross salary: {money(total_gross)}",
            f"Total LOP deduction: {money(total_deduction)}",
            f"Total net salary: {money(total_net)}",
        ]

        return "Payroll Summary", columns, rows, summary

    raise HTTPException(
        status_code=400,
        detail=(
            "Invalid report type. Use attendance, leave, or payroll"
        ),
    )


def csv_safe_value(value) -> str:
    """
    Prevent CSV spreadsheet formula injection for text fields.
    """

    text = str(value if value is not None else "")

    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text

    return text


def build_csv(
    columns: list,
    rows: list,
) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow(columns)

    for row in rows:
        writer.writerow([
            csv_safe_value(value)
            for value in row
        ])

    return output.getvalue().encode("utf-8-sig")


def build_pdf(
    title: str,
    columns: list,
    rows: list,
    summary: list,
    start_date,
    end_date,
    department,
) -> bytes:
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#163A5F"),
        spaceAfter=10,
    )

    header_style = ParagraphStyle(
        "ReportHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.white,
    )

    cell_style = ParagraphStyle(
        "ReportCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        wordWrap="CJK",
    )

    story = [
        Paragraph(
            "PeopleDesk HRMS — " + escape(title),
            title_style,
        ),
    ]

    filter_description = []

    if start_date is not None:
        filter_description.append(
            f"Start date: {start_date.isoformat()}"
        )

    if end_date is not None:
        filter_description.append(
            f"End date: {end_date.isoformat()}"
        )

    if department:
        filter_description.append(
            f"Department: {department}"
        )

    story.append(
        Paragraph(
            escape(
                " | ".join(filter_description)
                if filter_description
                else "Filters: All records"
            ),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 5 * mm))

    for item in summary:
        story.append(
            Paragraph(escape(item), styles["Normal"])
        )

    story.append(Spacer(1, 5 * mm))

    table_data = [
        [
            Paragraph(escape(str(column)), header_style)
            for column in columns
        ]
    ]

    for row in rows:
        table_data.append([
            Paragraph(
                escape(str(value if value is not None else "")),
                cell_style,
            )
            for value in row
        ])

    column_width = document.width / len(columns)

    report_table = Table(
        table_data,
        colWidths=[column_width] * len(columns),
        repeatRows=1,
        hAlign="LEFT",
    )

    report_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#163A5F"),
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                colors.HexColor("#D6DCE5"),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    colors.HexColor("#F3F6FA"),
                ],
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ])
    )

    story.append(report_table)

    document.build(story)
    buffer.seek(0)

    return buffer.getvalue()


@router.get("/{report_type}/export")
def export_report(
    report_type: Literal["attendance", "leave", "payroll"],
    export_format: Literal["csv", "pdf"] = Query(
        default="csv",
        alias="format",
    ),
    start_date: date | None = None,
    end_date: date | None = None,
    department: str | None = Query(
        default=None,
        max_length=100,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    """
    Admin/HR report export endpoint.

    Examples:
      /reports/attendance/export?format=csv
      /reports/leave/export?format=pdf
      /reports/payroll/export?format=csv&department=IT
      /reports/attendance/export?start_date=2026-10-01&end_date=2026-10-31
    """

    title, columns, rows, summary = get_report_data(
        report_type=report_type,
        db=db,
        start_date=start_date,
        end_date=end_date,
        department=department,
    )

    filename = f"{report_type}_report.{export_format}"

    if export_format == "csv":
        content = build_csv(columns, rows)

        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"'
                ),
                "Cache-Control": "no-store",
            },
        )

    content = build_pdf(
        title=title,
        columns=columns,
        rows=rows,
        summary=summary,
        start_date=start_date,
        end_date=end_date,
        department=department,
    )

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Cache-Control": "no-store",
        },
    )