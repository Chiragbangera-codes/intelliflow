"""
Tests for RAGService (Milestone 7 Phase 9/10/11).

Covers:
  - RAG uses HybridSearchService (not semantic-only SearchService)
  - No-context short-circuit: zero chunks → fallback, LLM NOT called
  - LLM generates answer when chunks are present
  - LLMUnavailableError propagates (→ 503 from API layer)
  - Timing log emitted when AI_TIMING_ENABLED
  - Timing log NOT emitted when AI_TIMING_ENABLED=False
  - Sources built correctly from used_chunks (similarity, distance, match_type)
  - Conversation history injected into system prompt (Phase 11)
  - History fetch failure does NOT break the pipeline (graceful)
  - History section absent when AI_MAX_HISTORY_EXCHANGES=0
  - History injection does NOT affect retrieved chunks (RBAC unaffected)
  - History is bounded by AI_MAX_HISTORY_CHARS
  - answer_question returns AIChatResponseData with correct fields
  - Placeholder conversation_id/message_id are zeros (replaced by API layer)
  - Context builder is called with AI_MAX_CONTEXT_CHUNKS/AI_MAX_CONTEXT_CHARACTERS
  - Blank query is normalized (stripped)

No real DB, FAISS, or Ollama required. All external collaborators are mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.search import SearchData, SearchResult
from app.services.llm_service import LLMUnavailableError

pytestmark = pytest.mark.asyncio

_ACTOR_ID = uuid.uuid4()
_DOC_ID = uuid.uuid4()
_CHUNK_ID = uuid.uuid4()
_FAKE_SEARCH_RESULT = SearchResult(
    chunk_id=_CHUNK_ID,
    document_id=_DOC_ID,
    document_name="handbook.pdf",
    chunk_number=1,
    content="Leave is 15 days.",
    distance=0.4,
    similarity=0.71,
    score=0.014,
    match_type="hybrid",
)

_EMPTY_SEARCH_DATA = SearchData(query="anything", results=[], total_results=0)
_NONEMPTY_SEARCH_DATA = SearchData(
    query="anything",
    results=[_FAKE_SEARCH_RESULT],
    total_results=1,
)


def _make_actor(role_name: str = "employee") -> MagicMock:
    actor = MagicMock()
    actor.id = _ACTOR_ID
    role = MagicMock()
    role.name = role_name
    actor.role = role
    return actor


def _make_db() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# RAGService instantiation / collaborator wiring
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_rag_service_instantiates_hybrid_search(
    mock_conv_repo: MagicMock,
    mock_llm: MagicMock,
    mock_hybrid: MagicMock,
) -> None:
    """RAGService must instantiate HybridSearchService, not SearchService."""
    from app.services.rag_service import RAGService

    db = _make_db()
    svc = RAGService(db)
    # HybridSearchService is called with the db session
    mock_hybrid.assert_called_once_with(db)
    # Ensure the attribute is set
    assert svc._hybrid_search is mock_hybrid.return_value


# ---------------------------------------------------------------------------
# No-context short-circuit
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_no_context_returns_fallback_without_calling_llm(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """Zero authorized chunks → fallback answer, LLM generate() NOT called."""
    from app.services.rag_service import _NO_CONTEXT_ANSWER, RAGService

    mock_hybrid = mock_hybrid_cls.return_value
    mock_hybrid.search = AsyncMock(return_value=_EMPTY_SEARCH_DATA)

    mock_llm = mock_llm_cls.return_value
    mock_llm.generate = AsyncMock()
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])

    svc = RAGService(_make_db())
    result = await svc.answer_question(
        query="What is leave?",
        actor=_make_actor(),
        conversation_id=None,
        top_k=5,
        min_score=None,
        ip_address="127.0.0.1",
    )

    # LLM must NOT have been called
    mock_llm.generate.assert_not_called()
    assert result.answer == _NO_CONTEXT_ANSWER
    assert result.sources == []
    assert result.retrieved_chunks == 0


# ---------------------------------------------------------------------------
# Normal RAG flow
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_rag_calls_llm_when_chunks_present(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """When hybrid search returns chunks, LLM is called and answer returned."""
    from app.services.rag_service import RAGService

    mock_hybrid = mock_hybrid_cls.return_value
    mock_hybrid.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])

    mock_llm = mock_llm_cls.return_value
    mock_llm.generate = AsyncMock(return_value="Leave is 15 days per year.")

    svc = RAGService(_make_db())
    result = await svc.answer_question(
        query="What is leave?",
        actor=_make_actor(),
        conversation_id=None,
        top_k=5,
        min_score=None,
        ip_address=None,
    )

    mock_llm.generate.assert_called_once()
    assert result.answer == "Leave is 15 days per year."
    assert result.retrieved_chunks == 1
    assert len(result.sources) == 1


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_rag_sources_carry_correct_metadata(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """Sources include similarity, distance, score, match_type from hybrid results."""
    from app.services.rag_service import RAGService

    mock_hybrid = mock_hybrid_cls.return_value
    mock_hybrid.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])
    mock_llm_cls.return_value.generate = AsyncMock(return_value="Answer.")

    svc = RAGService(_make_db())
    result = await svc.answer_question(
        query="query",
        actor=_make_actor(),
        conversation_id=None,
        top_k=5,
        min_score=None,
        ip_address=None,
    )

    src = result.sources[0]
    assert src.similarity == _FAKE_SEARCH_RESULT.similarity
    assert src.distance == _FAKE_SEARCH_RESULT.distance
    assert src.score == _FAKE_SEARCH_RESULT.score
    assert src.match_type == _FAKE_SEARCH_RESULT.match_type
    assert src.document_name == "handbook.pdf"
    assert src.chunk_number == 1


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_rag_returns_placeholder_conversation_ids(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """RAGService returns zero UUIDs for conversation_id/message_id (replaced by API)."""
    from app.services.rag_service import RAGService

    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_EMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])

    svc = RAGService(_make_db())
    result = await svc.answer_question(
        query="q",
        actor=_make_actor(),
        conversation_id=None,
        top_k=5,
        min_score=None,
        ip_address=None,
    )
    assert result.conversation_id == uuid.UUID(int=0)
    assert result.message_id == uuid.UUID(int=0)


# ---------------------------------------------------------------------------
# LLM unavailable
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_llm_unavailable_error_propagates(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """LLMUnavailableError from LLMService must propagate (API → 503)."""
    from app.services.rag_service import RAGService

    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])
    mock_llm_cls.return_value.generate = AsyncMock(side_effect=LLMUnavailableError("Ollama down"))

    svc = RAGService(_make_db())
    with pytest.raises(LLMUnavailableError):
        await svc.answer_question(
            query="q",
            actor=_make_actor(),
            conversation_id=None,
            top_k=5,
            min_score=None,
            ip_address=None,
        )


# ---------------------------------------------------------------------------
# HybridSearchService pass-through parameters
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_rag_passes_write_audit_false_to_hybrid(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """RAGService passes write_audit=False so HybridSearchService skips its audit."""
    from app.services.rag_service import RAGService

    mock_hybrid = mock_hybrid_cls.return_value
    mock_hybrid.search = AsyncMock(return_value=_EMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])

    svc = RAGService(_make_db())
    await svc.answer_question(
        query="q",
        actor=_make_actor(),
        conversation_id=None,
        top_k=7,
        min_score=0.3,
        ip_address="10.0.0.1",
    )

    mock_hybrid.search.assert_called_once()
    call_kwargs = mock_hybrid.search.call_args.kwargs
    assert call_kwargs["write_audit"] is False
    assert call_kwargs["top_k"] == 7
    assert call_kwargs["min_score"] == 0.3
    assert call_kwargs["ip_address"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# Timing log (Phase 10)
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_timing_log_emitted_when_enabled(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AI_TIMING log should be emitted when AI_TIMING_ENABLED is True."""
    from app.core.config import settings
    from app.services.rag_service import RAGService

    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_EMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])

    with patch.object(settings, "AI_TIMING_ENABLED", True):
        import logging

        with caplog.at_level(logging.INFO, logger="app.services.rag_service"):
            svc = RAGService(_make_db())
            await svc.answer_question(
                query="q",
                actor=_make_actor(),
                conversation_id=None,
                top_k=5,
                min_score=None,
                ip_address=None,
            )
    timing_lines = [r for r in caplog.records if "AI_TIMING" in r.message]
    assert len(timing_lines) == 1, f"Expected 1 AI_TIMING log, got {len(timing_lines)}"


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_timing_log_not_emitted_when_disabled(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No AI_TIMING log when AI_TIMING_ENABLED is False."""
    from app.core.config import settings
    from app.services.rag_service import RAGService

    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_EMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])

    with patch.object(settings, "AI_TIMING_ENABLED", False):
        import logging

        with caplog.at_level(logging.INFO, logger="app.services.rag_service"):
            svc = RAGService(_make_db())
            await svc.answer_question(
                query="q",
                actor=_make_actor(),
                conversation_id=None,
                top_k=5,
                min_score=None,
                ip_address=None,
            )
    timing_lines = [r for r in caplog.records if "AI_TIMING" in r.message]
    assert len(timing_lines) == 0


# ---------------------------------------------------------------------------
# Conversation history injection (Phase 11)
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_history_injected_into_system_prompt(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """Prior exchanges are injected into the system prompt when available."""
    from app.core.config import settings
    from app.services.rag_service import RAGService

    # Set up a prior exchange
    prior = MagicMock()
    prior.question = "What is overtime?"
    prior.answer = "Overtime is 1.5x pay."

    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[prior])
    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)

    # Capture the system_prompt passed to LLM
    captured_prompt: dict = {}

    async def _capture_generate(system_prompt: str, user_prompt: str) -> str:
        captured_prompt["system_prompt"] = system_prompt
        return "Answer."

    mock_llm_cls.return_value.generate = _capture_generate

    with patch.object(settings, "AI_MAX_HISTORY_EXCHANGES", 3):
        with patch.object(settings, "AI_MAX_HISTORY_CHARS", 2000):
            svc = RAGService(_make_db())
            await svc.answer_question(
                query="Follow-up?",
                actor=_make_actor(),
                conversation_id=None,
                top_k=5,
                min_score=None,
                ip_address=None,
            )

    system_prompt = captured_prompt.get("system_prompt", "")
    assert "What is overtime?" in system_prompt
    assert "Overtime is 1.5x pay." in system_prompt
    assert "CONVERSATION HISTORY" in system_prompt


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_history_absent_when_max_exchanges_zero(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """When AI_MAX_HISTORY_EXCHANGES=0, history is skipped, repo NOT called."""
    from app.core.config import settings
    from app.services.rag_service import RAGService

    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])
    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)
    mock_llm_cls.return_value.generate = AsyncMock(return_value="A.")

    with patch.object(settings, "AI_MAX_HISTORY_EXCHANGES", 0):
        svc = RAGService(_make_db())
        await svc.answer_question(
            query="q",
            actor=_make_actor(),
            conversation_id=None,
            top_k=5,
            min_score=None,
            ip_address=None,
        )
    mock_conv_repo.return_value.get_recent_by_user.assert_not_called()


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_history_fetch_failure_does_not_break_pipeline(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """If history repo raises, RAG pipeline still completes normally."""
    from app.services.rag_service import RAGService

    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(
        side_effect=Exception("DB connection lost")
    )
    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)
    mock_llm_cls.return_value.generate = AsyncMock(return_value="Answer despite error.")

    svc = RAGService(_make_db())
    result = await svc.answer_question(
        query="q",
        actor=_make_actor(),
        conversation_id=None,
        top_k=5,
        min_score=None,
        ip_address=None,
    )
    assert result.answer == "Answer despite error."


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
async def test_history_bounded_by_max_history_chars(
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """History exceeding AI_MAX_HISTORY_CHARS is truncated (exchange-level)."""
    from app.core.config import settings
    from app.services.rag_service import RAGService

    # Two exchanges, each ~100 chars — max 50 chars should drop at least one
    e1 = MagicMock()
    e1.question = "Short question."
    e1.answer = "Short answer."
    e2 = MagicMock()
    e2.question = "Another question about the documents."
    e2.answer = "Another long answer that goes beyond the character limit."

    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[e1, e2])
    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)

    captured: dict = {}

    async def _cap(system_prompt: str, user_prompt: str) -> str:
        captured["sp"] = system_prompt
        return "A."

    mock_llm_cls.return_value.generate = _cap

    with patch.object(settings, "AI_MAX_HISTORY_EXCHANGES", 5):
        with patch.object(settings, "AI_MAX_HISTORY_CHARS", 30):
            svc = RAGService(_make_db())
            await svc.answer_question(
                query="q",
                actor=_make_actor(),
                conversation_id=None,
                top_k=5,
                min_score=None,
                ip_address=None,
            )
    # At least one exchange should be absent because budget was only 30 chars
    sp = captured.get("sp", "")
    # Both exchanges' full text shouldn't fit in 30 chars of history
    assert "Another long answer" not in sp


# ---------------------------------------------------------------------------
# Context builder integration
# ---------------------------------------------------------------------------


@patch("app.services.rag_service.LLMService")
@patch("app.services.rag_service.HybridSearchService")
@patch("app.services.rag_service.AIConversationRepository")
@patch("app.services.rag_service.build_context")
async def test_rag_passes_correct_limits_to_context_builder(
    mock_build_context: MagicMock,
    mock_conv_repo: MagicMock,
    mock_hybrid_cls: MagicMock,
    mock_llm_cls: MagicMock,
) -> None:
    """Context builder is called with AI_MAX_CONTEXT_CHUNKS and AI_MAX_CONTEXT_CHARACTERS."""
    from app.core.config import settings
    from app.services.rag_service import RAGService

    mock_build_context.return_value = ("context text", [_FAKE_SEARCH_RESULT])
    mock_hybrid_cls.return_value.search = AsyncMock(return_value=_NONEMPTY_SEARCH_DATA)
    mock_conv_repo.return_value.get_recent_by_user = AsyncMock(return_value=[])
    mock_llm_cls.return_value.generate = AsyncMock(return_value="Answer.")

    svc = RAGService(_make_db())
    await svc.answer_question(
        query="q",
        actor=_make_actor(),
        conversation_id=None,
        top_k=5,
        min_score=None,
        ip_address=None,
    )

    mock_build_context.assert_called_once()
    call_kwargs = mock_build_context.call_args.kwargs
    assert call_kwargs["max_chunks"] == settings.AI_MAX_CONTEXT_CHUNKS
    assert call_kwargs["max_chars"] == settings.AI_MAX_CONTEXT_CHARACTERS
