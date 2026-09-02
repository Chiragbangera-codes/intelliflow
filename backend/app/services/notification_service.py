"""
Notification service — business logic for Phase 10 notifications.

Architecture:
  API → NotificationService → NotificationRepository → PostgreSQL
                            ↘ smtplib (for email channel, synchronous)

RBAC:
  - Admin / Manager: may create notifications for any user.
  - HR / Finance / Employee: may NOT create notifications.
  - Any authenticated user: may list, read, and delete their OWN notifications.
  - Admin: may additionally retrieve and delete any user's notification.
  - Only the owner may mark a notification as read (mark_read / mark_all_read).

Email delivery:
  When channel == NotificationChannel.EMAIL:
    1. Notification record is persisted first (preserves database integrity).
    2. The recipient's email address is resolved from the database.
    3. SMTP delivery is attempted using settings.SMTP_* configuration.
    4. On success: sent_at is stamped on the record and an audit event is logged.
    5. On SMTP failure: the notification record remains but sent_at stays NULL;
       an audit event "notification.email_failed" is logged.
    If SMTP_HOST is not configured, the step is documented and the notification
    is persisted without delivery (same safe-fallback as the workflow email step).

SMS channel:
  No SMS provider is configured. The notification record is persisted normally
  (channel=sms) but no external delivery is attempted. A warning is logged.

Security:
  - SMTP credentials are never logged or returned to callers.
  - Recipient email is resolved server-side; the caller cannot inject an
    arbitrary target address.
  - Notification content is never rendered as HTML in delivery (plain text only).
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import NotificationChannel
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationCountResponse,
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
)

logger = logging.getLogger(__name__)

# Roles permitted to create notifications for other users
_CREATE_ROLES = frozenset({"admin", "manager"})

# Roles permitted to access any user's notification (admin-level read/delete)
_ADMIN_ROLES = frozenset({"admin"})


def _role_name(actor: User) -> str:
    """Return the actor's role name safely in lowercase."""
    if actor.role and hasattr(actor.role, "name") and actor.role.name:
        return actor.role.name.lower()
    return str(getattr(actor, "role", "employee")).lower()


