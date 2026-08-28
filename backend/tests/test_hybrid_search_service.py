"""
Tests for HybridSearchService (Milestone 7 Phase 3 — hybrid retrieval + RRF).

Strategy:
  - The semantic branch (embedding + FAISS) is mocked — no model download, no
    real index — so FAISS becomes a controllable candidate generator.
  - The lexical branch runs for real against the SQLite fallback DB.
  - Authorization runs for real against the DB (the authoritative RBAC gate).

Coverage: semantic-only, lexical-only, hybrid fusion, RRF ranking, cross-user
RBAC isolation, admin global access, min_score semantics, top_k bounding,
soft-delete exclusion, the hybrid kill-switch, and audit-metadata safety.

No Ollama, no embedding download, no network.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.reranker_service as reranker_module
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User, UserStatus
from app.services.hybrid_search_service import HybridSearchService
from app.services.vector_store_service import SearchResult as FAISSHit

pytestmark = pytest.mark.asyncio

_EMPLOYEE = uuid.UUID("00000000-0000-4000-8000-000000000003")
_ADMIN = uuid.UUID("00000000-0000-4000-8000-000000000001")
_HR = uuid.UUID("00000000-0000-4000-8000-000000000004")
_FAKE_VECTOR = [0.1] * 384


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def _make_user(db: AsyncSession, *, role_id: uuid.UUID = _EMPLOYEE) -> User:
    u = User(
        email=f"h_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x" * 60,
        first_name="H",
        last_name="User",
        role_id=role_id,
        status=UserStatus.ACTIVE,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_chunk(
    db: AsyncSession,
    *,
    owner: User,
    content: str,
    file_name: str = "doc.txt",
    chunk_number: int = 1,
    deleted: bool = False,
) -> DocumentChunk:
    doc = Document(
        file_name=file_name,
        storage_path=f"/s/{uuid.uuid4().hex}",
        file_type="text/plain",
        owner_id=owner.id,
        status=DocumentStatus.PROCESSED,
        ocr_status=OcrStatus.COMPLETED,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(doc)
    await db.flush()
    chunk = DocumentChunk(document_id=doc.id, chunk_number=chunk_number, content=content)
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


@contextlib.contextmanager
def _mock_semantic(faiss_hits: list[FAISSHit]):
    """Patch the embedding model + FAISS so the semantic branch is deterministic."""
    with (
        patch("app.services.hybrid_search_service.embedding_service") as emb,
        patch("app.services.hybrid_search_service.vector_store") as vs,
    ):
        emb.embed_text.return_value = _FAKE_VECTOR
        vs.search.return_value = faiss_hits
        yield


@pytest_asyncio.fixture
async def owner_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session)


@pytest_asyncio.fixture
async def owner_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session)


# ---------------------------------------------------------------------------
# Match-type / fusion behaviour
# ---------------------------------------------------------------------------
async def test_semantic_only_match(db_session: AsyncSession, owner_a: User) -> None:
    # Content shares no term with the query → lexical misses; FAISS returns it.
    chunk = await _make_chunk(db_session, owner=owner_a, content="alpha bravo charlie")
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk.id, distance=0.1, rank=1)]):
        data = await svc.search(query="zulu", actor=owner_a, top_k=5)
    assert data.total_results == 1
    r = data.results[0]
    assert r.match_type == "semantic"
    assert r.similarity is not None and r.distance is not None
    assert r.score is not None and r.score > 0


async def test_lexical_only_match(db_session: AsyncSession, owner_a: User) -> None:
    chunk = await _make_chunk(db_session, owner=owner_a, content="quarterly revenue report")
    svc = HybridSearchService(db_session)
    with _mock_semantic([]):  # FAISS finds nothing
        data = await svc.search(query="revenue", actor=owner_a, top_k=5)
    assert data.total_results == 1
    r = data.results[0]
    assert r.chunk_id == chunk.id
    assert r.match_type == "lexical"
    assert r.similarity is None and r.distance is None
    assert r.score is not None and r.score > 0


async def test_hybrid_match_same_chunk(db_session: AsyncSession, owner_a: User) -> None:
    chunk = await _make_chunk(db_session, owner=owner_a, content="onboarding roadmap details")
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk.id, distance=0.2, rank=1)]):
        data = await svc.search(query="roadmap", actor=owner_a, top_k=5)
    assert data.total_results == 1
    r = data.results[0]
    assert r.match_type == "hybrid"
    # RRF from both branches at rank 1: 1/(k+1) + 1/(k+1)
    expected = 2.0 / (settings.AI_RRF_K + 1)
    assert abs(r.score - expected) < 1e-9


async def test_rrf_hybrid_outranks_better_single_branch(
    db_session: AsyncSession, owner_a: User
) -> None:
    # chunk_both: lexical hit (term 'synergy') + FAISS rank 2
    # chunk_sem : FAISS rank 1 (better semantic rank) but no lexical hit
    chunk_both = await _make_chunk(
        db_session, owner=owner_a, content="synergy initiatives", chunk_number=1
    )
    chunk_sem = await _make_chunk(
        db_session, owner=owner_a, content="unrelated material", chunk_number=1, file_name="b.txt"
    )
    svc = HybridSearchService(db_session)
    with _mock_semantic(
        [
            FAISSHit(chunk_id=chunk_sem.id, distance=0.05, rank=1),
            FAISSHit(chunk_id=chunk_both.id, distance=0.30, rank=2),
        ]
    ):
        data = await svc.search(query="synergy", actor=owner_a, top_k=5)
    assert data.total_results == 2
    # Fusion lifts the doc found by BOTH branches above the top semantic-only doc.
    assert data.results[0].chunk_id == chunk_both.id
    assert data.results[0].match_type == "hybrid"
    assert data.results[1].chunk_id == chunk_sem.id


# ---------------------------------------------------------------------------
# RBAC — the authoritative gate
# ---------------------------------------------------------------------------
async def test_cross_user_isolation(db_session: AsyncSession, owner_a: User, owner_b: User) -> None:
    """FAISS returning another user's chunk must NOT leak it. PG ownership wins."""
    chunk_a = await _make_chunk(db_session, owner=owner_a, content="confidential merger plan")
    chunk_b = await _make_chunk(db_session, owner=owner_b, content="confidential merger plan")
    svc = HybridSearchService(db_session)
    # FAISS ranks owner_b's chunk #1 (the adversarial case).
    with _mock_semantic(
        [
            FAISSHit(chunk_id=chunk_b.id, distance=0.01, rank=1),
            FAISSHit(chunk_id=chunk_a.id, distance=0.50, rank=2),
        ]
    ):
        data = await svc.search(query="merger", actor=owner_a, top_k=5)
    doc_ids = {r.document_id for r in data.results}
    assert chunk_b.id not in {r.chunk_id for r in data.results}
    for r in data.results:
        assert r.chunk_id == chunk_a.id
    # owner_b's document id must never appear.
    b_chunk = await db_session.get(DocumentChunk, chunk_b.id)
    assert b_chunk is not None
    assert b_chunk.document_id not in doc_ids


