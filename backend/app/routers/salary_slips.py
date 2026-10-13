
from io import BytesIO
from calendar import month_name

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
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

from app.db.database import get_db
from app.models.employee import Employee
from app.models.payroll import Payroll
from app.models.user import User
from app.routers.auth import get_current_user


router = APIRouter(
    prefix="/salary-slips",
    tags=["Salary Slips"],
)


def format_amount(value) -> str:
    return f"INR {float(value):,.2f}"


@router.get("/{payroll_id}/download")
def download_salary_slip(
    payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find the payroll record.
    payroll = (
        db.query(Payroll)
        .filter(Payroll.id == payroll_id)
        .first()
    )

    if payroll is None:
        raise HTTPException(
            status_code=404,
            detail="Payroll record not found",
        )

    # Employees can download only their own salary slips.
    # Admin and HR can download any employee's salary slip.
    if current_user.role not in ("Admin", "HR"):
        employee = (
            db.query(Employee)
            .filter(Employee.user_id == current_user.id)
            .first()
        )

        if (
            employee is None
            or employee.id != payroll.employee_id
        ):
            raise HTTPException(
                status_code=404,
                detail="Salary slip not found",
            )

    employee = (
        db.query(Employee)
        .filter(Employee.id == payroll.employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee record not found",
        )

    user = (
        db.query(User)
        .filter(User.id == employee.user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Employee account not found",
        )

    # Build the PDF in memory; no temporary file is required.
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "SalarySlipTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#163A5F"),
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "SalarySlipSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=18,
    )

    story = [
        Paragraph("HUMAN RESOURCE MANAGEMENT SYSTEM", title_style),
        Paragraph("MONTHLY SALARY SLIP", subtitle_style),
    ]

    period = f"{month_name[payroll.month]} {payroll.year}"

    employee_data = [
        ["Employee Name", user.full_name],
        ["Employee Code", employee.employee_code],
        ["Email", user.email],
        ["Department", employee.department],
        ["Designation", employee.designation],
        ["Joining Date", employee.joining_date.strftime("%d-%m-%Y")],
        ["Salary Period", period],
    ]

    employee_table = Table(
        employee_data,
        colWidths=[48 * mm, 112 * mm],
    )

    employee_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF1F8")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#163A5F")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])
    )

    story.extend([
        employee_table,
        Spacer(1, 10 * mm),
        Paragraph("Earnings and Deductions", styles["Heading2"]),
    ])

    salary_data = [
        ["Description", "Amount"],
        ["Monthly Gross Salary", format_amount(payroll.gross_salary)],
        ["Loss of Pay Days", str(payroll.lop_days)],
        ["LOP Deduction", format_amount(payroll.lop_deduction)],
        ["Net Salary", format_amount(payroll.net_salary)],
    ]

    salary_table = Table(
        salary_data,
        colWidths=[100 * mm, 60 * mm],
    )

    salary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF1F8")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ])
    )

    story.extend([
        salary_table,
        Spacer(1, 8 * mm),
        Paragraph(
            f"Attendance days recorded: {payroll.present_days}",
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Payroll status: {payroll.status}"
            + (
                " (simulated credit only)"
                if payroll.status == "Paid"
                else ""
            ),
            styles["Normal"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "This document was generated electronically by the HRMS. "
            "Salary credit, if marked Paid, is simulated and does not "
            "confirm an actual bank transfer.",
            styles["Italic"],
        ),
    ])

    document.build(story)
    buffer.seek(0)

    filename = (
        f"salary_slip_{employee.employee_code}_"
        f"{payroll.year}_{payroll.month:02d}.pdf"
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
