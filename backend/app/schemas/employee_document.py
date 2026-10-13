from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmployeeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_by: int | None
    created_at: datetime