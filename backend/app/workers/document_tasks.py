"""
Celery background tasks for Document Intelligence (Milestone 11).

Tasks:
  1. tasks.check_document_expirations()
     Finds active documents whose expires_at timestamp has passed, transitions them
     to 'expired', logs audit events, and sends notifications to owners.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.document import DocumentLifecycleStatus
from app.models.notification import NotificationChannel, NotificationPriority
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.notification_repository import NotificationRepository
from app.workers.celery_app import celery_app
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)


async def _async_check_document_expirations(
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Find and expire active documents whose expires_at timestamp has passed."""

    async def _run(session: AsyncSession) -> dict[str, Any]:
        doc_repo = DocumentRepository(session)
        audit_repo = AuditLogRepository(session)

        expired_docs = await doc_repo.get_expired_active_documents(limit=500)
        if not expired_docs:
            return {"expired_count": 0, "status": "no_expired_documents"}

        logger.info("Found %d expired documents to transition.", len(expired_docs))
        transitioned_ids: list[str] = []

        notif_repo = NotificationRepository(session)

        for doc in expired_docs:
            await doc_repo.update_lifecycle_status(doc.id, DocumentLifecycleStatus.EXPIRED)
            transitioned_ids.append(str(doc.id))

            # Audit event
            await audit_repo.create(
                action="document.expired",
                user_id=doc.owner_id,
                table_name="documents",
                record_id=doc.id,
                new_value={"lifecycle_status": "expired", "expires_at": str(doc.expires_at)},
            )

            # Notification
            try:
                await notif_repo.create(
                    user_id=doc.owner_id,
                    title="Document Expired",
                    message=f"Document '{doc.display_name}' has reached its expiration date ({doc.expires_at.strftime('%Y-%m-%d') if doc.expires_at else 'passed'}) and is now expired.",
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.MEDIUM,
                )
            except Exception as notif_exc:
                logger.warning(
                    "Failed to send expiration notification for doc %s: %s", doc.id, notif_exc
                )

        await session.commit()
        logger.info("Successfully expired %d documents.", len(transitioned_ids))
        return {
            "expired_count": len(transitioned_ids),
            "document_ids": transitioned_ids,
            "status": "completed",
        }

    if db is not None:
        return await _run(db)

    async with AsyncSessionLocal() as session:
        return await _run(session)


@celery_app.task(
    name="tasks.check_document_expirations",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)
def check_document_expirations_task(self: Any) -> dict[str, Any]:
    """Celery task entrypoint for checking and transitioning expired documents."""
    logger.info("Executing Celery task check_document_expirations (id=%s)", self.request.id)
    return run_in_worker(_async_check_document_expirations())
