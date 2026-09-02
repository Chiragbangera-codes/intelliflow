"""
Phase 3.1 — Durability tests for the AI retrieval pipeline.

Covers the three durability features added in the "durability-first" scope. Each
one exists to stop the "chunks exist but embeddings are missing → FAISS empty →
every answer falls back" failure from recurring silently:

  1. Admin reindex endpoint — POST /api/v1/admin/ai/reindex
       401 unauthenticated · 403 non-admin · 202 admin (task dispatched) ·
       503 when broker dispatch fails, with NO internal detail leaked.

  2. Admin index-status endpoint — GET /api/v1/admin/ai/index-status
       403 non-admin · 200 admin · correctly surfaces the
       "chunks without embeddings" gap and the healthy/consistent state.

  3. ReindexService — reindex_all_embeddings()
       heals a document that has chunks but no embeddings, and is idempotent
       (a second run yields the same vector count and one embedding per chunk —
       never duplicates).

  4. AI_MIN_RETRIEVAL_SCORE config default (Phase 7)
       filters low-similarity chunks when a request supplies no min_score;
       an explicit per-request min_score overrides the config default;
       None (the default) disables filtering entirely.

Every FAISS / embedding / broker call is mocked. No Ollama, no real embedding
model, and no live Celery broker are required to run this module.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_embedding import AIEmbedding
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.repositories.ai_embedding_repository import AIEmbeddingRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.reindex_service import reindex_all_embeddings
from app.services.search_service import SearchService
from app.services.vector_store_service import SearchResult as VSSearchResult
from app.services.vector_store_service import VectorStoreService

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EMBED_DIM = 384
_FAKE_VECTOR = [0.1] * EMBED_DIM


class _FakeIndex:
    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.ntotal = 0

    def add(self, arr: Any) -> None:
        self.ntotal += len(arr)

    def search(self, arr: Any, k: int) -> tuple[Any, Any]:
        return [], []


class _FakeFaiss:
    IndexFlatL2 = _FakeIndex

    @staticmethod
    def write_index(idx: Any, path: str | Path) -> None:
        Path(path).write_bytes(b"FAISS_MOCK")

    @staticmethod
    def read_index(path: str | Path) -> _FakeIndex:
        return _FakeIndex(EMBED_DIM)


def _make_svc(tmp_path: Path) -> VectorStoreService:
    """Return a VectorStoreService whose on-disk paths live under tmp_path."""
    svc = VectorStoreService()

    def _safe_import_faiss(self: Any) -> Any:
        try:
            import faiss

            return faiss
        except ImportError:
            return _FakeFaiss()

    svc.__class__ = type(
        "PatchedVSS",
        (VectorStoreService,),
        {
            "_index_path": property(lambda self: tmp_path / "index.faiss"),
            "_mapping_path": property(lambda self: tmp_path / "index_mapping.json"),
            "_import_faiss": _safe_import_faiss,
        },
    )
    return svc


async def _make_document(
    db: AsyncSession,
    owner: User,
    *,
    chunk_texts: list[str],
    with_embeddings: bool = False,
    file_name: str = "durability.pdf",
) -> Document:
    """
    Create a PROCESSED/COMPLETED document with chunks (and optionally embeddings).

    with_embeddings=False reproduces the exact broken state the durability work
    guards against: a fully-OCR'd document whose chunks never got embedded.
    """
    doc = Document(
        file_name=file_name,
        file_type="application/pdf",
        file_size=1234,
        storage_path=f"test/{uuid.uuid4().hex}.pdf",
        owner_id=owner.id,
        status=DocumentStatus.PROCESSED,
        ocr_status=OcrStatus.COMPLETED,
    )
    db.add(doc)
    await db.flush()

    chunk_repo = DocumentChunkRepository(db)
    chunks = await chunk_repo.save_chunks(doc.id, chunk_texts)

    if with_embeddings:
        emb_repo = AIEmbeddingRepository(db)
        for chunk in chunks:
            await emb_repo.create(
                document_chunk_id=chunk.id,
                vector_reference=str(chunk.id),
                embedding_model=settings.EMBEDDING_MODEL,
            )

    await db.commit()
    return doc


# ===========================================================================
# 1. POST /api/v1/admin/ai/reindex
# ===========================================================================


@pytest.mark.asyncio
class TestReindexEndpoint:
    """RBAC + dispatch behaviour of the admin reindex endpoint."""

    _URL = "/api/v1/admin/ai/reindex"

    async def test_requires_authentication(self, async_client: AsyncClient) -> None:
        """No token → 401 (auth is checked before role)."""
        resp = await async_client.post(self._URL)
        assert resp.status_code == 401

    async def test_forbidden_for_employee(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """An authenticated employee must never reach the reindex machinery."""
        resp = await async_client.post(self._URL, headers=auth_headers)
        assert resp.status_code == 403

    async def test_dispatches_for_admin(
        self, async_client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        """Admin → 202 with the dispatched Celery task id; no work runs inline."""
        fake_task = MagicMock()
        fake_task.id = "task-abc-123"
        with patch("app.api.v1.admin.celery_app.send_task", return_value=fake_task) as mock_send:
            resp = await async_client.post(self._URL, headers=admin_headers)

        assert resp.status_code == 202
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["task_id"] == "task-abc-123"
        assert body["data"]["status"] == "accepted"
        mock_send.assert_called_once_with("tasks.reindex_all_embeddings")

    async def test_dispatch_failure_returns_503_without_leak(
        self, async_client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        """A broker failure returns 503 and leaks NO internal detail to the client."""
        with patch(
            "app.api.v1.admin.celery_app.send_task",
            side_effect=RuntimeError("broker down: amqp://user:secret@rabbit:5672"),
        ):
            resp = await async_client.post(self._URL, headers=admin_headers)

        assert resp.status_code == 503
        body = resp.json()
        assert body["success"] is False
        # The raw exception text / broker URL / credentials must not surface.
        text = resp.text.lower()
        assert "secret" not in text
        assert "amqp" not in text
        assert "broker down" not in text
        assert "traceback" not in text


# ===========================================================================
# 2. GET /api/v1/admin/ai/index-status
# ===========================================================================


@pytest.mark.asyncio
class TestIndexStatusEndpoint:
    """RBAC + consistency reporting of the index-status endpoint."""

    _URL = "/api/v1/admin/ai/index-status"

    async def test_forbidden_for_employee(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resp = await async_client.get(self._URL, headers=auth_headers)
        assert resp.status_code == 403

    async def test_empty_index_is_consistent(
        self, async_client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        """No documents at all → everything zero → consistent is True."""
        with patch("app.api.v1.admin.vector_store") as mock_vs:
            mock_vs.vector_count = 0
            resp = await async_client.get(self._URL, headers=admin_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {
            "chunks": 0,
            "embeddings": 0,
            "faiss_vectors": 0,
            "missing_embeddings": 0,
            "consistent": True,
        }

    async def test_detects_missing_embeddings(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        admin_user: User,
        db_session: AsyncSession,
    ) -> None:
        """Chunks present, embeddings absent → missing_embeddings>0, inconsistent."""
        await _make_document(
            db_session, admin_user, chunk_texts=["a", "b", "c"], with_embeddings=False
        )
        with patch("app.api.v1.admin.vector_store") as mock_vs:
            mock_vs.vector_count = 0
            resp = await async_client.get(self._URL, headers=admin_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["chunks"] == 3
        assert data["embeddings"] == 0
        assert data["missing_embeddings"] == 3
        assert data["consistent"] is False

    async def test_consistent_with_data(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        admin_user: User,
        db_session: AsyncSession,
    ) -> None:
        """chunks == embeddings == faiss_vectors and nothing missing → consistent."""
        await _make_document(db_session, admin_user, chunk_texts=["a", "b"], with_embeddings=True)
        with patch("app.api.v1.admin.vector_store") as mock_vs:
            mock_vs.vector_count = 2
            resp = await async_client.get(self._URL, headers=admin_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["chunks"] == 2
        assert data["embeddings"] == 2
        assert data["faiss_vectors"] == 2
        assert data["missing_embeddings"] == 0
        assert data["consistent"] is True


# ===========================================================================
# 3. ReindexService — reindex_all_embeddings()
# ===========================================================================


@pytest.mark.asyncio
class TestReindexService:
    """The heal-everything operation: correctness + idempotence."""

    async def test_heals_document_missing_embeddings(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """A chunk-but-no-embedding document is fully healed in one pass."""
        doc = await _make_document(
            db_session, test_user, chunk_texts=["alpha", "beta"], with_embeddings=False
        )

        chunk_repo = DocumentChunkRepository(db_session)
        emb_repo = AIEmbeddingRepository(db_session)
        chunks = list(await chunk_repo.get_chunks_by_document(doc.id))
        assert len(chunks) == 2
        for chunk in chunks:  # precondition: no embeddings yet
            assert await emb_repo.get_by_chunk_id(chunk.id) is None

        svc = _make_svc(tmp_path)
        with (
            patch(
                "app.services.reindex_service.embedding_service.embed_batch",
                side_effect=lambda texts: [list(_FAKE_VECTOR) for _ in texts],
            ),
            patch("app.services.reindex_service.vector_store", svc),
        ):
            report = await reindex_all_embeddings(db_session)

        assert report["documents_processed"] == 1
        assert report["chunks_processed"] == 2
        assert report["embeddings_created"] == 2
        assert report["vectors_indexed"] == 2
        assert report["failures"] == 0

        # Every chunk now has exactly one embedding, and FAISS is populated + saved.
        for chunk in chunks:
            assert await emb_repo.get_by_chunk_id(chunk.id) is not None
        assert svc.vector_count == 2
        assert (tmp_path / "index.faiss").exists()

    async def test_is_idempotent(
        self, db_session: AsyncSession, test_user: User, tmp_path: Path
    ) -> None:
        """Running twice converges: same vector count, one embedding per chunk."""
        doc = await _make_document(
            db_session, test_user, chunk_texts=["alpha", "beta"], with_embeddings=False
        )
        svc = _make_svc(tmp_path)

        async def _run() -> dict:
            with (
                patch(
                    "app.services.reindex_service.embedding_service.embed_batch",
                    side_effect=lambda texts: [list(_FAKE_VECTOR) for _ in texts],
                ),
                patch("app.services.reindex_service.vector_store", svc),
            ):
                return await reindex_all_embeddings(db_session)

        first = await _run()
        second = await _run()

        assert first["vectors_indexed"] == 2
        assert second["vectors_indexed"] == 2  # build_index replaces — never 4
        assert svc.vector_count == 2

        # Exactly one embedding per chunk — the 2nd run replaced, not duplicated.
        emb_count = (
            await db_session.execute(
                select(func.count(AIEmbedding.id))
                .join(DocumentChunk, DocumentChunk.id == AIEmbedding.document_chunk_id)
                .where(DocumentChunk.document_id == doc.id)
            )
        ).scalar_one()
        assert emb_count == 2


# ===========================================================================
# 4. AI_MIN_RETRIEVAL_SCORE config default (Phase 7)
# ===========================================================================


@pytest.mark.asyncio
class TestMinScoreConfigDefault:
    """
    The configured default threshold filters weak matches when a request does
    not specify its own min_score, while an explicit request value always wins.

    FAISS distances are chosen so their similarities straddle the 0.5 threshold:
        distance 0.5 → similarity 1/(1+0.5) = 0.667  (kept at threshold 0.5)
        distance 3.0 → similarity 1/(1+3.0) = 0.25   (dropped at threshold 0.5)
    """

    async def _two_chunks(
        self, db: AsyncSession, user: User
    ) -> tuple[DocumentChunk, DocumentChunk]:
        doc = await _make_document(
            db, user, chunk_texts=["high relevance chunk", "low relevance chunk"]
        )
        chunk_repo = DocumentChunkRepository(db)
        chunks = list(await chunk_repo.get_chunks_by_document(doc.id))
        return chunks[0], chunks[1]

    def _mock_vector_store(self, chunk_high: DocumentChunk, chunk_low: DocumentChunk) -> MagicMock:
        mock_vs = MagicMock()
        mock_vs.search.return_value = [
            VSSearchResult(chunk_id=chunk_high.id, distance=0.5, rank=1),
            VSSearchResult(chunk_id=chunk_low.id, distance=3.0, rank=2),
        ]
        return mock_vs

    async def test_config_default_filters_low_similarity(
        self, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        high, low = await self._two_chunks(db_session, test_user)
        mock_vs = self._mock_vector_store(high, low)
        monkeypatch.setattr(settings, "AI_MIN_RETRIEVAL_SCORE", 0.5)

        with (
            patch("app.services.search_service.vector_store", mock_vs),
            patch(
                "app.services.search_service.embedding_service.embed_text",
                return_value=list(_FAKE_VECTOR),
            ),
        ):
            data = await SearchService(db_session).semantic_search(
                query="anything", actor=test_user, top_k=5, min_score=None
            )

        assert data.total_results == 1
        assert data.results[0].chunk_id == high.id

    async def test_request_min_score_overrides_config(
        self, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        high, low = await self._two_chunks(db_session, test_user)
        mock_vs = self._mock_vector_store(high, low)
        monkeypatch.setattr(settings, "AI_MIN_RETRIEVAL_SCORE", 0.5)

        with (
            patch("app.services.search_service.vector_store", mock_vs),
            patch(
                "app.services.search_service.embedding_service.embed_text",
                return_value=list(_FAKE_VECTOR),
            ),
        ):
            data = await SearchService(db_session).semantic_search(
                query="anything", actor=test_user, top_k=5, min_score=0.0
            )

        # Explicit min_score=0.0 wins over the 0.5 default → both chunks returned.
        assert data.total_results == 2

    async def test_config_none_disables_filtering(
        self, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        high, low = await self._two_chunks(db_session, test_user)
        mock_vs = self._mock_vector_store(high, low)
        monkeypatch.setattr(settings, "AI_MIN_RETRIEVAL_SCORE", None)

        with (
            patch("app.services.search_service.vector_store", mock_vs),
            patch(
                "app.services.search_service.embedding_service.embed_text",
                return_value=list(_FAKE_VECTOR),
            ),
        ):
            data = await SearchService(db_session).semantic_search(
                query="anything", actor=test_user, top_k=5, min_score=None
            )

        assert data.total_results == 2
