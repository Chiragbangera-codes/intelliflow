"""
Tests for LexicalSearchRepository (Milestone 7 Phase 3 — lexical retrieval).

These run against the SQLite fallback engine (the LIKE branch). They verify:
  - content and filename matching
  - Layer-1 owner filtering enforced in SQL (RBAC)
  - soft-deleted documents excluded
  - empty/no-match queries return []
  - result bounding and 1-based ranking

No Ollama, no embedding model, no network. Pure DB.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User, UserStatus
from app.repositories.lexical_search_repository import LexicalSearchRepository

pytestmark = pytest.mark.asyncio


async def _make_user(db: AsyncSession, *, role_id: uuid.UUID) -> User:
    user = User(
        email=f"lex_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x" * 60,
        first_name="Lex",
        last_name="User",
        role_id=role_id,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_document(
    db: AsyncSession,
    *,
    owner: User,
    file_name: str,
    chunk_texts: list[str],
    deleted: bool = False,
) -> Document:
    from datetime import UTC, datetime

    doc = Document(
        file_name=file_name,
        storage_path=f"/store/{uuid.uuid4().hex}",
        file_type="text/plain",
        owner_id=owner.id,
        status=DocumentStatus.PROCESSED,
        ocr_status=OcrStatus.COMPLETED,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(doc)
    await db.flush()
    for i, text in enumerate(chunk_texts):
        db.add(DocumentChunk(document_id=doc.id, chunk_number=i, content=text))
    await db.commit()
    await db.refresh(doc)
    return doc


_EMPLOYEE = uuid.UUID("00000000-0000-4000-8000-000000000003")


@pytest_asyncio.fixture
async def owner_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, role_id=_EMPLOYEE)


@pytest_asyncio.fixture
async def owner_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, role_id=_EMPLOYEE)


async def test_matches_content(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(
        db_session,
        owner=owner_a,
        file_name="notes.txt",
        chunk_texts=["The quarterly revenue projection exceeded expectations."],
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search(query="revenue projection", owner_id=owner_a.id, limit=10)
    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].score >= 1


async def test_matches_filename(db_session: AsyncSession, owner_a: User) -> None:
    doc = await _make_document(
        db_session,
        owner=owner_a,
        file_name="onboarding_roadmap.docx",
        chunk_texts=["Week one covers environment setup and introductions."],
    )
    repo = LexicalSearchRepository(db_session)
    # The term "roadmap" appears only in the filename, not the chunk content.
    results = await repo.search(query="roadmap", owner_id=owner_a.id, limit=10)
    assert len(results) == 1
    assert results[0].chunk_id is not None
    # Confirm it belongs to the expected document.
    chunk = await db_session.get(DocumentChunk, results[0].chunk_id)
    assert chunk is not None and chunk.document_id == doc.id


async def test_owner_filter_excludes_other_users(
    db_session: AsyncSession, owner_a: User, owner_b: User
) -> None:
    await _make_document(
        db_session,
        owner=owner_a,
        file_name="a.txt",
        chunk_texts=["confidential merger strategy document"],
    )
    await _make_document(
        db_session,
        owner=owner_b,
        file_name="b.txt",
        chunk_texts=["confidential merger strategy document"],
    )
    repo = LexicalSearchRepository(db_session)
    # owner_a must only see their own chunk even though both match identically.
    results = await repo.search(query="merger strategy", owner_id=owner_a.id, limit=10)
    assert len(results) == 1
    chunk = await db_session.get(DocumentChunk, results[0].chunk_id)
    assert chunk is not None
    doc = await db_session.get(Document, chunk.document_id)
    assert doc is not None and doc.owner_id == owner_a.id


async def test_owner_none_returns_all(
    db_session: AsyncSession, owner_a: User, owner_b: User
) -> None:
    await _make_document(
        db_session, owner=owner_a, file_name="a.txt", chunk_texts=["synergy alpha"]
    )
    await _make_document(db_session, owner=owner_b, file_name="b.txt", chunk_texts=["synergy beta"])
    repo = LexicalSearchRepository(db_session)
    # owner_id=None models admin/HR global access.
    results = await repo.search(query="synergy", owner_id=None, limit=10)
    assert len(results) == 2


async def test_excludes_soft_deleted(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(
        db_session,
        owner=owner_a,
        file_name="deleted.txt",
        chunk_texts=["uniquetoken alpha"],
        deleted=True,
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search(query="uniquetoken", owner_id=owner_a.id, limit=10)
    assert results == []


async def test_empty_query_returns_empty(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(db_session, owner=owner_a, file_name="a.txt", chunk_texts=["content here"])
    repo = LexicalSearchRepository(db_session)
    assert await repo.search(query="   ", owner_id=owner_a.id, limit=10) == []
    assert await repo.search(query="!!! ___ %%%", owner_id=owner_a.id, limit=10) == []


async def test_no_match_returns_empty(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(
        db_session, owner=owner_a, file_name="a.txt", chunk_texts=["alpha beta gamma"]
    )
    repo = LexicalSearchRepository(db_session)
    assert await repo.search(query="zzzznonexistent", owner_id=owner_a.id, limit=10) == []


async def test_limit_bounds_results(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(
        db_session,
        owner=owner_a,
        file_name="a.txt",
        chunk_texts=[f"repeated keyword chunk {i}" for i in range(6)],
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search(query="keyword", owner_id=owner_a.id, limit=3)
    assert len(results) == 3
    # Ranks are 1-based and sequential.
    assert [r.rank for r in results] == [1, 2, 3]


async def test_more_matched_terms_ranks_higher(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(
        db_session,
        owner=owner_a,
        file_name="doc.txt",
        chunk_texts=[
            "apple banana cherry",  # matches all three terms
            "apple only",  # matches one term
        ],
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search(query="apple banana cherry", owner_id=owner_a.id, limit=10)
    assert len(results) == 2
    assert results[0].rank == 1
    # The chunk matching more terms must score at least as high and come first.
    assert results[0].score >= results[1].score


# ---------------------------------------------------------------------------
# search_by_filename — document-aware branch (Phase 4)
# ---------------------------------------------------------------------------
async def _doc_of(db: AsyncSession, chunk_id: uuid.UUID) -> uuid.UUID:
    chunk = await db.get(DocumentChunk, chunk_id)
    assert chunk is not None
    return chunk.document_id


async def test_by_filename_returns_leading_chunks(db_session: AsyncSession, owner_a: User) -> None:
    doc = await _make_document(
        db_session,
        owner=owner_a,
        file_name="onboarding_roadmap.docx",
        chunk_texts=["intro", "week one", "week two", "week three"],
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search_by_filename(
        terms=["roadmap"], owner_id=owner_a.id, chunks_per_doc=2, max_docs=5
    )
    assert len(results) == 2  # only the first 2 chunks of the matched document
    for r in results:
        assert await _doc_of(db_session, r.chunk_id) == doc.id
    # Leading chunks means the lowest chunk_numbers (0 and 1).
    numbers = []
    for r in results:
        chunk = await db_session.get(DocumentChunk, r.chunk_id)
        assert chunk is not None
        numbers.append(chunk.chunk_number)
    assert sorted(numbers) == [0, 1]


async def test_by_filename_matches_filename_not_content(
    db_session: AsyncSession, owner_a: User
) -> None:
    doc = await _make_document(
        db_session,
        owner=owner_a,
        file_name="placement_strategy.pdf",
        chunk_texts=["this text never mentions the magic word"],
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search_by_filename(
        terms=["placement"], owner_id=owner_a.id, chunks_per_doc=3, max_docs=5
    )
    assert len(results) == 1
    assert await _doc_of(db_session, results[0].chunk_id) == doc.id


async def test_by_filename_owner_filter(
    db_session: AsyncSession, owner_a: User, owner_b: User
) -> None:
    await _make_document(db_session, owner=owner_a, file_name="report.txt", chunk_texts=["a"])
    await _make_document(db_session, owner=owner_b, file_name="report.txt", chunk_texts=["b"])
    repo = LexicalSearchRepository(db_session)
    results = await repo.search_by_filename(
        terms=["report"], owner_id=owner_a.id, chunks_per_doc=3, max_docs=5
    )
    assert len(results) == 1
    doc_id = await _doc_of(db_session, results[0].chunk_id)
    doc = await db_session.get(Document, doc_id)
    assert doc is not None and doc.owner_id == owner_a.id


async def test_by_filename_excludes_soft_deleted(db_session: AsyncSession, owner_a: User) -> None:
    await _make_document(
        db_session,
        owner=owner_a,
        file_name="secret_report.txt",
        chunk_texts=["x"],
        deleted=True,
    )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search_by_filename(
        terms=["report"], owner_id=owner_a.id, chunks_per_doc=3, max_docs=5
    )
    assert results == []


async def test_by_filename_max_docs_bounds(db_session: AsyncSession, owner_a: User) -> None:
    for i in range(3):
        await _make_document(
            db_session, owner=owner_a, file_name=f"report_{i}.txt", chunk_texts=["c"]
        )
    repo = LexicalSearchRepository(db_session)
    results = await repo.search_by_filename(
        terms=["report"], owner_id=owner_a.id, chunks_per_doc=5, max_docs=2
    )
    distinct_docs = {await _doc_of(db_session, r.chunk_id) for r in results}
    assert len(distinct_docs) == 2  # capped at max_docs even though 3 match


async def test_by_filename_more_terms_ranks_first(db_session: AsyncSession, owner_a: User) -> None:
    strong = await _make_document(
        db_session, owner=owner_a, file_name="annual_budget_report.pdf", chunk_texts=["s"]
    )
    await _make_document(db_session, owner=owner_a, file_name="budget.txt", chunk_texts=["w"])
    repo = LexicalSearchRepository(db_session)
    results = await repo.search_by_filename(
        terms=["budget", "report"], owner_id=owner_a.id, chunks_per_doc=3, max_docs=5
    )
    assert results[0].rank == 1
    # The filename matching BOTH terms ranks first.
    assert await _doc_of(db_session, results[0].chunk_id) == strong.id


async def test_by_filename_empty_or_invalid_returns_empty(
    db_session: AsyncSession, owner_a: User
) -> None:
    await _make_document(db_session, owner=owner_a, file_name="report.txt", chunk_texts=["c"])
    repo = LexicalSearchRepository(db_session)
    assert (
        await repo.search_by_filename(terms=[], owner_id=owner_a.id, chunks_per_doc=3, max_docs=5)
        == []
    )
    assert (
        await repo.search_by_filename(
            terms=["report"], owner_id=owner_a.id, chunks_per_doc=0, max_docs=5
        )
        == []
    )
    assert (
        await repo.search_by_filename(
            terms=["report"], owner_id=owner_a.id, chunks_per_doc=3, max_docs=0
        )
        == []
    )
