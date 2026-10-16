import asyncio
from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO

from sqlalchemy.orm import Session

from app.db.database import engine
from app.models.user import User
from app.models.employee import Employee
from app.models.payroll import Payroll
from app.routers import salary_slips as slips_router


connection = engine.connect()
outer_transaction = connection.begin()
db = Session(bind=connection, join_transaction_mode="create_savepoint")

try:
    admin = db.query(User).filter(User.role == "Admin").first()
    employee = (
        db.query(Employee)
        .filter(Employee.id == 1, Employee.is_active.is_(True))
        .first()
    )

    if admin is None or employee is None:
        raise RuntimeError("Admin account or test employee EMP001 not found.")

    # Use an unused future period for this temporary PDF-only record.
    candidate = None
    for year in range(2090, 2100):
        for month in range(1, 13):
            exists = db.query(Payroll.id).filter(
                Payroll.employee_id == employee.id,
                Payroll.year == year,
                Payroll.month == month,
            ).first()

            if not exists:
                candidate = (year, month)
                break
        if candidate:
            break

    if candidate is None:
        raise RuntimeError("No unused period available for the temporary PDF test.")

    year, month = candidate

    payroll = Payroll(
        employee_id=employee.id,
        month=month,
        year=year,
        monthly_salary=Decimal("44000.00"),
        present_days=20,
        lop_days=1,
        gross_salary=Decimal("49000.00"),
        lop_deduction=Decimal("1466.67"),
        compensation_deductions=Decimal("3600.00"),
        compensation_structure_id=None,
        compensation_breakdown=[
            {
                "component_name": "Basic Salary",
                "component_type": "Earning",
                "period_amount": "30000.00",
            },
            {
                "component_name": "HRA",
                "component_type": "Earning",
                "period_amount": "12000.00",
            },
            {
                "component_name": "Transport",
                "component_type": "Earning",
                "period_amount": "2000.00",
            },
            {
                "component_name": "Performance Bonus",
                "component_type": "Earning",
                "period_amount": "5000.00",
            },
            {
                "component_name": "PF",
                "component_type": "Deduction",
                "period_amount": "3600.00",
            },
        ],
        net_salary=Decimal("43933.33"),
        manual_adjustment_amount=Decimal("0.00"),
        status="Generated",
        is_locked=False,
        generated_by=admin.id,
    )

    db.add(payroll)
    db.flush()

    # Prevent emails or notifications during the PDF test.
    slips_router.notify_salary_slip_safely = lambda **kwargs: None

    response = slips_router.download_salary_slip(
        payroll_id=payroll.id,
        db=db,
        current_user=admin,
    )

    async def read_response():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        return b"".join(chunks)

    pdf_bytes = asyncio.run(read_response())

    print("===== PDF RESPONSE =====")
    print("Content type:", response.media_type)
    print("Disposition:", response.headers.get("content-disposition"))
    print("PDF bytes:", len(pdf_bytes))
    print("Valid PDF signature:", pdf_bytes.startswith(b"%PDF-"))

    if response.media_type != "application/pdf":
        raise AssertionError("Response media type is not application/pdf.")

    if not pdf_bytes.startswith(b"%PDF-"):
        raise AssertionError("PDF signature is missing.")

    if len(pdf_bytes) < 500:
        raise AssertionError("PDF response is unexpectedly small.")

    # Extract PDF text using an installed parser if available.
    reader_class = None
    try:
        from pypdf import PdfReader
        reader_class = PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
            reader_class = PdfReader
        except ImportError:
            pass

    if reader_class is not None:
        reader = reader_class(BytesIO(pdf_bytes))
        pdf_text = " ".join(
            (page.extract_text() or "")
            for page in reader.pages
        )
        normalized = " ".join(pdf_text.split())

        expected = [
            "Basic Salary",
            "HRA",
            "Transport",
            "Performance Bonus",
            "Deduction: PF",
            "Gross Earnings",
            "LOP Deduction",
            "Total Compensation Deductions",
            "Manual Adjustment",
            "Net Salary",
        ]

        missing = [label for label in expected if label not in normalized]
        print("PDF pages:", len(reader.pages))
        print("Component text checks:", len(expected) - len(missing), "/", len(expected))

        if missing:
            raise AssertionError(
                f"Missing labels in generated PDF: {missing}"
            )

        print("PASS: All expected payslip labels were extracted.")
    else:
        print(
            "WARNING: PDF generation passed, but no PDF text reader is "
            "installed to verify each label."
        )

    print("PASS: Temporary payslip generated successfully.")

finally:
    db.close()
    outer_transaction.rollback()
    connection.close()
    print("ROLLBACK: Temporary PDF test payroll was not committed.")
