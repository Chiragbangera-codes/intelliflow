"""
Notification Pydantic schemas — Phase 10.

Request and response models for the /api/v1/notifications/* endpoints.

Validation:
  - user_id: valid UUID (required on create)
  - title:   non-empty string, max 500 characters
  - message: non-empty string
  - channel: must be a valid NotificationChannel value
  - priority: must be a valid NotificationPriority value
  - pagination: skip >= 0, limit 1–100

Conventions follow existing Phase 9 schema patterns (see report_schemas.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.notification import NotificationChannel, NotificationPriority

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class NotificationCreate(BaseModel):
    """Request body for POST /api/v1/notifications."""

    user_id: uuid.UUID = Field(
        ...,
        description="UUID of the recipient user.",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Short notification title (max 500 characters).",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Full notification message body.",
    )
    channel: NotificationChannel = Field(
        NotificationChannel.IN_APP,
        description="Delivery channel: in_app | email | sms.",
    )
    priority: NotificationPriority = Field(
        NotificationPriority.MEDIUM,
        description="Priority level: low | medium | high | critical.",
    )

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        """Reject titles that are only whitespace."""
        if not value.strip():
            raise ValueError("title must not be blank.")
        return value

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        """Reject messages that are only whitespace."""
        if not value.strip():
            raise ValueError("message must not be blank.")
        return value


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class NotificationResponse(BaseModel):
    """Single notification record returned by the API."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    message: str
    channel: NotificationChannel
    is_read: bool
    priority: NotificationPriority
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    """Paginated list of notifications with unread count."""

    data: list[NotificationResponse]
    meta: dict[str, int]
    unread_count: int


class NotificationCountResponse(BaseModel):
    """Unread notification count — returned by GET /notifications/count."""

    unread_count: int


class MarkAllReadResponse(BaseModel):
    """Response returned after marking all notifications as read."""

    updated: int
    unread_count: int
