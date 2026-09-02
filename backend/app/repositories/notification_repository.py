"""
Notification repository — database access layer for the notifications table.

All notification-related database operations are centralised here.
Only this repository communicates with the notifications table for Phase 10 CRUD.

Note: WorkflowRepository.create_notification() is preserved for workflow step
use (Phase 8). This repository handles the full REST API surface introduced in
Phase 10 (list, mark-read, count, delete).

Architecture:
  NotificationService → NotificationRepository → PostgreSQL

Security:
  All queries are scoped to the owning user_id unless the caller explicitly
  requests admin-level access. The service layer enforces which callers may
  request admin-level access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationPriority,
)


class NotificationRepository:
    """Handles all database operations for the notifications table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    # =========================================================================
    # Create
    # =========================================================================

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        message: str,
        channel: NotificationChannel = NotificationChannel.IN_APP,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> Notification:
        """
        Persist a new notification record.

        Args:
            user_id:  UUID of the recipient user.
            title:    Short notification title (max 500 chars, enforced at model).
            message:  Full notification message body.
            channel:  Delivery channel (in_app / email / sms).
            priority: Priority level (low / medium / high / critical).

        Returns:
            The persisted Notification instance with id populated.
        """
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            channel=channel,
            priority=priority,
        )
        self._session.add(notification)
        await self._session.flush()
        await self._session.refresh(notification)
        return notification

    # =========================================================================
    # Read
    # =========================================================================

    async def get_by_id(
        self,
        notification_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
    ) -> Notification | None:
        """
        Return a notification by UUID.

        When user_id is provided the query adds an ownership filter so that
        only the owner's record is returned — cross-user access returns None.
        When user_id is None the query is admin-level (no ownership filter).

        Args:
            notification_id: UUID of the notification.
            user_id:         When set, restrict to this owner.

        Returns:
            The Notification instance, or None if not found / not owned.
        """
        conditions: list[Any] = [Notification.id == notification_id]
        if user_id is not None:
            conditions.append(Notification.user_id == user_id)

        result = await self._session.execute(select(Notification).where(*conditions))
        return result.scalar_one_or_none()

    async def get_all_for_user(
        self,
        user_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
        channel: NotificationChannel | None = None,
    ) -> list[Notification]:
        """
        Return paginated notifications for a specific user.

        Results are ordered newest-first (created_at DESC).

        Args:
            user_id:     Owner's UUID.
            skip:        Records to skip (pagination offset).
            limit:       Max records to return (capped at 100 server-side).
            unread_only: When True, only return notifications where is_read=False.
            channel:     When set, filter by delivery channel.

        Returns:
            List of Notification instances.
        """
        effective_limit = min(max(limit, 1), 100)
        effective_skip = max(skip, 0)

        conditions: list[Any] = [Notification.user_id == user_id]
        if unread_only:
            conditions.append(Notification.is_read.is_(False))
        if channel is not None:
            conditions.append(Notification.channel == channel)

        result = await self._session.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .limit(effective_limit)
            .offset(effective_skip)
        )
        return list(result.scalars().all())

    async def count_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        channel: NotificationChannel | None = None,
    ) -> int:
        """
        Return the total notification count for a user, optionally filtered.

        Args:
            user_id:     Owner's UUID.
            unread_only: When True, count only unread notifications.
            channel:     When set, filter by delivery channel.

        Returns:
            Integer count.
        """
        conditions: list[Any] = [Notification.user_id == user_id]
        if unread_only:
            conditions.append(Notification.is_read.is_(False))
        if channel is not None:
            conditions.append(Notification.channel == channel)

        result = await self._session.execute(
            select(func.count()).select_from(Notification).where(*conditions)
        )
        return result.scalar_one()

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        """
        Return the number of unread notifications for a user.

        Optimised single-column COUNT query — does not load any rows.

        Args:
            user_id: Owner's UUID.

        Returns:
            Integer unread count (0 when there are no unread notifications).
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        return result.scalar_one()

    # =========================================================================
    # Update
    # =========================================================================

    async def mark_as_read(
        self,
        notification_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
    ) -> Notification | None:
        """
        Mark a single notification as read.

        Only the owning user's record is updated (user_id filter prevents
        cross-user mutations).

        Args:
            notification_id: UUID of the notification.
            user_id:         Must match the notification's user_id.

        Returns:
            The updated Notification, or None if not found / not owned.
        """
        await self._session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            .values(
                is_read=True,
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.flush()
        return await self.get_by_id(notification_id, user_id=user_id)

    async def mark_all_as_read(self, user_id: uuid.UUID) -> int:
        """
        Mark all unread notifications for a user as read.

        Args:
            user_id: Owner's UUID.

        Returns:
            Number of rows updated.
        """
        result = await self._session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(
                is_read=True,
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def update_sent_at(
        self,
        notification_id: uuid.UUID,
        sent_at: datetime,
    ) -> None:
        """
        Stamp sent_at after successful email delivery.

        Args:
            notification_id: UUID of the notification.
            sent_at:         UTC datetime of successful delivery.
        """
        await self._session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(
                sent_at=sent_at,
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.flush()

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete(
        self,
        notification_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Hard-delete a notification record.

        When user_id is provided, only the owner's record is deleted.
        When user_id is None (admin path), any record with the given id is deleted.

        Args:
            notification_id: UUID of the notification.
            user_id:         When set, restrict deletion to this owner.

        Returns:
            True if a row was deleted, False if not found.
        """
        from sqlalchemy import delete as sa_delete

        conditions: list[Any] = [Notification.id == notification_id]
        if user_id is not None:
            conditions.append(Notification.user_id == user_id)

        result = await self._session.execute(sa_delete(Notification).where(*conditions))
        await self._session.flush()
        return result.rowcount > 0  # type: ignore[return-value]