async def test_admin_global_access(db_session: AsyncSession, owner_b: User) -> None:
    admin = await _make_user(db_session, role_id=_ADMIN)
    chunk_b = await _make_chunk(db_session, owner=owner_b, content="payroll figures")
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk_b.id, distance=0.1, rank=1)]):
        data = await svc.search(query="payroll", actor=admin, top_k=5)
    assert data.total_results == 1
    assert data.results[0].chunk_id == chunk_b.id


async def test_hr_global_access(db_session: AsyncSession, owner_b: User) -> None:
    hr = await _make_user(db_session, role_id=_HR)
    chunk_b = await _make_chunk(db_session, owner=owner_b, content="benefits enrollment")
    svc = HybridSearchService(db_session)
    with _mock_semantic([]):
        data = await svc.search(query="benefits", actor=hr, top_k=5)
    assert data.total_results == 1
    assert data.results[0].chunk_id == chunk_b.id


async def test_soft_deleted_excluded(db_session: AsyncSession, owner_a: User) -> None:
    chunk = await _make_chunk(db_session, owner=owner_a, content="uniqueterm secret", deleted=True)
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk.id, distance=0.01, rank=1)]):
        data = await svc.search(query="uniqueterm", actor=owner_a, top_k=5)
    assert data.total_results == 0


# ---------------------------------------------------------------------------
# Thresholds / bounds / switches
# ---------------------------------------------------------------------------
async def test_min_score_filters_semantic_keeps_lexical(
    db_session: AsyncSession, owner_a: User
) -> None:
    # semantic-only, far away → low similarity; content has no query term.
    chunk_sem = await _make_chunk(
        db_session, owner=owner_a, content="totally different topic", file_name="s.txt"
    )
    # lexical-only, matches the query term; FAISS won't return it.
    chunk_lex = await _make_chunk(
        db_session, owner=owner_a, content="lexword appears here", file_name="l.txt"
    )
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk_sem.id, distance=2.0, rank=1)]):
        data = await svc.search(query="lexword", actor=owner_a, top_k=5, min_score=0.9)
    ids = {r.chunk_id for r in data.results}
    assert chunk_sem.id not in ids  # similarity 0.333 < 0.9 → filtered
    assert chunk_lex.id in ids  # lexical-only (similarity None) → kept


