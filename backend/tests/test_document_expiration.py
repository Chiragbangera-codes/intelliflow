"""
Milestone 11 — Document Expiration Background Task Test Suite.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentLifecycleStatus
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.workers.document_tasks import _async_check_document_expirations


@pytest.mark.asyncio
async def test_document_expiration_task(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Expired documents are automatically transitioned by the background task."""
    # 1. Upload doc with expires_at in the past
    past_time = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    res1 = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("expiring_doc.pdf", io.BytesIO(b"content"), "application/pdf")},
        data={"expires_at": past_time},
        headers=auth_headers,
    )
    doc1_id = uuid.UUID(res1.json()["data"]["id"])

    # 2. Upload doc with expires_at in the future
    future_time = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    res2 = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("valid_doc.pdf", io.BytesIO(b"content"), "application/pdf")},
        data={"expires_at": future_time},
        headers=auth_headers,
    )
    doc2_id = uuid.UUID(res2.json()["data"]["id"])

    # 3. Run expiration worker function
    result = await _async_check_document_expirations(db=db_session)
    assert result["status"] == "completed"
    assert result["expired_count"] >= 1
    assert str(doc1_id) in result["document_ids"]

    # 4. Verify document 1 is now EXPIRED
    doc1 = await db_session.get(Document, doc1_id)
    assert doc1.lifecycle_status == DocumentLifecycleStatus.EXPIRED

    # 5. Verify document 2 is still ACTIVE
    doc2 = await db_session.get(Document, doc2_id)
    assert doc2.lifecycle_status == DocumentLifecycleStatus.ACTIVE

    # 6. Verify notification was sent
    notif_repo = NotificationRepository(db_session)
    notifs = await notif_repo.get_all_for_user(test_user.id)
    notif_titles = [n.title for n in notifs]
    assert any("Document Expired" in t for t in notif_titles)
