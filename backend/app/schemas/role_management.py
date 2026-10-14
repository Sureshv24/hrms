from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


RoleName = Literal["Admin", "HR", "Employee"]


class RoleUpdateRequest(BaseModel):
    role: RoleName


class UserRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role: RoleName
    is_active: bool
    created_at: datetime | None = None


class RoleInfo(BaseModel):
    role: RoleName
    description: str