async def test_top_k_bounds_results(db_session: AsyncSession, owner_a: User) -> None:
    hits = []
    for i in range(5):
        c = await _make_chunk(
            db_session,
            owner=owner_a,
            content=f"keyword chunk {i}",
            chunk_number=i + 1,
            file_name=f"f{i}.txt",
        )
        hits.append(FAISSHit(chunk_id=c.id, distance=0.1 * (i + 1), rank=i + 1))
    svc = HybridSearchService(db_session)
    with _mock_semantic(hits):
        data = await svc.search(query="keyword", actor=owner_a, top_k=2)
    assert data.total_results == 2


async def test_hybrid_disabled_is_semantic_only(
    db_session: AsyncSession, owner_a: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A chunk that only a lexical search could find; FAISS returns nothing.
    await _make_chunk(db_session, owner=owner_a, content="lexicalonly token")
    monkeypatch.setattr(settings, "AI_HYBRID_ENABLED", False)
    svc = HybridSearchService(db_session)
    with _mock_semantic([]):
        data = await svc.search(query="lexicalonly", actor=owner_a, top_k=5)
    # Kill-switch on: lexical branch does not run, so nothing is found.
    assert data.total_results == 0


async def test_blank_query_raises_422(db_session: AsyncSession, owner_a: User) -> None:
    svc = HybridSearchService(db_session)
    with pytest.raises(HTTPException) as exc:
        await svc.search(query="   ", actor=owner_a, top_k=5)
    assert exc.value.status_code == 422


async def test_empty_everything_returns_empty(db_session: AsyncSession, owner_a: User) -> None:
    await _make_chunk(db_session, owner=owner_a, content="alpha beta")
    svc = HybridSearchService(db_session)
    with _mock_semantic([]):
        data = await svc.search(query="zzznomatch", actor=owner_a, top_k=5)
    assert data.total_results == 0
    assert data.results == []


# ---------------------------------------------------------------------------
# Audit safety
# ---------------------------------------------------------------------------
async def test_audit_written_without_query_text(db_session: AsyncSession, owner_a: User) -> None:
    chunk = await _make_chunk(db_session, owner=owner_a, content="auditable content")
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk.id, distance=0.1, rank=1)]):
        await svc.search(
            query="auditable secret phrase", actor=owner_a, top_k=5, ip_address="10.0.0.1"
        )
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "search.hybrid")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    payload = rows[0].new_value or {}
    assert "query_length" in payload
    # The raw query text must never be persisted.
    assert "auditable secret phrase" not in str(payload)


async def test_write_audit_false_skips_audit(db_session: AsyncSession, owner_a: User) -> None:
    chunk = await _make_chunk(db_session, owner=owner_a, content="no audit please")
    svc = HybridSearchService(db_session)
    with _mock_semantic([FAISSHit(chunk_id=chunk.id, distance=0.1, rank=1)]):
        await svc.search(query="audit", actor=owner_a, top_k=5, write_audit=False)
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "search.hybrid")))
        .scalars()
        .all()
    )
    assert rows == []


