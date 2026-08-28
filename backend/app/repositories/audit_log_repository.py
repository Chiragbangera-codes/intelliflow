"""
AuditLog repository — database access layer for audit logs.

Audit logs are append-only at the application level.
Only insert and query operations are provided — no update or delete.
"""

import uuid
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
