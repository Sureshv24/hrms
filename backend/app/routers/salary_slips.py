import logging
from io import BytesIO
from calendar import month_name

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
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
from app.models.email_log import EmailLog
from app.models.payroll import Payroll
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.email_service import (
    send_salary_slip_notification_email,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/salary-slips",
    tags=["Salary Slips"],
)


def format_amount(value) -> str:
    return f"INR {float(value):,.2f}"


def notify_salary_slip_safely(
    db: Session,
    recipient: User,
    payroll: Payroll,
) -> None:
    """
    Send a salary-slip availability notification only once per
    payroll record after the PDF has been generated successfully.

    A failed or skipped email can be retried on a later download.
    Email failures must never prevent the PDF from being downloaded.
    """

    try:
        # Avoid sending duplicate notifications for repeated downloads.
        existing_notification = (
            db.query(EmailLog.id)
            .filter(
                EmailLog.template_name
                == "salary_slip_notification",
                EmailLog.related_entity_type == "payroll",
                EmailLog.related_entity_id == str(payroll.id),
                EmailLog.status == "sent",
            )
            .first()
        )

        if existing_notification:
            logger.info(
                "Salary-slip notification already sent "
                "for payroll_id=%s",
                payroll.id,
            )
            return

        email_status = send_salary_slip_notification_email(
            db=db,
            recipient_email=recipient.email,
            employee_name=recipient.full_name,
            month=payroll.month,
            year=payroll.year,
            payroll_id=payroll.id,
        )

        if email_status != "sent":
            logger.warning(
                "Salary-slip email status=%s for payroll_id=%s",
                email_status,
                payroll.id,
            )

    except Exception:
        logger.exception(
            "Unable to process salary-slip notification "
            "for payroll_id=%s",
            payroll.id,
        )


@router.get("/{payroll_id}/download")
def download_salary_slip(
    payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Find the payroll record.
    payroll = (
        db.query(Payroll)
        .filter(Payroll.id == payroll_id)
        .first()
    )

    if payroll is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll record not found",
        )

    # 2. Employees can download only their own salary slips.
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
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salary slip not found",
            )

    # 3. Retrieve the employee record.
    employee = (
        db.query(Employee)
        .filter(Employee.id == payroll.employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )

    # 4. Retrieve the linked employee account.
    user = (
        db.query(User)
        .filter(User.id == employee.user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee account not found",
        )

    # 5. Build the PDF in memory; no temporary file is required.
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
        Paragraph(
            "HUMAN RESOURCE MANAGEMENT SYSTEM",
            title_style,
        ),
        Paragraph(
            "MONTHLY SALARY SLIP",
            subtitle_style,
        ),
    ]

    period = (
        f"{month_name[payroll.month]} {payroll.year}"
    )

    employee_data = [
        ["Employee Name", user.full_name],
        ["Employee Code", employee.employee_code],
        ["Email", user.email],
        ["Department", employee.department],
        ["Designation", employee.designation],
        [
            "Joining Date",
            employee.joining_date.strftime("%d-%m-%Y"),
        ],
        ["Salary Period", period],
    ]

    employee_table = Table(
        employee_data,
        colWidths=[48 * mm, 112 * mm],
    )

    employee_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, -1),
                colors.HexColor("#EAF1F8"),
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (0, -1),
                colors.HexColor("#163A5F"),
            ),
            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTNAME",
                (1, 0),
                (1, -1),
                "Helvetica",
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.lightgrey,
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                7,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                7,
            ),
        ])
    )

    story.extend([
        employee_table,
        Spacer(1, 10 * mm),
        Paragraph(
            "Earnings and Deductions",
            styles["Heading2"],
        ),
    ])

    salary_data = [["Description", "Amount"]]

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

    salary_table = Table(
        salary_data,
        colWidths=[100 * mm, 60 * mm],
    )

    salary_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#163A5F"),
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),
            (
                "FONTNAME",
                (0, 1),
                (-1, -2),
                "Helvetica",
            ),
            (
                "BACKGROUND",
                (0, -1),
                (-1, -1),
                colors.HexColor("#EAF1F8"),
            ),
            (
                "FONTNAME",
                (0, -1),
                (-1, -1),
                "Helvetica-Bold",
            ),
            (
                "ALIGN",
                (1, 1),
                (1, -1),
                "RIGHT",
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.lightgrey,
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                9,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                9,
            ),
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

    # Generate the PDF before attempting the notification.
    document.build(story)
    buffer.seek(0)

    filename = (
        f"salary_slip_{employee.employee_code}_"
        f"{payroll.year}_{payroll.month:02d}.pdf"
    )

    # 6. Notify the employee that the salary slip is available.
    # The email tells the employee to sign in to HRMS to download it.
    # The PDF itself is returned through the HTTP response.
    notify_salary_slip_safely(
        db=db,
        recipient=user,
        payroll=payroll,
    )

    # 7. Return the generated PDF even if email delivery fails.
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )