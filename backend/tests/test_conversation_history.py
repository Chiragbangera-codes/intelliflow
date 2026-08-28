"""
Tests for AIConversationRepository.get_recent_by_user (Phase 11).

Covers:
  - Returns empty list when no exchanges exist
  - Returns exchanges in oldest-first order (for history injection)
  - Limit bounds the result count
  - Only returns exchanges owned by the requesting user (RBAC)
  - Safety cap: limit > 20 is clamped to 20
  - Exchanges with blank answers are still returned

No LLM, no FAISS, no Celery.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AIConversation
from app.models.user import User, UserStatus
from app.repositories.ai_conversation_repository import AIConversationRepository

pytestmark = pytest.mark.asyncio

_EMPLOYEE = uuid.UUID("00000000-0000-4000-8000-000000000003")


async def _make_user(db: AsyncSession) -> User:
    u = User(
        email=f"hist_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x" * 60,
        first_name="H",
        last_name="User",
        role_id=_EMPLOYEE,
        status=UserStatus.ACTIVE,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_exchange(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: str,
    answer: str | None = "A.",
) -> AIConversation:
    ex = AIConversation(
        user_id=user_id,
        question=question,
        answer=answer,
    )
    db.add(ex)
    await db.commit()
    await db.refresh(ex)
    return ex


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_get_recent_empty_when_no_exchanges(db_session: AsyncSession) -> None:
    """Returns empty list when user has no prior exchanges."""
    user = await _make_user(db_session)
    repo = AIConversationRepository(db_session)
    result = await repo.get_recent_by_user(user_id=user.id, limit=5)
    assert result == []


async def test_get_recent_returns_oldest_first(db_session: AsyncSession) -> None:
    """Recent exchanges are returned oldest-first for history injection."""
    user = await _make_user(db_session)
    repo = AIConversationRepository(db_session)

    await _make_exchange(db_session, user_id=user.id, question="Q1")
    await _make_exchange(db_session, user_id=user.id, question="Q2")
    await _make_exchange(db_session, user_id=user.id, question="Q3")

    result = await repo.get_recent_by_user(user_id=user.id, limit=10)
    # Oldest first
    questions = [r.question for r in result]
    assert questions == ["Q1", "Q2", "Q3"]


async def test_get_recent_limit_bounds_result(db_session: AsyncSession) -> None:
    """Limit is respected: only the N most recent exchanges are returned."""
    user = await _make_user(db_session)
    repo = AIConversationRepository(db_session)

    for i in range(5):
        await _make_exchange(db_session, user_id=user.id, question=f"Q{i}")

    result = await repo.get_recent_by_user(user_id=user.id, limit=3)
    assert len(result) == 3


async def test_get_recent_limit_returns_most_recent(db_session: AsyncSession) -> None:
    """When limit < total, returns the N most recent, oldest-first among them."""
    user = await _make_user(db_session)
    repo = AIConversationRepository(db_session)

    for i in range(5):
        await _make_exchange(db_session, user_id=user.id, question=f"Q{i}")

    result = await repo.get_recent_by_user(user_id=user.id, limit=2)
    # Should get the last 2 (Q3, Q4) in oldest-first order
    assert len(result) == 2
    questions = [r.question for r in result]
    assert questions == ["Q3", "Q4"]


async def test_get_recent_only_own_exchanges(db_session: AsyncSession) -> None:
    """get_recent_by_user only returns exchanges belonging to that user."""
    user1 = await _make_user(db_session)
    user2 = await _make_user(db_session)
    repo = AIConversationRepository(db_session)

    await _make_exchange(db_session, user_id=user1.id, question="User1 Q")
    await _make_exchange(db_session, user_id=user2.id, question="User2 Q")

    result_u1 = await repo.get_recent_by_user(user_id=user1.id, limit=10)
    result_u2 = await repo.get_recent_by_user(user_id=user2.id, limit=10)

    assert all(r.user_id == user1.id for r in result_u1)
    assert all(r.user_id == user2.id for r in result_u2)
    assert len(result_u1) == 1
    assert len(result_u2) == 1


async def test_get_recent_safety_cap_at_20(db_session: AsyncSession) -> None:
    """Limit > 20 is clamped to 20 internally (safety cap)."""
    user = await _make_user(db_session)
    repo = AIConversationRepository(db_session)

    for i in range(25):
        await _make_exchange(db_session, user_id=user.id, question=f"Q{i}")

    result = await repo.get_recent_by_user(user_id=user.id, limit=100)
    assert len(result) <= 20


async def test_get_recent_includes_exchanges_with_none_answer(
    db_session: AsyncSession,
) -> None:
    """Exchanges where answer is None (e.g. LLM failure) are still returned."""
    user = await _make_user(db_session)
    repo = AIConversationRepository(db_session)

    await _make_exchange(db_session, user_id=user.id, question="Q", answer=None)

    result = await repo.get_recent_by_user(user_id=user.id, limit=5)
    assert len(result) == 1
    assert result[0].answer is None
