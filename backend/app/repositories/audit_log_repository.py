"""
AuditLog repository — database access layer for audit logs.

Audit logs are append-only at the application level.
Only insert and query operations are provided — no update or delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogRepository:
    """Handles all database operations for the audit_logs table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def create(
        self,
        *,
        action: str,
        user_id: uuid.UUID | None = None,
        table_name: str | None = None,
        record_id: uuid.UUID | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """
        Insert a new audit log entry.

        Args:
            action:     Short action descriptor (e.g. 'user.login').
            user_id:    UUID of the user who performed the action. None for system events.
            table_name: Database table affected by the action.
            record_id:  UUID of the affected record (no FK — cross-table reference).
            old_value:  Previous state as a dict (stored as JSONB).
            new_value:  New state as a dict (stored as JSONB).
            ip_address: IPv4 or IPv6 address of the request.

        Returns:
            The persisted AuditLog instance.
        """
        log = AuditLog(
            action=action,
            user_id=user_id,
            table_name=table_name,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
        )
        self._session.add(log)
        await self._session.flush()
        await self._session.refresh(log)
        return log

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AuditLog]:
        """
        Return audit log entries for a specific user.

        Args:
            user_id: The user's UUID.
            limit:   Maximum records to return (default 20, max 100).
            offset:  Pagination offset.

        Returns:
            List of AuditLog instances ordered by created_at descending.
        """
        effective_limit = min(limit, 100)
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_table(
        self,
        table_name: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AuditLog]:
        """
        Return audit log entries for a specific table.

        Args:
            table_name: Name of the database table.
            limit:      Maximum records to return (default 20, max 100).
            offset:     Pagination offset.

        Returns:
            List of AuditLog instances ordered by created_at descending.
        """
        effective_limit = min(limit, 100)
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.table_name == table_name)
            .order_by(AuditLog.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def search_security_events(
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
    ) -> tuple[list[AuditLog], int]:
        """
        Search and paginate audit and security events with multi-dimensional filtering.

        Returns:
            Tuple of (list of matching AuditLog instances, total matching count).
        """
        from sqlalchemy import func
        from sqlalchemy.orm import selectinload

        stmt = select(AuditLog).options(selectinload(AuditLog.user))
        count_stmt = select(func.count(AuditLog.id))

        filters = []
        if action:
            filters.append(AuditLog.action.ilike(f"%{action}%"))
        if user_id:
            filters.append(AuditLog.user_id == user_id)
        if start_date:
            filters.append(AuditLog.created_at >= start_date)
        if end_date:
            filters.append(AuditLog.created_at <= end_date)

        # Filter by severity or status within new_value JSON
        # For cross-DB compatibility (SQLite + PostgreSQL), we filter JSON at SQL or application level if needed
        if filters:
            for f in filters:
                stmt = stmt.where(f)
                count_stmt = count_stmt.where(f)

        # Count total
        total_count = int((await self._session.execute(count_stmt)).scalar_one())

        # Paginate
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(page_size).offset(offset)
        result = await self._session.execute(stmt)
        items = list(result.scalars().all())

        # Post-filter on in-memory JSON fields if severity or status was specified
        if severity:
            items = [
                item
                for item in items
                if (item.new_value and item.new_value.get("severity") == severity.lower())
                or (not item.new_value and severity.lower() == "info")
            ]
        if status:
            items = [
                item
                for item in items
                if item.new_value and item.new_value.get("status") == status.lower()
            ]

        return items, total_count

    async def get_security_summary_metrics(self) -> dict[str, int]:
        """
        Calculate 24-hour aggregate metrics for security dashboards.
        """
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import func

        since = datetime.now(UTC) - timedelta(hours=24)

        # Count total events in last 24h
        total_stmt = select(func.count(AuditLog.id)).where(AuditLog.created_at >= since)
        total_events = int((await self._session.execute(total_stmt)).scalar_one())

        # Fetch 24h logs for categorization
        stmt = select(AuditLog).where(AuditLog.created_at >= since)
        logs = list((await self._session.execute(stmt)).scalars().all())

        failed_logins = 0
        rate_limits = 0
        unauthorized = 0
        critical = 0
        token_reuse = 0

        for log in logs:
            action = (log.action or "").lower()
            nv = log.new_value or {}
            sev = (nv.get("severity") or "info").lower()

            if "login_failed" in action or "auth.failed" in action:
                failed_logins += 1
            if "rate_limit" in action:
                rate_limits += 1
            if "unauthorized" in action or "forbidden" in action or "access_denied" in action:
                unauthorized += 1
            if "reuse_detected" in action:
                token_reuse += 1
            if sev == "critical" or "reuse" in action:
                critical += 1

        return {
            "total_events": total_events,
            "failed_logins_24h": failed_logins,
            "rate_limit_exceeded_24h": rate_limits,
            "unauthorized_attempts_24h": unauthorized,
            "critical_events_24h": critical,
            "token_reuse_detected_24h": token_reuse,
        }
