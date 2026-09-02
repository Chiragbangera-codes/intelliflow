"""
Integration Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.integration import IntegrationProvider, IntegrationStatus


class IntegrationCreate(BaseModel):
    """Payload to configure a new integration endpoint."""

    provider: IntegrationProvider
    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    configuration: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] | None = None
    status: IntegrationStatus = IntegrationStatus.ACTIVE


class IntegrationUpdate(BaseModel):
    """Payload to update an existing integration."""

    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    configuration: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    status: IntegrationStatus | None = None


class IntegrationResponse(BaseModel):
    """Integration details without exposing decrypted credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: IntegrationProvider
    name: str
    description: str | None = None
    status: IntegrationStatus
    configuration: dict[str, Any]
    has_credentials: bool = False
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None = None


class IntegrationListResponse(BaseModel):
    """Paginated list of integrations."""

    items: list[IntegrationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class IntegrationTestResponse(BaseModel):
    """Result of testing an integration connection."""

    success: bool
    status_code: int | None = None
    response: str | None = None
    error: str | None = None
    message: str | None = None