class NotificationService:
    """Business logic for the notification lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject database session."""
        self._session = session
        self._repo = NotificationRepository(session)
        self._audit = AuditLogRepository(session)
        self._user_repo = UserRepository(session)

    # =========================================================================
    # Create
    # =========================================================================

    async def create_notification(
        self,
        payload: NotificationCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> NotificationResponse:
        """
        Create and optionally deliver a notification.

        Only Admin and Manager roles may create notifications for other users.

        Args:
            payload:    Validated request body (user_id, title, message, channel, priority).
            actor:      Authenticated user performing the action.
            ip_address: Request IP for audit logging.

        Raises:
            HTTPException 403: Insufficient role.
            HTTPException 404: Recipient user not found.

        Returns:
            NotificationResponse for the created record.
        """
        if _role_name(actor) not in _CREATE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Admin and Manager roles may create notifications.",
            )

        # Resolve recipient — validates the target user exists
        recipient = await self._user_repo.get_by_id(payload.user_id)
        if recipient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recipient user {payload.user_id} not found.",
            )

        # Persist the notification record first (DB integrity before delivery)
        notification = await self._repo.create(
            user_id=payload.user_id,
            title=payload.title,
            message=payload.message,
            channel=payload.channel,
            priority=payload.priority,
        )
        await self._session.commit()

        # Audit: notification created
        await self._audit.create(
            action="notification.created",
            user_id=actor.id,
            table_name="notifications",
            record_id=notification.id,
            new_value={
                "channel": payload.channel.value,
                "priority": payload.priority.value,
                "recipient_id": str(payload.user_id),
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        # Channel-specific delivery
        if payload.channel == NotificationChannel.EMAIL:
            await self._deliver_email(
                notification_id=notification.id,
                to_email=recipient.email,
                subject=payload.title,
                body=payload.message,
                actor=actor,
                ip_address=ip_address,
            )
        elif payload.channel == NotificationChannel.SMS:
            logger.warning(
                "SMS delivery is not configured. Notification %s persisted "
                "with channel=sms but no message was sent.",
                notification.id,
            )

        # Refresh to get the latest sent_at if email was delivered
        await self._session.refresh(notification)
        return NotificationResponse.model_validate(notification)

    # =========================================================================
    # List
    # =========================================================================

    async def list_notifications(
        self,
        *,
        actor: User,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
        channel: NotificationChannel | None = None,
    ) -> NotificationListResponse:
        """
        Return paginated notifications for the authenticated user.

        Args:
            actor:       Authenticated user (sees only their own notifications).
            skip:        Pagination offset.
            limit:       Max records (capped at 100).
            unread_only: When True, return only unread notifications.
            channel:     When set, filter by delivery channel.

        Returns:
            NotificationListResponse with data, meta, and unread_count.
        """
        limit = min(max(limit, 1), 100)
        skip = max(skip, 0)

        records = await self._repo.get_all_for_user(
            actor.id,
            skip=skip,
            limit=limit,
            unread_only=unread_only,
            channel=channel,
        )
        total = await self._repo.count_for_user(
            actor.id,
            unread_only=unread_only,
            channel=channel,
        )
        unread_count = await self._repo.get_unread_count(actor.id)

        total_pages = max(1, math.ceil(total / limit))
        page = (skip // limit) + 1 if limit > 0 else 1

        return NotificationListResponse(
            data=[NotificationResponse.model_validate(r) for r in records],
            meta={
                "skip": skip,
                "limit": limit,
                "total_items": total,
                "total_pages": total_pages,
                "page": page,
            },
            unread_count=unread_count,
        )

    # =========================================================================
    # Get single
    # =========================================================================

    async def get_notification(
        self,
        notification_id: uuid.UUID,
        *,
        actor: User,
    ) -> NotificationResponse:
        """
        Return a notification by ID.

        Admin may retrieve any notification. Other roles may only retrieve
        their own notifications.

        Raises:
            HTTPException 404: Not found or not accessible.
        """
        if _role_name(actor) in _ADMIN_ROLES:
            record = await self._repo.get_by_id(notification_id)
        else:
            record = await self._repo.get_by_id(notification_id, user_id=actor.id)

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )
        return NotificationResponse.model_validate(record)

    # =========================================================================
    # Mark read
    # =========================================================================

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> NotificationResponse:
        """
        Mark a single notification as read.

        Only the owner may mark their notification as read.

        Raises:
            HTTPException 404: Not found or not owned.
        """
        # First verify the notification belongs to this user
        record = await self._repo.get_by_id(notification_id, user_id=actor.id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )

        updated = await self._repo.mark_as_read(notification_id, user_id=actor.id)
        await self._session.commit()

        await self._audit.create(
            action="notification.read",
            user_id=actor.id,
            table_name="notifications",
            record_id=notification_id,
            ip_address=ip_address,
        )
        await self._session.commit()

        assert updated is not None
        return NotificationResponse.model_validate(updated)

    async def mark_all_read(
        self,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> MarkAllReadResponse:
        """
        Mark all of the actor's unread notifications as read.

        Returns:
            MarkAllReadResponse containing the count of updated rows.
        """
        updated_count = await self._repo.mark_all_as_read(actor.id)
        await self._session.commit()

        await self._audit.create(
            action="notification.read_all",
            user_id=actor.id,
            table_name="notifications",
            new_value={"updated": updated_count},
            ip_address=ip_address,
        )
        await self._session.commit()

        remaining = await self._repo.get_unread_count(actor.id)
        return MarkAllReadResponse(updated=updated_count, unread_count=remaining)

    # =========================================================================
    # Unread count
    # =========================================================================

    async def get_unread_count(self, *, actor: User) -> NotificationCountResponse:
        """
        Return the unread notification count for the actor.

        Each user only sees their own count — no cross-user leakage.
        """
        count = await self._repo.get_unread_count(actor.id)
        return NotificationCountResponse(unread_count=count)

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete_notification(
        self,
        notification_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """
        Delete a notification.

        Admin may delete any notification.
        Other roles may only delete their own notifications.

        Raises:
            HTTPException 404: Not found or not owned.
        """
        # Verify existence (and ownership for non-admin)
        if _role_name(actor) in _ADMIN_ROLES:
            record = await self._repo.get_by_id(notification_id)
        else:
            record = await self._repo.get_by_id(notification_id, user_id=actor.id)

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )

        # Audit before deletion (record_id preserved in audit log)
        await self._audit.create(
            action="notification.deleted",
            user_id=actor.id,
            table_name="notifications",
            record_id=notification_id,
            old_value={
                "title": record.title,
                "channel": record.channel.value,
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        # Delete — admin path passes user_id=None to skip ownership filter
        owner_id = None if _role_name(actor) in _ADMIN_ROLES else actor.id
        await self._repo.delete(notification_id, user_id=owner_id)
        await self._session.commit()

    # =========================================================================
    # Internal — Email delivery
    # =========================================================================

    async def _deliver_email(
        self,
        notification_id: uuid.UUID,
        to_email: str,
        subject: str,
        body: str,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """
        Attempt SMTP email delivery for an email-channel notification.

        On success: stamps sent_at on the notification record.
        On failure: logs the error and records a notification.email_failed
                    audit event. The notification record is preserved.

        Security:
          - SMTP credentials are read from settings, never from the request.
          - Only safe error type names are logged/audited (no credentials).
          - 'to_email' was resolved from the DB, not supplied by the caller.
        """
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        if not settings.SMTP_HOST:
            logger.warning(
                "Email notification %s not delivered: SMTP_HOST is not configured. "
                "Set SMTP_HOST in environment to enable email delivery.",
                notification_id,
            )
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        try:
            if settings.SMTP_USE_TLS:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                    smtp.starttls()
                    if settings.SMTP_USER:
                        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    smtp.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                    if settings.SMTP_USER:
                        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    smtp.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())

            # Stamp sent_at
            await self._repo.update_sent_at(notification_id, datetime.now(UTC))
            await self._session.commit()

            await self._audit.create(
                action="notification.email_sent",
                user_id=actor.id,
                table_name="notifications",
                record_id=notification_id,
                ip_address=ip_address,
            )
            await self._session.commit()

            logger.info(
                "Email notification %s delivered successfully.",
                notification_id,
            )

        except smtplib.SMTPException as exc:
            # Log only the error type — never the recipient or credentials
            logger.error(
                "Email notification %s SMTP delivery failed: %s",
                notification_id,
                type(exc).__name__,
            )
            await self._audit.create(
                action="notification.email_failed",
                user_id=actor.id,
                table_name="notifications",
                record_id=notification_id,
                new_value={"error": type(exc).__name__},
                ip_address=ip_address,
            )
            try:
                await self._session.commit()
            except Exception:  # noqa: BLE001
                pass
