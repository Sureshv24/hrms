import os
import smtplib
import ssl
from datetime import datetime, timezone
from decimal import Decimal
from email.message import EmailMessage
from html import escape

from sqlalchemy.orm import Session

from app.models.email_log import EmailLog


def _save_email_log(
    db: Session,
    recipient_email: str,
    subject: str,
    template_name: str,
    status: str,
    related_entity_type: str | None = None,
    related_entity_id: int | str | None = None,
    error_message: str | None = None,
) -> None:
    """Persist the result of an email delivery attempt."""

    log = EmailLog(
        recipient_email=recipient_email,
        subject=subject,
        template_name=template_name,
        status=status,
        related_entity_type=related_entity_type,
        related_entity_id=(
            str(related_entity_id)
            if related_entity_id is not None
            else None
        ),
        error_message=error_message,
        sent_at=(
            datetime.now(timezone.utc).replace(tzinfo=None)
            if status == "sent"
            else None
        ),
    )

    try:
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()

        # Do not expose database or SMTP details to the client.
        # In production, send this failure to a secure application
        # logger or monitoring service.


def send_email(
    db: Session,
    recipient_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    template_name: str,
    related_entity_type: str | None = None,
    related_entity_id: int | str | None = None,
) -> str:
    """
    Send an email and record its outcome.

    Returns: 'sent', 'failed', or 'skipped'.

    Call after the main HR operation has been committed.
    """

    recipient_email = recipient_email.strip().lower()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    sender_email = os.getenv("SMTP_FROM_EMAIL", "").strip()

    use_tls = (
        os.getenv("SMTP_USE_TLS", "true").lower()
        in ("1", "true", "yes")
    )

    if not sender_email:
        sender_email = smtp_username

    delivery_status = "failed"
    error_message = None

    if not recipient_email or "@" not in recipient_email:
        delivery_status = "failed"
        error_message = "Recipient email address is invalid"

    elif not smtp_host or not sender_email:
        delivery_status = "skipped"
        error_message = "SMTP is not configured"

    else:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender_email
        message["To"] = recipient_email

        message.set_content(text_body)
        message.add_alternative(
            html_body,
            subtype="html",
        )

        try:
            with smtplib.SMTP(
                smtp_host,
                smtp_port,
                timeout=20,
            ) as server:

                if use_tls:
                    server.starttls(
                        context=ssl.create_default_context()
                    )

                if smtp_username:
                    server.login(
                        smtp_username,
                        smtp_password,
                    )

                server.send_message(message)

            delivery_status = "sent"

        except Exception:
            # Intentionally do not store credentials or raw server
            # responses in the database.
            delivery_status = "failed"
            error_message = (
                "Email delivery failed. Check the server-side "
                "SMTP configuration and application logs."
            )

    _save_email_log(
        db=db,
        recipient_email=recipient_email or "(invalid recipient)",
        subject=subject,
        template_name=template_name,
        status=delivery_status,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        error_message=error_message,
    )

    return delivery_status


