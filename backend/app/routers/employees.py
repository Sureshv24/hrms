import logging
import re
import uuid

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.db.database import get_db
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
)
from app.schemas.employee_document import EmployeeDocumentResponse
from app.services.email_service import (
    send_employee_onboarding_email,
)
from app.utils.audit import record_audit_log


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/employees",
    tags=["Employee Management"],
)

# Files are stored outside the public frontend directory.
BACKEND_DIR = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = (
    BACKEND_DIR / "uploads" / "employee_documents"
)

MAX_DOCUMENT_SIZE = 5 * 1024 * 1024  # 5 MB
CHUNK_SIZE = 64 * 1024

# Only these file types are accepted.
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
}


def get_employee_or_404(
    employee_id: int,
    db: Session,
) -> Employee:
    employee = (
        db.query(Employee)
        .filter(Employee.id == employee_id)
        .first()
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )

    return employee


def ensure_document_access(
    employee_id: int,
    db: Session,
    current_user: User,
) -> Employee:
    """
    Admin/HR can access any employee's documents.
    Employees can access only their own documents.
    """

    employee = get_employee_or_404(
        employee_id=employee_id,
        db=db,
    )

    if current_user.role in ("Admin", "HR"):
        return employee

    if employee.user_id != current_user.id:
        # Return 404 instead of revealing another employee's data.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )

    return employee


def sanitize_original_filename(
    filename: str | None,
) -> str:
    """
    Keep a safe display filename without trusting client paths.
    """

    raw = (filename or "").replace("\\", "/")
    basename = raw.rsplit("/", 1)[-1]

    safe_name = re.sub(
        r"[^\w.\- ()]",
        "_",
        basename,
        flags=re.UNICODE,
    ).strip(" .")

    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid filename is required",
        )

    if len(safe_name) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot exceed 255 characters",
        )

    return safe_name


def validate_file_signature(
    prefix: bytes,
    extension: str,
) -> str:
    """
    Validate file contents instead of trusting the supplied MIME type.
    Returns the server-determined content type.
    """

    if extension == ".pdf" and prefix.startswith(b"%PDF-"):
        return "application/pdf"

    if (
        extension == ".png"
        and prefix.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        return "image/png"

    if (
        extension in (".jpg", ".jpeg")
        and prefix.startswith(b"\xff\xd8\xff")
    ):
        return "image/jpeg"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "File content does not match the allowed PDF, PNG, "
            "or JPEG file types"
        ),
    )


def remove_saved_file(path: Path | None) -> None:
    if path is None:
        return

    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception(
            "Unable to remove temporary employee document: %s",
            path.name,
        )


async def save_employee_document(
    upload: UploadFile,
) -> tuple[str, str, str, int, Path]:
    """
    Save a file under a random storage name.

    Limits the file size, checks the extension and file signature,
    and removes partially uploaded files on failure.
    """

    original_filename = sanitize_original_filename(
        upload.filename
    )

    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. "
                "Allowed types: PDF, PNG, JPG, JPEG"
            ),
        )

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    destination = DOCUMENTS_DIR / stored_filename

    size_bytes = 0
    prefix = bytearray()

    try:
        DOCUMENTS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Exclusive creation avoids accidentally overwriting a file.
        with destination.open("xb") as output:
            while True:
                chunk = await upload.read(CHUNK_SIZE)

                if not chunk:
                    break

                size_bytes += len(chunk)

                if size_bytes > MAX_DOCUMENT_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Maximum document size is 5 MB",
                    )

                if len(prefix) < 16:
                    remaining = 16 - len(prefix)
                    prefix.extend(chunk[:remaining])

                output.write(chunk)

        if size_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        content_type = validate_file_signature(
            bytes(prefix),
            extension,
        )

        return (
            original_filename,
            stored_filename,
            content_type,
            size_bytes,
            destination,
        )

    except HTTPException:
        remove_saved_file(destination)
        raise

    except OSError as exc:
        remove_saved_file(destination)

        logger.exception(
            "Unable to save employee document"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the uploaded document",
        ) from exc

    except Exception as exc:
        remove_saved_file(destination)

        logger.exception(
            "Unexpected employee document upload error"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process the uploaded document",
        ) from exc

    finally:
        await upload.close()


# ---------------------------------------------------------
# CREATE EMPLOYEE
# ---------------------------------------------------------

@router.post(
    "/",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    user = (
        db.query(User)
        .filter(User.id == data.user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "User account not found. "
                "Register the user first."
            ),
        )

    if user.role != "Employee":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "An employee record can only be linked "
                "to an Employee account"
            ),
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot create an employee record "
                "for an inactive user"
            ),
        )

    existing_profile = (
        db.query(Employee)
        .filter(Employee.user_id == data.user_id)
        .first()
    )

    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This user already has an employee record"
            ),
        )

    existing_code = (
        db.query(Employee)
        .filter(
            Employee.employee_code == data.employee_code
        )
        .first()
    )

    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee code already exists",
        )

    employee = Employee(**data.model_dump())
    db.add(employee)

    try:
        db.flush()

        record_audit_log(
            db=db,
            actor=current_user,
            action="employee.created",
            entity_type="employee",
            entity_id=employee.id,
            details={
                "employee_code": employee.employee_code,
                "department": employee.department,
                "designation": employee.designation,
            },
        )

        db.commit()
        db.refresh(employee)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Employee code or user account already exists"
            ),
        ) from exc

    # Email delivery must not undo employee creation.
    try:
        email_status = send_employee_onboarding_email(
            db=db,
            recipient_email=user.email,
            employee_name=user.full_name,
            employee_code=employee.employee_code,
            employee_id=employee.id,
        )

        if email_status != "sent":
            logger.warning(
                "Onboarding email status=%s for employee_id=%s",
                email_status,
                employee.id,
            )

    except Exception:
        logger.exception(
            "Unable to process onboarding email for employee_id=%s",
            employee.id,
        )

    return employee


