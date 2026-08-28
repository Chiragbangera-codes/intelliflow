"""
Milestone 7 Phase 2 — Semantic Search Tests.

Coverage:
  Authentication
    1.  Unauthenticated search → 401

  Validation
    2.  Empty query → 422
    3.  Whitespace-only query → 422
    4.  Query > 1000 characters → 422
    5.  top_k = 0 → 422
    6.  top_k = 21 → 422
    7.  min_score = -0.1 → 422
    8.  min_score = 1.5 → 422

  Basic Retrieval
    9.  Valid query returns 200 with expected structure
    10. top_k limits number of returned results
    11. Empty FAISS index → 200 with empty results
    12. FAISS missing / stale chunk IDs are skipped gracefully
    13. Soft-deleted documents are excluded from results

  Ranking & Scoring
    14. Results are ordered by ascending L2 distance (most similar first)
    15. Distance values in response match FAISS distances exactly
    16. similarity = 1 / (1 + distance) — deterministic formula
    17. min_score filters results by similarity threshold

  Security / RBAC
    18. Employee receives only their own documents
    19. Employee cannot retrieve another user's document via search
    20. Manager ownership rules are enforced (same as employee)
    21. Admin receives global results (cross-user access)
    22. HR receives global results (cross-user access)
    23. FAISS layer-1 bypass: SQL owner filter blocks unauthorised chunks
    24. FAISS layer-2 bypass: in-process ownership check blocks anything
        that slips through the SQL filter (defence-in-depth)

  Batch / N+1 Prevention
    25. Multiple FAISS results resolved in a single PostgreSQL query
    26. DB query count == 2 for any number of FAISS results (one for chunks
        resolution, one for audit) — verifying no N+1 pattern

  Audit
    27. Successful search creates a search.semantic audit record
    28. Audit record contains query_length, top_k, result_count metadata

  FAISS Safety
    29. Empty FAISS index does not crash
    30. Stale chunk IDs (absent from DB) do not crash or appear in results
    31. Stale chunk IDs mixed with valid ones — only valid returned

  Service-level unit tests (mocked)
    32. SearchService.semantic_search — happy path returns SearchData
    33. SearchService — blank query raises 422
    34. SearchService — RBAC layer-2 violation drops chunk (defence-in-depth)
    35. SearchService — min_score correctly filters by similarity
    36. SearchRepository.get_chunks_with_documents — returns correct data
    37. SearchRepository.get_chunks_with_documents — owner filter applied
    38. SearchRepository.get_chunks_with_documents — empty list returns {}
    39. similarity computation formula is correct and deterministic
    40. similarity = 1.0 when distance = 0.0
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User, UserStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.search_repository import ChunkWithDocument, SearchRepository
from app.services.search_service import SearchService, _compute_similarity
from app.services.vector_store_service import SearchResult as FAISSSearchResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBED_DIM = 384
_FAKE_VECTOR: list[float] = [0.1] * EMBED_DIM

_EMPLOYEE_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_HR_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------


async def _create_user(
    db: AsyncSession,
    *,
    role_id: uuid.UUID = _EMPLOYEE_ROLE_ID,
    prefix: str = "user",
) -> User:
    u = User(
        email=f"{prefix}_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1!"),
        first_name=prefix.capitalize(),
        last_name="Test",
        role_id=role_id,
        status=UserStatus.ACTIVE,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _create_document(
    db: AsyncSession,
    *,
    owner: User,
    file_name: str = "test.txt",
    deleted: bool = False,
) -> Document:
    doc = Document(
        file_name=file_name,
        storage_path=f"uploads/{uuid.uuid4().hex}/{file_name}",
        owner_id=owner.id,
        file_type="text/plain",
        file_size=100,
        status=DocumentStatus.PROCESSED,
        ocr_status=OcrStatus.COMPLETED,
    )
    if deleted:
        doc.deleted_at = datetime.now(UTC)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def _create_chunk(
    db: AsyncSession,
    *,
    document: Document,
    content: str = "Test content",
    chunk_number: int = 1,
) -> DocumentChunk:
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_number=chunk_number,
        content=content,
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        role=user.role.name if user.role else "employee",
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# FAISS / embedding mock helpers
# ---------------------------------------------------------------------------


def _mock_embedding_service(vector: list[float] | None = None) -> MagicMock:
    """Return a mock EmbeddingService.embed_text."""
    mock = MagicMock()
    mock.embed_text.return_value = vector or _FAKE_VECTOR
    return mock


def _mock_vector_store(
    results: list[FAISSSearchResult] | None = None,
) -> MagicMock:
    """Return a mock VectorStoreService.search."""
    mock = MagicMock()
    mock.search.return_value = results or []
    return mock


# ===========================================================================
# 1. Authentication Tests
# ===========================================================================


class TestSearchAuthentication:
    """Tests for authentication enforcement on POST /api/v1/search."""

    @pytest.mark.asyncio
    async def test_unauthenticated_search_returns_401(self, async_client: AsyncClient) -> None:
        """Test 1: No token → 401."""
        resp = await async_client.post("/api/v1/search", json={"query": "hello world"})
        assert resp.status_code == 401


# ===========================================================================
# 2. Validation Tests
# ===========================================================================


class TestSearchValidation:
    """Tests for request payload validation."""

    @pytest.mark.asyncio
    async def test_empty_query_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 2: Empty string → 422."""
        user = await _create_user(db_session)
        resp = await async_client.post(
            "/api/v1/search", json={"query": ""}, headers=_auth_headers(user)
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_query_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 3: Whitespace-only → 422."""
        user = await _create_user(db_session)
        with (
            patch("app.api.v1.search.SearchService") as MockSvc,
        ):
            MockSvc.return_value.semantic_search = AsyncMock(
                side_effect=Exception("should not reach")
            )
            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "   "},
                headers=_auth_headers(user),
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_query_too_long_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 4: Query > 1000 characters → 422."""
        user = await _create_user(db_session)
        resp = await async_client.post(
            "/api/v1/search",
            json={"query": "x" * 1001},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_top_k_zero_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 5: top_k = 0 → 422."""
        user = await _create_user(db_session)
        resp = await async_client.post(
            "/api/v1/search",
            json={"query": "hello world", "top_k": 0},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_top_k_too_large_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 6: top_k = 21 → 422."""
        user = await _create_user(db_session)
        resp = await async_client.post(
            "/api/v1/search",
            json={"query": "hello world", "top_k": 21},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_min_score_negative_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 7: min_score < 0 → 422."""
        user = await _create_user(db_session)
        resp = await async_client.post(
            "/api/v1/search",
            json={"query": "hello world", "min_score": -0.1},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_min_score_above_one_422(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 8: min_score > 1 → 422 (similarity is bounded to (0,1])."""
        user = await _create_user(db_session)
        resp = await async_client.post(
            "/api/v1/search",
            json={"query": "hello world", "min_score": 1.5},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422


# ===========================================================================
# 3. Basic Retrieval Tests
# ===========================================================================


class TestSearchBasicRetrieval:
    """Tests for basic search functionality."""

    @pytest.mark.asyncio
    async def test_valid_query_returns_200(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 9: Valid query returns 200 with expected envelope structure."""
        user = await _create_user(db_session)

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = []

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "what is FAISS"},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body
        assert "query" in body["data"]
        assert "results" in body["data"]
        assert "total_results" in body["data"]

    @pytest.mark.asyncio
    async def test_top_k_limits_results(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 10: top_k=2 returns at most 2 results."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunks = []
        for i in range(5):
            c = await _create_chunk(
                db_session, document=doc, content=f"chunk {i}", chunk_number=i + 1
            )
            chunks.append(c)

        faiss_hits = [
            FAISSSearchResult(chunk_id=c.id, distance=float(i) * 0.1, rank=i + 1)
            for i, c in enumerate(chunks)
        ]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "chunk content", "top_k": 2},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["results"]) <= 2
        assert data["total_results"] <= 2

    @pytest.mark.asyncio
    async def test_empty_faiss_index_returns_empty_results(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 11: Empty FAISS index → 200 with empty results, no crash."""
        user = await _create_user(db_session)

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = []  # empty index

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "what is FAISS"},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["results"] == []
        assert data["total_results"] == 0

    @pytest.mark.asyncio
    async def test_stale_faiss_chunk_ids_skipped(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 12: FAISS returns chunk IDs that no longer exist in DB — skipped gracefully."""
        user = await _create_user(db_session)
        stale_id = uuid.uuid4()  # not in DB

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = [
                FAISSSearchResult(chunk_id=stale_id, distance=0.1, rank=1)
            ]

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "what is FAISS"},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["results"] == []
        assert data["total_results"] == 0

    @pytest.mark.asyncio
    async def test_soft_deleted_documents_excluded(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 13: Chunks belonging to soft-deleted documents are excluded."""
        user = await _create_user(db_session)
        deleted_doc = await _create_document(db_session, owner=user, deleted=True)
        chunk = await _create_chunk(db_session, document=deleted_doc, content="deleted content")

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = [
                FAISSSearchResult(chunk_id=chunk.id, distance=0.05, rank=1)
            ]

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "deleted content"},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["results"] == []
        assert data["total_results"] == 0


# ===========================================================================
# 4. Ranking & Scoring Tests
# ===========================================================================


class TestSearchRankingAndScoring:
    """Tests for result ordering and score computation."""

    @pytest.mark.asyncio
    async def test_results_ordered_by_ascending_distance(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 14: Results are ordered from smallest distance (most similar) first."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunk_a = await _create_chunk(db_session, document=doc, content="A", chunk_number=1)
        chunk_b = await _create_chunk(db_session, document=doc, content="B", chunk_number=2)

        # FAISS returns B (distance 0.3) then A (distance 0.8)
        # — already ordered by FAISS ascending distance
        faiss_hits = [
            FAISSSearchResult(chunk_id=chunk_b.id, distance=0.3, rank=1),
            FAISSSearchResult(chunk_id=chunk_a.id, distance=0.8, rank=2),
        ]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "content", "top_k": 5},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        assert len(results) == 2
        # First result should have the smaller distance
        assert results[0]["distance"] < results[1]["distance"]

    @pytest.mark.asyncio
    async def test_distance_matches_faiss_exactly(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 15: distance values in response match FAISS exactly."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunk = await _create_chunk(db_session, document=doc, content="test")

        exact_distance = 0.42
        faiss_hits = [FAISSSearchResult(chunk_id=chunk.id, distance=exact_distance, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "test"},
                headers=_auth_headers(user),
            )

        results = resp.json()["data"]["results"]
        assert len(results) == 1
        assert abs(results[0]["distance"] - exact_distance) < 1e-6

    @pytest.mark.asyncio
    async def test_similarity_formula_deterministic(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 16: similarity = 1/(1+distance), exactly and deterministically."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunk = await _create_chunk(db_session, document=doc, content="test")

        distance = 0.5
        expected_similarity = 1.0 / (1.0 + distance)  # 0.6666...

        faiss_hits = [FAISSSearchResult(chunk_id=chunk.id, distance=distance, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "test"},
                headers=_auth_headers(user),
            )

        results = resp.json()["data"]["results"]
        assert len(results) == 1
        assert abs(results[0]["similarity"] - expected_similarity) < 1e-6

    @pytest.mark.asyncio
    async def test_min_score_filters_results(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 17: min_score=0.9 keeps only high-similarity results."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        # chunk_a: distance=0.05 → similarity=1/(1+0.05)≈0.952 — PASSES 0.9
        # chunk_b: distance=1.5  → similarity=1/(1+1.5)=0.4   — FAILS 0.9
        chunk_a = await _create_chunk(db_session, document=doc, content="near", chunk_number=1)
        chunk_b = await _create_chunk(db_session, document=doc, content="far", chunk_number=2)

        faiss_hits = [
            FAISSSearchResult(chunk_id=chunk_a.id, distance=0.05, rank=1),
            FAISSSearchResult(chunk_id=chunk_b.id, distance=1.5, rank=2),
        ]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "near content", "min_score": 0.9},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        # Only chunk_a should pass the threshold
        assert len(results) == 1
        assert results[0]["similarity"] >= 0.9


# ===========================================================================
# 5. Security / RBAC Tests
# ===========================================================================


class TestSearchRBAC:
    """Tests for document ownership enforcement and cross-user isolation."""

    @pytest.mark.asyncio
    async def test_employee_sees_only_own_documents(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 18: Employee sees only chunks from their own documents."""
        user_a = await _create_user(db_session, prefix="usera")
        doc_a = await _create_document(db_session, owner=user_a, file_name="docA.txt")
        chunk_a = await _create_chunk(db_session, document=doc_a, content="user A content")

        faiss_hits = [FAISSSearchResult(chunk_id=chunk_a.id, distance=0.1, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "user A content"},
                headers=_auth_headers(user_a),
            )

        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        assert len(results) == 1
        assert results[0]["document_id"] == str(doc_a.id)

    @pytest.mark.asyncio
    async def test_employee_cannot_see_another_users_document(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """
        Test 19 — Critical security test.

        FAISS returns User B's chunk as the top match.
        User A should receive zero results.
        The existence of User B's document must NOT be revealed.
        """
        user_a = await _create_user(db_session, prefix="usera")
        user_b = await _create_user(db_session, prefix="userb")

        # User B uploads a payroll document
        doc_b = await _create_document(db_session, owner=user_b, file_name="payroll.txt")
        chunk_b = await _create_chunk(
            db_session,
            document=doc_b,
            content="salary compensation payroll data",
        )

        # FAISS ranks User B's payroll chunk as the #1 mathematical match
        faiss_hits = [FAISSSearchResult(chunk_id=chunk_b.id, distance=0.02, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            # User A searches for payroll-related content
            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "salary payroll compensation"},
                headers=_auth_headers(user_a),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        # User A must receive ZERO results — User B's document is invisible
        assert data["results"] == [], (
            "SECURITY VIOLATION: User A received User B's document chunk. "
            "FAISS must not bypass RBAC."
        )
        assert data["total_results"] == 0

    @pytest.mark.asyncio
    async def test_manager_ownership_enforced(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 20: Manager only sees their own documents (same as employee)."""
        manager = await _create_user(db_session, role_id=_MANAGER_ROLE_ID, prefix="mgr")
        other = await _create_user(db_session, prefix="other")

        doc_other = await _create_document(db_session, owner=other, file_name="other.txt")
        chunk_other = await _create_chunk(db_session, document=doc_other, content="other content")

        faiss_hits = [FAISSSearchResult(chunk_id=chunk_other.id, distance=0.1, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "other content"},
                headers=_auth_headers(manager),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_admin_sees_all_documents(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 21: Admin receives global results — cross-user access."""
        admin = await _create_user(db_session, role_id=_ADMIN_ROLE_ID, prefix="admin")
        user_b = await _create_user(db_session, prefix="userb")

        doc_b = await _create_document(db_session, owner=user_b, file_name="b.txt")
        chunk_b = await _create_chunk(db_session, document=doc_b, content="secret data")

        faiss_hits = [FAISSSearchResult(chunk_id=chunk_b.id, distance=0.1, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "secret data"},
                headers=_auth_headers(admin),
            )

        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        # Admin can see User B's document
        assert len(results) == 1
        assert results[0]["document_id"] == str(doc_b.id)

    @pytest.mark.asyncio
    async def test_hr_sees_all_documents(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 22: HR receives global results."""
        hr = await _create_user(db_session, role_id=_HR_ROLE_ID, prefix="hr")
        user_b = await _create_user(db_session, prefix="userb")

        doc_b = await _create_document(db_session, owner=user_b, file_name="payroll.txt")
        chunk_b = await _create_chunk(db_session, document=doc_b, content="payroll data")

        faiss_hits = [FAISSSearchResult(chunk_id=chunk_b.id, distance=0.1, rank=1)]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "payroll data"},
                headers=_auth_headers(hr),
            )

        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        assert len(results) == 1
        assert results[0]["document_id"] == str(doc_b.id)


# ===========================================================================
# 6. Batch / N+1 Prevention Tests
# ===========================================================================


class TestSearchBatchQuery:
    """Tests to verify that multiple FAISS results trigger only one DB query."""

    @pytest.mark.asyncio
    async def test_multiple_faiss_results_single_db_query(self, db_session: AsyncSession) -> None:
        """
        Test 25 & 26: Multiple FAISS chunk IDs resolved in ONE SQL query.

        We patch AsyncSession.execute to count round-trips.  For N FAISS
        results, the repository must issue exactly 1 execute call (the batched
        IN query), not N separate calls.  This proves no N+1 pattern.
        """
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunks = []
        for i in range(5):
            c = await _create_chunk(
                db_session, document=doc, content=f"chunk {i}", chunk_number=i + 1
            )
            chunks.append(c)

        # Wrap the session's execute to count round-trips
        execute_call_count = 0
        original_execute = db_session.execute

        async def counting_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal execute_call_count
            execute_call_count += 1
            return await original_execute(stmt, *args, **kwargs)

        db_session.execute = counting_execute  # type: ignore[method-assign]

        try:
            repo = SearchRepository(db_session)
            chunk_ids = [c.id for c in chunks]
            result = await repo.get_chunks_with_documents(chunk_ids, owner_id=user.id)
        finally:
            db_session.execute = original_execute  # type: ignore[method-assign]

        # All 5 chunk IDs resolved correctly
        assert len(result) == 5
        # The repository must have issued exactly ONE execute call for all 5 IDs
        assert execute_call_count == 1, (
            f"N+1 detected: expected 1 SQL execute call, got {execute_call_count}. "
            f"The repository must use a batched IN query, not one query per chunk."
        )

    @pytest.mark.asyncio
    async def test_missing_db_chunks_do_not_crash(self, db_session: AsyncSession) -> None:
        """Test 26b: Stale chunk IDs (not in DB) simply absent from result dict."""
        user = await _create_user(db_session)
        stale_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        repo = SearchRepository(db_session)
        result = await repo.get_chunks_with_documents(stale_ids, owner_id=user.id)

        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_chunk_list_returns_empty_dict(self, db_session: AsyncSession) -> None:
        """Test 38: Empty chunk ID list returns {} without hitting the database."""
        user = await _create_user(db_session)
        repo = SearchRepository(db_session)
        result = await repo.get_chunks_with_documents([], owner_id=user.id)
        assert result == {}


# ===========================================================================
# 7. Audit Trail Tests
# ===========================================================================


class TestSearchAudit:
    """Tests for audit log generation on semantic search."""

    @pytest.mark.asyncio
    async def test_successful_search_creates_audit_record(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 27: search.semantic audit record is created on successful search."""
        user = await _create_user(db_session)

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = []

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "what is FAISS", "top_k": 3},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200

        audit_repo = AuditLogRepository(db_session)
        logs = await audit_repo.get_by_user(user.id)
        search_logs = [log for log in logs if log.action == "search.semantic"]
        assert len(search_logs) >= 1

    @pytest.mark.asyncio
    async def test_audit_record_contains_safe_metadata(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 28: Audit metadata contains query_length, top_k, result_count — not query text."""
        user = await _create_user(db_session)
        query = "what vector database does IntelliFlow use"

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = []

            await async_client.post(
                "/api/v1/search",
                json={"query": query, "top_k": 5},
                headers=_auth_headers(user),
            )

        audit_repo = AuditLogRepository(db_session)
        logs = await audit_repo.get_by_user(user.id)
        search_log = next((log for log in logs if log.action == "search.semantic"), None)
        assert search_log is not None
        assert search_log.new_value is not None
        assert search_log.new_value.get("query_length") == len(query)
        assert search_log.new_value.get("top_k") == 5
        assert "result_count" in search_log.new_value
        # Full query text must NOT be stored (privacy)
        assert "query" not in search_log.new_value or search_log.new_value.get("query") is None


# ===========================================================================
# 8. Service-Level Unit Tests (mocked)
# ===========================================================================


class TestSearchServiceUnit:
    """Unit tests for SearchService with mocked dependencies."""

    def _make_service(self, db: AsyncSession) -> SearchService:
        return SearchService(db)

    @pytest.mark.asyncio
    async def test_semantic_search_happy_path(self, db_session: AsyncSession) -> None:
        """Test 32: SearchService returns SearchData on valid query."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunk = await _create_chunk(db_session, document=doc, content="FAISS content")

        svc = self._make_service(db_session)

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = [
                FAISSSearchResult(chunk_id=chunk.id, distance=0.2, rank=1)
            ]

            result = await svc.semantic_search(
                query="FAISS content",
                actor=user,
                top_k=5,
                min_score=None,
            )

        assert result.total_results == 1
        assert result.results[0].chunk_id == chunk.id
        assert result.results[0].document_id == doc.id

    @pytest.mark.asyncio
    async def test_blank_query_raises_422(self, db_session: AsyncSession) -> None:
        """Test 33: Blank query raises HTTP 422."""
        from fastapi import HTTPException

        user = await _create_user(db_session)
        svc = self._make_service(db_session)

        with pytest.raises(HTTPException) as exc_info:
            await svc.semantic_search(
                query="   ",
                actor=user,
                top_k=5,
                min_score=None,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_rbac_layer2_drops_unauthorised_chunk(self, db_session: AsyncSession) -> None:
        """
        Test 34: Defence-in-depth.

        Even if SearchRepository mistakenly returns a chunk from another user's
        document (e.g., if a future code change breaks the SQL filter), the
        in-process ownership check in the service must block it.
        """
        user_a = await _create_user(db_session, prefix="a")
        user_b = await _create_user(db_session, prefix="b")
        doc_b = await _create_document(db_session, owner=user_b)
        chunk_b = await _create_chunk(db_session, document=doc_b, content="secret")

        svc = self._make_service(db_session)

        # Bypass SQL filter by patching the repository to return user_b's chunk
        fake_resolved = {
            chunk_b.id: ChunkWithDocument(
                chunk_id=chunk_b.id,
                document_id=doc_b.id,
                document_owner_id=user_b.id,  # <-- different owner
                document_name="secret.txt",
                chunk_number=1,
                content="secret",
                file_type=None,
                created_at=datetime.now(UTC),
            )
        }

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
            patch.object(
                svc._search_repo,
                "get_chunks_with_documents",
                new_callable=AsyncMock,
                return_value=fake_resolved,
            ),
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = [
                FAISSSearchResult(chunk_id=chunk_b.id, distance=0.1, rank=1)
            ]

            result = await svc.semantic_search(
                query="secret",
                actor=user_a,
                top_k=5,
                min_score=None,
            )

        # Layer 2 must have dropped the chunk
        assert (
            result.total_results == 0
        ), "SECURITY: Layer-2 RBAC check failed to block unauthorised chunk."

    @pytest.mark.asyncio
    async def test_min_score_service_filter(self, db_session: AsyncSession) -> None:
        """Test 35: SearchService filters results by similarity >= min_score."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        chunk_near = await _create_chunk(db_session, document=doc, content="near", chunk_number=1)
        chunk_far = await _create_chunk(db_session, document=doc, content="far", chunk_number=2)

        svc = self._make_service(db_session)

        # near: distance=0.05 → similarity≈0.952; far: distance=2.0 → similarity≈0.333
        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = [
                FAISSSearchResult(chunk_id=chunk_near.id, distance=0.05, rank=1),
                FAISSSearchResult(chunk_id=chunk_far.id, distance=2.0, rank=2),
            ]

            result = await svc.semantic_search(
                query="near",
                actor=user,
                top_k=5,
                min_score=0.8,
            )

        assert result.total_results == 1
        assert result.results[0].chunk_id == chunk_near.id


# ===========================================================================
# 9. SearchRepository Unit Tests
# ===========================================================================


class TestSearchRepository:
    """Unit tests for SearchRepository."""

    @pytest.mark.asyncio
    async def test_get_chunks_with_documents_returns_correct_data(
        self, db_session: AsyncSession
    ) -> None:
        """Test 36: Repository returns correct chunk and document metadata."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user, file_name="arch.docx")
        chunk = await _create_chunk(db_session, document=doc, content="FAISS arch")

        repo = SearchRepository(db_session)
        result = await repo.get_chunks_with_documents([chunk.id], owner_id=user.id)

        assert chunk.id in result
        cwd = result[chunk.id]
        assert cwd.document_id == doc.id
        assert cwd.document_name == "arch.docx"
        assert cwd.chunk_number == 1
        assert cwd.content == "FAISS arch"
        assert cwd.document_owner_id == user.id

    @pytest.mark.asyncio
    async def test_owner_filter_excludes_other_users_chunks(self, db_session: AsyncSession) -> None:
        """Test 37: SQL owner filter excludes chunks from other users' documents."""
        user_a = await _create_user(db_session, prefix="a")
        user_b = await _create_user(db_session, prefix="b")
        doc_b = await _create_document(db_session, owner=user_b)
        chunk_b = await _create_chunk(db_session, document=doc_b, content="B secret")

        repo = SearchRepository(db_session)
        # Query with user_a's owner_id — should not return user_b's chunk
        result = await repo.get_chunks_with_documents([chunk_b.id], owner_id=user_a.id)

        assert chunk_b.id not in result

    @pytest.mark.asyncio
    async def test_no_owner_filter_returns_all_non_deleted(self, db_session: AsyncSession) -> None:
        """Test 37b: None owner_id (admin) returns chunks from all non-deleted docs."""
        user_a = await _create_user(db_session, prefix="a")
        user_b = await _create_user(db_session, prefix="b")
        doc_a = await _create_document(db_session, owner=user_a)
        doc_b = await _create_document(db_session, owner=user_b)
        chunk_a = await _create_chunk(db_session, document=doc_a, content="A content")
        chunk_b = await _create_chunk(db_session, document=doc_b, content="B content")

        repo = SearchRepository(db_session)
        result = await repo.get_chunks_with_documents([chunk_a.id, chunk_b.id], owner_id=None)

        assert chunk_a.id in result
        assert chunk_b.id in result

    @pytest.mark.asyncio
    async def test_soft_deleted_excluded_by_repo(self, db_session: AsyncSession) -> None:
        """Test: Repo excludes soft-deleted documents automatically."""
        user = await _create_user(db_session)
        deleted_doc = await _create_document(db_session, owner=user, deleted=True)
        chunk = await _create_chunk(db_session, document=deleted_doc, content="deleted")

        repo = SearchRepository(db_session)
        result = await repo.get_chunks_with_documents([chunk.id], owner_id=None)

        assert chunk.id not in result


# ===========================================================================
# 10. Similarity Formula Unit Tests
# ===========================================================================


class TestSimilarityFormula:
    """Pure unit tests for _compute_similarity."""

    def test_similarity_is_one_when_distance_is_zero(self) -> None:
        """Test 40: Perfect match (distance=0) → similarity=1.0."""
        assert _compute_similarity(0.0) == 1.0

    def test_similarity_formula_deterministic(self) -> None:
        """Test 39: 1/(1+d) is deterministic for same input."""
        d = 0.75
        assert _compute_similarity(d) == pytest.approx(1.0 / (1.0 + d))
        assert _compute_similarity(d) == _compute_similarity(d)

    def test_similarity_decreases_as_distance_increases(self) -> None:
        """Larger distance → smaller similarity (monotonic)."""
        assert _compute_similarity(0.1) > _compute_similarity(0.5)
        assert _compute_similarity(0.5) > _compute_similarity(2.0)

    def test_similarity_bounded_above_by_one(self) -> None:
        """similarity is always ≤ 1.0."""
        for d in [0.0, 0.001, 0.5, 1.0, 10.0, 100.0]:
            assert _compute_similarity(d) <= 1.0

    def test_similarity_always_positive(self) -> None:
        """similarity is always > 0."""
        for d in [0.0, 0.5, 1.0, 10.0, 100.0]:
            assert _compute_similarity(d) > 0.0


# ===========================================================================
# 11. FAISS Safety Integration Tests
# ===========================================================================


class TestFAISSSafety:
    """Tests for graceful handling of FAISS edge cases."""

    @pytest.mark.asyncio
    async def test_stale_mixed_with_valid_chunks(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test 31: Mix of stale and valid FAISS results — only valid returned."""
        user = await _create_user(db_session)
        doc = await _create_document(db_session, owner=user)
        valid_chunk = await _create_chunk(db_session, document=doc, content="valid content")
        stale_id = uuid.uuid4()

        faiss_hits = [
            FAISSSearchResult(chunk_id=valid_chunk.id, distance=0.1, rank=1),
            FAISSSearchResult(chunk_id=stale_id, distance=0.2, rank=2),
        ]

        with (
            patch("app.services.search_service.embedding_service") as mock_emb,
            patch("app.services.search_service.vector_store") as mock_vs,
        ):
            mock_emb.embed_text.return_value = _FAKE_VECTOR
            mock_vs.search.return_value = faiss_hits

            resp = await async_client.post(
                "/api/v1/search",
                json={"query": "valid"},
                headers=_auth_headers(user),
            )

        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        # Only the valid chunk should appear
        assert len(results) == 1
        assert results[0]["chunk_id"] == str(valid_chunk.id)