def _email_layout(
    title: str,
    content: str,
) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
      <body style="
        margin: 0;
        padding: 24px;
        background: #f3f5fb;
        font-family: Arial, sans-serif;
        color: #172554;
      ">
        <div style="
          max-width: 600px;
          margin: auto;
          background: #ffffff;
          border-radius: 12px;
          padding: 28px;
        ">
          <h2 style="color: #4338ca;">
            PeopleDesk HRMS
          </h2>

          <h3>{escape(title)}</h3>

          {content}

          <hr style="border: 0; border-top: 1px solid #e5e7eb;">

          <p style="font-size: 12px; color: #64748b;">
            This is an automated notification from PeopleDesk HRMS.
          </p>
        </div>
      </body>
    </html>
    """


def send_employee_onboarding_email(
    db: Session,
    recipient_email: str,
    employee_name: str,
    employee_code: str,
    employee_id: int | None = None,
) -> str:
    name = escape(employee_name)
    code = escape(employee_code)

    subject = "Welcome to PeopleDesk HRMS"

    text_body = (
        f"Hello {employee_name},\n\n"
        "Your employee account and employment profile have "
        "been created.\n"
        f"Employee code: {employee_code}\n\n"
        "Please use your assigned credentials to sign in."
    )

    html_body = _email_layout(
        "Welcome to the team!",
        f"""
        <p>Hello <strong>{name}</strong>,</p>
        <p>Your employee account and employment profile
        have been created successfully.</p>
        <p>Employee code: <strong>{code}</strong></p>
        <p>Please use your assigned credentials to sign in.</p>
        """,
    )

    return send_email(
        db=db,
        recipient_email=recipient_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        template_name="employee_onboarding",
        related_entity_type="employee",
        related_entity_id=employee_id,
    )


def send_leave_notification_email(
    db: Session,
    recipient_email: str,
    employee_name: str,
    leave_type: str,
    start_date,
    end_date,
    leave_status: str,
    leave_id: int | None = None,
) -> str:
    subject = f"Leave request {leave_status.lower()}"

    name = escape(employee_name)
    leave_type_html = escape(leave_type)
    status_html = escape(leave_status)
    start_html = escape(str(start_date))
    end_html = escape(str(end_date))

    text_body = (
        f"Hello {employee_name},\n\n"
        f"Your {leave_type} leave request from {start_date} "
        f"to {end_date} has status: {leave_status}.\n\n"
        "Please sign in to HRMS to view your leave history."
    )

    html_body = _email_layout(
        "Leave request update",
        f"""
        <p>Hello <strong>{name}</strong>,</p>
        <p>Your leave request has been updated.</p>
        <p>Leave type: <strong>{leave_type_html}</strong></p>
        <p>Start date: {start_html}</p>
        <p>End date: {end_html}</p>
        <p>Status: <strong>{status_html}</strong></p>
        <p>Please sign in to HRMS to view your leave history.</p>
        """,
    )

    return send_email(
        db=db,
        recipient_email=recipient_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        template_name="leave_notification",
        related_entity_type="leave",
        related_entity_id=leave_id,
    )


def send_payroll_notification_email(
    db: Session,
    recipient_email: str,
    employee_name: str,
    month: int,
    year: int,
    net_salary: Decimal | str | float,
    payroll_status: str,
    payroll_id: int | None = None,
) -> str:
    amount = Decimal(str(net_salary))
    formatted_amount = f"INR {amount:,.2f}"

    subject = f"Payroll update - {month:02d}/{year}"

    name = escape(employee_name)
    status_html = escape(payroll_status)
    amount_html = escape(formatted_amount)

    text_body = (
        f"Hello {employee_name},\n\n"
        f"Your payroll for {month:02d}/{year} "
        f"has status: {payroll_status}.\n"
        f"Net salary: {formatted_amount}\n\n"
        "Sign in to PeopleDesk HRMS to view your payroll details."
    )

    html_body = _email_layout(
        "Payroll update",
        f"""
        <p>Hello <strong>{name}</strong>,</p>
        <p>Your payroll record has been updated.</p>
        <p>Period: <strong>{month:02d}/{year}</strong></p>
        <p>Status: <strong>{status_html}</strong></p>
        <p>Net salary: <strong>{amount_html}</strong></p>
        <p>Please sign in to HRMS to view your payroll details.</p>
        """,
    )

    return send_email(
        db=db,
        recipient_email=recipient_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        template_name="payroll_notification",
        related_entity_type="payroll",
        related_entity_id=payroll_id,
    )


def send_salary_slip_notification_email(
    db: Session,
    recipient_email: str,
    employee_name: str,
    month: int,
    year: int,
    payroll_id: int | None = None,
) -> str:
    subject = f"Salary slip available - {month:02d}/{year}"

    name = escape(employee_name)

    text_body = (
        f"Hello {employee_name},\n\n"
        f"Your salary slip for {month:02d}/{year} is available.\n"
        "Sign in to PeopleDesk HRMS to download it."
    )

    html_body = _email_layout(
        "Your salary slip is available",
        f"""
        <p>Hello <strong>{name}</strong>,</p>
        <p>Your salary slip for
        <strong>{month:02d}/{year}</strong> is available.</p>
        <p>Please sign in to PeopleDesk HRMS to download your PDF.</p>
        """,
    )

    return send_email(
        db=db,
        recipient_email=recipient_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        template_name="salary_slip_notification",
        related_entity_type="payroll",
        related_entity_id=payroll_id,
    )