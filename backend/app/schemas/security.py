"""
Pydantic schemas for Security Events, Auditing, and Session Management.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SecuritySeverity(str, Enum):
    """Severity classification for security events."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SecurityEventItem(BaseModel):
    """Sanitized security event representation."""

    id: uuid.UUID
    action: str
    severity: str = "info"
    user_id: uuid.UUID | None = None
    user_email: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    status: str = "success"  # "success" | "failure"
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SecurityEventPagination(BaseModel):
    """Pagination metadata for security event queries."""

    page: int
    page_size: int
    total_items: int
    total_pages: int


class SecurityEventListResponse(BaseModel):
    """Response envelope for paginated security events."""

    success: bool = True
    data: list[SecurityEventItem]
    pagination: SecurityEventPagination


class SecuritySummaryData(BaseModel):
    """Aggregated security metrics over recent time windows."""

    total_events: int
    failed_logins_24h: int
    rate_limit_exceeded_24h: int
    unauthorized_attempts_24h: int
    critical_events_24h: int
    token_reuse_detected_24h: int
    active_sessions_count: int


class SecuritySummaryResponse(BaseModel):
    """Response envelope for security summary metrics."""

    success: bool = True
    data: SecuritySummaryData


class ActiveSessionItem(BaseModel):
    """Metadata representation of an active user session / refresh token."""

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


class ActiveSessionListResponse(BaseModel):
    """Response envelope for active user sessions."""

    success: bool = True
    data: list[ActiveSessionItem]
