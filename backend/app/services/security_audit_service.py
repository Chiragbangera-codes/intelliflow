"""
Security Audit Service — centralized security event logging, metadata sanitization, and querying.

Enforces:
  - Strict metadata sanitization (redacting passwords, tokens, secrets, JWTs, file bytes)
  - Standardized severity levels (info, warning, critical)
  - Multi-dimensional query & aggregate statistics for Admin Security Dashboard
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.security import (
    SecurityEventItem,
    SecurityEventListResponse,
    SecurityEventPagination,
    SecuritySeverity,
    SecuritySummaryData,
    SecuritySummaryResponse,
)

logger = logging.getLogger(__name__)

# Sensitive key patterns that must ALWAYS be sanitized before persistence or display
_SENSITIVE_KEY_SUBSTRINGS = {
    "password",
    "token",
    "secret",
    "jwt",
    "hash",
    "refresh",
    "authorization",
    "smtp_password",
    "api_key",
    "credentials",
    "raw_content",
    "file_bytes",
}


def sanitize_security_metadata(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and values to prevent secret leakage.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(sub in k_lower for sub in _SENSITIVE_KEY_SUBSTRINGS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_security_metadata(v)
        return sanitized
    elif isinstance(data, list | tuple | set):
        return [sanitize_security_metadata(item) for item in data]
    return data


class SecurityAuditService:
    """
    Centralized service for logging, sanitizing, and retrieving security audit events.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit_repo = AuditLogRepository(session)
        self._token_repo = RefreshTokenRepository(session)

    async def log_security_event(
        self,
        *,
        action: str,
        severity: SecuritySeverity = SecuritySeverity.INFO,
        user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
        resource_type: str | None = None,
        resource_id: uuid.UUID | str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """
        Record a sanitized security-sensitive event.
        """
        safe_details = sanitize_security_metadata(details or {})
        rec_id = None
        if resource_id:
            try:
                rec_id = uuid.UUID(str(resource_id))
            except ValueError:
                rec_id = None

        new_value = {
            "severity": severity.value,
            "status": status,
            "user_agent": (user_agent or "")[:255] if user_agent else None,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "details": safe_details,
        }

        log = await self._audit_repo.create(
            action=action,
            user_id=user_id,
            table_name=resource_type or "security_events",
            record_id=rec_id,
            new_value=new_value,
            ip_address=(ip_address or "")[:45] if ip_address else None,
        )

        logger.info(
            "Security event recorded: action=%s severity=%s user_id=%s status=%s ip=%s",
            action,
            severity.value,
            user_id,
            status,
            ip_address,
        )
        return log

    async def get_security_events(
        self,
        *,
        action: str | None = None,
        user_id: uuid.UUID | None = None,
        severity: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SecurityEventListResponse:
        """
        Retrieve paginated, sanitized security events with multi-dimensional filtering.
        """
        logs, total_count = await self._audit_repo.search_security_events(
            action=action,
            user_id=user_id,
            severity=severity,
            status=status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

        items: list[SecurityEventItem] = []
        for log in logs:
            nv = log.new_value or {}
            items.append(
                SecurityEventItem(
                    id=log.id,
                    action=log.action,
                    severity=nv.get("severity", "info"),
                    user_id=log.user_id,
                    user_email=log.user.email if log.user else None,
                    ip_address=log.ip_address,
                    user_agent=nv.get("user_agent"),
                    status=nv.get("status", "success"),
                    resource_type=nv.get("resource_type") or log.table_name,
                    resource_id=nv.get("resource_id")
                    or (str(log.record_id) if log.record_id else None),
                    details=nv.get("details", {}),
                    created_at=log.created_at,
                )
            )

        total_pages = max(1, math.ceil(total_count / max(1, page_size)))

        return SecurityEventListResponse(
            success=True,
            data=items,
            pagination=SecurityEventPagination(
                page=page,
                page_size=page_size,
                total_items=total_count,
                total_pages=total_pages,
            ),
        )

    async def get_security_summary(self) -> SecuritySummaryResponse:
        """
        Retrieve 24h security overview metrics for admin monitoring.
        """
        metrics = await self._audit_repo.get_security_summary_metrics()

        # Count active unrevoked refresh token sessions
        from datetime import UTC, datetime

        from sqlalchemy import func, select

        from app.models.refresh_token import RefreshToken

        active_sess_stmt = select(func.count(RefreshToken.id)).where(
            RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > datetime.now(UTC)
        )
        active_sessions = int((await self._session.execute(active_sess_stmt)).scalar_one())

        data = SecuritySummaryData(
            total_events=metrics.get("total_events", 0),
            failed_logins_24h=metrics.get("failed_logins_24h", 0),
            rate_limit_exceeded_24h=metrics.get("rate_limit_exceeded_24h", 0),
            unauthorized_attempts_24h=metrics.get("unauthorized_attempts_24h", 0),
            critical_events_24h=metrics.get("critical_events_24h", 0),
            token_reuse_detected_24h=metrics.get("token_reuse_detected_24h", 0),
            active_sessions_count=active_sessions,
        )

        return SecuritySummaryResponse(success=True, data=data)
