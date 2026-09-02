"""
Milestone 11 — Document AI Intelligence Test Suite.
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.document_chunk import DocumentChunk
from app.models.role import Role
from app.models.user import User, UserStatus
from app.services.vector_store_service import SearchResult as VectorSearchResult


@pytest.mark.asyncio
async def test_document_ai_summary(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Document AI summary retrieves chunks, prompts LLM, and returns cited sources."""
    # 1. Upload document
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("contract.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = uuid.UUID(up_res.json()["data"]["id"])

    # 2. Add text chunks to document
    c1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_number=0,
        content="The agreement is effective from Jan 1 2026.",
    )
    c2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_number=1,
        content="Total fee is $50,000 payable in quarterly installments.",
    )
    db_session.add_all([c1, c2])
    await db_session.commit()

    # 3. Request AI summary with mocked LLM
    with patch("app.services.llm_service.LLMService.generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Executive Summary: Agreement effective Jan 1 2026 with $50k fee."
        res = await async_client.post(
            f"/api/v1/documents/{doc_id}/ai/summary", headers=auth_headers
        )

    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == str(doc_id)
    assert "Executive Summary" in data["summary"]
    assert data["chunks_used"] == 2
    assert len(data["sources"]) == 2


@pytest.mark.asyncio
async def test_document_scoped_ai_chat(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Document-scoped AI chat answers strictly from the document's chunks."""
    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("specs.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = uuid.UUID(up_res.json()["data"]["id"])

    c1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_number=0,
        content="Architecture uses PostgreSQL 16 and Redis 7.",
    )
    db_session.add(c1)
    await db_session.commit()

    with (
        patch(
            "app.services.document_ai_service.embedding_service.embed_text",
            return_value=[0.1] * 384,
        ),
        patch(
            "app.services.document_ai_service.vector_store.search",
            return_value=[VectorSearchResult(chunk_id=c1.id, distance=0.1, rank=1)],
        ),
        patch("app.services.llm_service.LLMService.generate", new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = "The architecture uses PostgreSQL 16 and Redis 7."
        res = await async_client.post(
            f"/api/v1/documents/{doc_id}/ai/chat",
            json={"message": "What database is used?"},
            headers=auth_headers,
        )

    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == str(doc_id)
    assert "PostgreSQL 16" in data["answer"]
    assert len(data["sources"]) >= 1


@pytest.mark.asyncio
async def test_unauthorized_user_blocked_from_document_ai(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
) -> None:
    """Unauthorized user cannot run AI summary or chat on a protected document."""
    role_res = await db_session.execute(select(Role).where(Role.name == "employee"))
    emp_role = role_res.scalar_one()
    other_user = User(
        id=uuid.uuid4(),
        email=f"aiother_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Other",
        last_name="User",
        role_id=emp_role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(other_user)
    await db_session.commit()

    up_res = await async_client.post(
        "/api/v1/documents/upload",
        files={"file": ("secret.pdf", io.BytesIO(b"content"), "application/pdf")},
        headers=auth_headers,
    )
    doc_id = up_res.json()["data"]["id"]

    token_b = create_access_token(subject=str(other_user.id), role="employee")

    sum_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/ai/summary",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert sum_res.status_code == 403

    chat_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/ai/chat",
        json={"message": "What is the secret?"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert chat_res.status_code == 403