# ---------------------------------------------------------------------------
# Document-aware branch (Phase 4)
# ---------------------------------------------------------------------------
async def _make_multichunk_doc(
    db: AsyncSession,
    *,
    owner: User,
    file_name: str,
    contents: list[str],
    deleted: bool = False,
) -> list[DocumentChunk]:
    doc = Document(
        file_name=file_name,
        storage_path=f"/s/{uuid.uuid4().hex}",
        file_type="text/plain",
        owner_id=owner.id,
        status=DocumentStatus.PROCESSED,
        ocr_status=OcrStatus.COMPLETED,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(doc)
    await db.flush()
    chunks = [
        DocumentChunk(document_id=doc.id, chunk_number=i, content=text)
        for i, text in enumerate(contents)
    ]
    db.add_all(chunks)
    await db.commit()
    for c in chunks:
        await db.refresh(c)
    return chunks


async def test_doc_aware_boosts_leading_chunks_of_named_document(
    db_session: AsyncSession, owner_a: User
) -> None:
    """
    A query naming a document by filename must lift that document's LEADING
    chunks above its later chunks — doc-aware gives chunks 0/1/2 a third RRF
    vote on top of the lexical filename match every chunk shares.
    """
    await _make_multichunk_doc(
        db_session,
        owner=owner_a,
        file_name="q4_roadmap.pdf",
        contents=[f"body paragraph {i}" for i in range(5)],
    )
    svc = HybridSearchService(db_session)
    # FAISS finds nothing — the filename term "roadmap" is the only signal.
    with _mock_semantic([]):
        data = await svc.search(query="roadmap", actor=owner_a, top_k=5)

    assert data.total_results == 5
    leading = {r.chunk_number for r in data.results[:3]}
    assert leading == {0, 1, 2}  # the three leading chunks rank first
    assert all(r.match_type == "lexical" for r in data.results)
    assert all(r.similarity is None for r in data.results)


async def test_doc_aware_respects_rbac(
    db_session: AsyncSession, owner_a: User, owner_b: User
) -> None:
    """Doc-aware must never surface another user's filename-matching document."""
    await _make_multichunk_doc(
        db_session, owner=owner_b, file_name="salary_report.pdf", contents=["confidential"]
    )
    svc = HybridSearchService(db_session)
    with _mock_semantic([]):
        data = await svc.search(query="salary report", actor=owner_a, top_k=5)
    assert data.total_results == 0  # owner_a has no matching document


async def test_doc_aware_and_semantic_yield_hybrid(db_session: AsyncSession, owner_a: User) -> None:
    chunks = await _make_multichunk_doc(
        db_session, owner=owner_a, file_name="roadmap_plan.pdf", contents=["intro", "middle"]
    )
    svc = HybridSearchService(db_session)
    # Semantic also returns the leading chunk → semantic + keyword-family = hybrid.
    with _mock_semantic([FAISSHit(chunk_id=chunks[0].id, distance=0.1, rank=1)]):
        data = await svc.search(query="roadmap", actor=owner_a, top_k=5)
    top = next(r for r in data.results if r.chunk_id == chunks[0].id)
    assert top.match_type == "hybrid"
    assert top.similarity is not None


async def test_doc_aware_disabled_skips_filename_branch(
    db_session: AsyncSession, owner_a: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    With doc-aware off, a filename-only reference is served by the lexical
    branch alone: the leading-chunk boost disappears, so later chunks are no
    longer pushed below the leading ones by a second vote.
    """
    await _make_multichunk_doc(
        db_session,
        owner=owner_a,
        file_name="q4_roadmap.pdf",
        contents=[f"body paragraph {i}" for i in range(5)],
    )
    monkeypatch.setattr(settings, "AI_DOC_AWARE_ENABLED", False)
    svc = HybridSearchService(db_session)
    with _mock_semantic([]):
        data = await svc.search(query="roadmap", actor=owner_a, top_k=5)
    # Lexical alone still finds all five chunks (filename is part of its index),
    # but every chunk now has exactly one vote — no leading-chunk guarantee.
    assert data.total_results == 5
    assert all(r.match_type == "lexical" for r in data.results)


# ---------------------------------------------------------------------------
# Reranker integration (Phase 5) — reranking is wired but OFF by default
# ---------------------------------------------------------------------------
async def test_rerank_reorders_final_results_when_enabled(
    db_session: AsyncSession, owner_a: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    With reranking enabled, the cross-encoder score — not the RRF rank — decides
    the final order. Semantic ranks A>B>C; the (mocked) reranker flips it to
    C>B>A, proving the reranker is genuinely wired into the pipeline.
    """
    chunk_a = await _make_chunk(db_session, owner=owner_a, content="aaa", file_name="a.txt")
    chunk_b = await _make_chunk(db_session, owner=owner_a, content="bbb", file_name="b.txt")
    chunk_c = await _make_chunk(db_session, owner=owner_a, content="ccc", file_name="c.txt")

    reranker_module._model_instance = None
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    svc = HybridSearchService(db_session)

    faiss_hits = [
        FAISSHit(chunk_id=chunk_a.id, distance=0.10, rank=1),
        FAISSHit(chunk_id=chunk_b.id, distance=0.20, rank=2),
        FAISSHit(chunk_id=chunk_c.id, distance=0.30, rank=3),
    ]
    # Query term "zulu" matches neither content nor filename → semantic-only,
    # so the RRF order is exactly the FAISS rank order (A, B, C).
    with _mock_semantic(faiss_hits), patch("app.services.reranker_service.CrossEncoder") as ce_cls:
        instance = MagicMock()
        # head is [A, B, C]; give C the top score, A the lowest → C, B, A.
        instance.predict.return_value = [0.1, 0.5, 0.9]
        ce_cls.return_value = instance
        data = await svc.search(query="zulu", actor=owner_a, top_k=5)

    reranker_module._model_instance = None
    assert [r.chunk_id for r in data.results] == [chunk_c.id, chunk_b.id, chunk_a.id]
    # score now carries the cross-encoder relevance, descending.
    assert [r.score for r in data.results] == [0.9, 0.5, 0.1]
