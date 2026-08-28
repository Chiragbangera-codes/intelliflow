"""
Tests for extended admin AI health and observability endpoints (Milestone 7 Phase 14).

Covers GET /api/v1/admin/ai/health and its extended observability fields.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User

pytestmark = pytest.mark.asyncio

_EMPLOYEE = uuid.UUID("00000000-0000-4000-8000-000000000003")


async def _make_document_with_chunks(
    db: AsyncSession,
    owner: User,
    *,
    chunk_texts: list[str],
) -> Document:
    """Create a document with chunks for testing counts."""
    doc = Document(
        file_name=f"test_{uuid.uuid4().hex[:6]}.txt",
        storage_path=f"/s/{uuid.uuid4().hex}",
        file_type="text/plain",
        owner_id=owner.id,
        status=DocumentStatus.PROCESSED,
        ocr_status=OcrStatus.COMPLETED,
    )
    db.add(doc)
    await db.flush()
    for i, text in enumerate(chunk_texts, start=1):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                chunk_number=i,
                content=text,
            )
        )
    await db.commit()
    return doc


# ---------------------------------------------------------------------------
# GET /admin/ai/health extended fields
# ---------------------------------------------------------------------------


async def test_ai_health_admin_returns_200(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Admin can access GET /admin/ai/health."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_ai_health_non_admin_returns_403(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Non-admin user gets 403 from health endpoint."""
    resp = await async_client.get("/api/v1/admin/ai/health", headers=auth_headers)
    assert resp.status_code == 403


async def test_ai_health_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Unauthenticated request gets 401."""
    resp = await async_client.get("/api/v1/admin/ai/health")
    assert resp.status_code == 401


async def test_ai_health_healthy_when_consistent(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """status='healthy' when no missing embeddings and index is consistent."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    data = resp.json()["data"]
    assert data["status"] == "healthy"
    assert data["faiss_loaded"] is True
    assert data["consistent"] is True


async def test_ai_health_response_has_all_extended_fields(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Health response contains all expected observability fields."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    data = resp.json()["data"]
    for field in (
        "status",
        "faiss_loaded",
        "faiss_vectors",
        "consistent",
        "missing_embeddings",
        "documents_with_chunks",
        "embedding_model",
        "vector_dimension",
        "reranker_enabled",
        "hybrid_enabled",
        "rrf_k",
        "semantic_multiplier",
        "max_candidates",
        "lexical_candidates",
    ):
        assert field in data, f"Missing field: {field}"


async def test_ai_health_embedding_model_matches_config(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """embedding_model in response matches settings.EMBEDDING_MODEL."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["embedding_model"] == settings.EMBEDDING_MODEL


async def test_ai_health_vector_dimension_is_384(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """vector_dimension is always 384 (all-MiniLM-L6-v2)."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    assert resp.json()["data"]["vector_dimension"] == 384


async def test_ai_health_config_fields_match_settings(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """RRF/hybrid/reranker config fields match the runtime settings."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    data = resp.json()["data"]
    assert data["rrf_k"] == settings.AI_RRF_K
    assert data["hybrid_enabled"] == settings.AI_HYBRID_ENABLED
    assert data["reranker_enabled"] == settings.AI_RERANK_ENABLED
    assert data["semantic_multiplier"] == settings.AI_SEMANTIC_CANDIDATE_MULTIPLIER
    assert data["max_candidates"] == settings.AI_MAX_RETRIEVAL_CANDIDATES
    assert data["lexical_candidates"] == settings.AI_LEXICAL_CANDIDATES


async def test_ai_health_faiss_vectors_reflects_count(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """faiss_vectors in health matches the vector_store count."""
    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 42
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    assert resp.json()["data"]["faiss_vectors"] == 42


async def test_ai_health_documents_with_chunks_count(
    async_client: AsyncClient,
    admin_user: User,
    admin_headers: dict,
    db_session: AsyncSession,
) -> None:
    """documents_with_chunks reflects the actual number of docs with chunks."""
    await _make_document_with_chunks(db_session, admin_user, chunk_texts=["Hello"])
    await _make_document_with_chunks(db_session, admin_user, chunk_texts=["World"])

    with patch("app.api.v1.admin.vector_store") as mock_vs:
        mock_vs.ensure_loaded = MagicMock()
        mock_vs.vector_count = 0
        mock_vs.is_loaded = True
        resp = await async_client.get("/api/v1/admin/ai/health", headers=admin_headers)
    assert resp.json()["data"]["documents_with_chunks"] >= 2
