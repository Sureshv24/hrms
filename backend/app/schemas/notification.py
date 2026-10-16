from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


NotificationCategory = Literal[
    "leave",
    "payroll",
    "attendance",
    "announcement",
    "admin",
    "system",
]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_user_id: int
    title: str
    message: str
    category: str
    is_read: bool
    read_at: datetime | None
    created_by_user_id: int | None
    source_entity_type: str | None
    source_entity_id: str | None
    created_at: datetime


class NotificationPreferenceUpdate(BaseModel):
    category: NotificationCategory
    enabled: bool


class NotificationPreferenceResponse(BaseModel):
    category: NotificationCategory
    enabled: bool


class NotificationBroadcastRequest(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=1, max_length=5000)
    category: Literal["announcement", "admin"] = "announcement"
    department: str | None = Field(default=None, max_length=100)