# ---------------------------------------------------------
# LIST EMPLOYEES — ADMIN/HR
# ---------------------------------------------------------

@router.get(
    "/",
    response_model=list[EmployeeResponse],
)
def list_employees(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    query = db.query(Employee)

    if not include_inactive:
        query = query.filter(
            Employee.is_active.is_(True)
        )

    return (
        query
        .order_by(Employee.id)
        .offset(skip)
        .limit(min(max(limit, 1), 100))
        .all()
    )


# ---------------------------------------------------------
# EMPLOYEE DOCUMENTS — LIST
# ---------------------------------------------------------

@router.get(
    "/{employee_id}/documents",
    response_model=list[EmployeeDocumentResponse],
)
def list_employee_documents(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = ensure_document_access(
        employee_id=employee_id,
        db=db,
        current_user=current_user,
    )

    return (
        db.query(EmployeeDocument)
        .filter(
            EmployeeDocument.employee_id == employee.id
        )
        .order_by(
            EmployeeDocument.created_at.desc(),
            EmployeeDocument.id.desc(),
        )
        .all()
    )


# ---------------------------------------------------------
# EMPLOYEE DOCUMENTS — UPLOAD
# ---------------------------------------------------------

@router.post(
    "/{employee_id}/documents",
    response_model=EmployeeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_employee_document(
    employee_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = ensure_document_access(
        employee_id=employee_id,
        db=db,
        current_user=current_user,
    )

    (
        original_filename,
        stored_filename,
        content_type,
        size_bytes,
        saved_path,
    ) = await save_employee_document(file)

    document = EmployeeDocument(
        employee_id=employee.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        uploaded_by=current_user.id,
    )

    try:
        db.add(document)
        db.flush()

        record_audit_log(
            db=db,
            actor=current_user,
            action="employee.document_uploaded",
            entity_type="employee_document",
            entity_id=document.id,
            details={
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
                "filename": original_filename,
                "content_type": content_type,
                "size_bytes": size_bytes,
            },
        )

        # Document metadata and audit log are committed together.
        db.commit()
        db.refresh(document)

    except SQLAlchemyError as exc:
        db.rollback()
        remove_saved_file(saved_path)

        logger.exception(
            "Unable to save employee document metadata"
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save employee document metadata",
        ) from exc

    return document


# ---------------------------------------------------------
# EMPLOYEE DOCUMENTS — DOWNLOAD
# ---------------------------------------------------------

@router.get(
    "/documents/{document_id}/download",
)
def download_employee_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = (
        db.query(EmployeeDocument)
        .filter(EmployeeDocument.id == document_id)
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee document not found",
        )

    # Verify that this user is allowed to access the document.
    ensure_document_access(
        employee_id=document.employee_id,
        db=db,
        current_user=current_user,
    )

    # Resolve the server-side path and ensure it stays inside
    # the document storage directory.
    storage_root = DOCUMENTS_DIR.resolve()

    file_path = (
        storage_root / document.stored_filename
    ).resolve()

    if file_path.parent != storage_root:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee document not found",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored employee document is missing",
        )

    return FileResponse(
        path=str(file_path),
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="attachment",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------
# EMPLOYEE: OWN PROFILE
# ---------------------------------------------------------

@router.get(
    "/me",
    response_model=EmployeeResponse,
)
def get_my_employee_record(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = (
        db.query(Employee)
        .filter(Employee.user_id == current_user.id)
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Your employee record has not been created yet"
            ),
        )

    return employee


# ---------------------------------------------------------
# GET EMPLOYEE — ADMIN/HR
# ---------------------------------------------------------

@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    return get_employee_or_404(
        employee_id=employee_id,
        db=db,
    )


# ---------------------------------------------------------
# UPDATE EMPLOYEE — ADMIN/HR
# ---------------------------------------------------------

@router.patch(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    employee = get_employee_or_404(
        employee_id=employee_id,
        db=db,
    )

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    for field, value in changes.items():
        setattr(employee, field, value)

    try:
        record_audit_log(
            db=db,
            actor=current_user,
            action="employee.updated",
            entity_type="employee",
            entity_id=employee.id,
            details={
                "employee_code": employee.employee_code,
                "changed_fields": sorted(changes.keys()),
            },
        )

        db.commit()
        db.refresh(employee)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to update employee record",
        ) from exc

    return employee


# ---------------------------------------------------------
# DEACTIVATE EMPLOYEE — ADMIN/HR
# ---------------------------------------------------------

@router.patch(
    "/{employee_id}/deactivate",
    response_model=EmployeeResponse,
)
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "HR")
    ),
):
    employee = get_employee_or_404(
        employee_id=employee_id,
        db=db,
    )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee is already deactivated",
        )

    user = (
        db.query(User)
        .filter(User.id == employee.user_id)
        .first()
    )

    employee.is_active = False

    if user:
        user.is_active = False

    record_audit_log(
        db=db,
        actor=current_user,
        action="employee.deactivated",
        entity_type="employee",
        entity_id=employee.id,
        details={
            "employee_code": employee.employee_code,
            "login_disabled": user is not None,
        },
    )

    try:
        db.commit()
        db.refresh(employee)

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to deactivate employee",
        ) from exc

    return employee