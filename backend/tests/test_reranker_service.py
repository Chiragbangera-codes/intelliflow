"""
Tests for RerankerService (Milestone 7 Phase 5 — optional cross-encoder rerank).

The CrossEncoder is always mocked — no model download, no Torch inference, no
network. We assert the *contract*:
  - disabled (default) → pure pass-through, model NEVER loaded
  - < 2 results        → pass-through, model NEVER loaded
  - enabled            → head re-scored + reordered by cross-encoder score
  - top_n              → only the head is scored; the tail is preserved after it
  - model loaded once  → lazy singleton
  - scoring error      → falls back to the original RRF order (never raises)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

import app.services.reranker_service as reranker_module
from app.core.config import settings
from app.schemas.search import SearchResult
from app.services.reranker_service import reranker_service


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """The reranker model is a module-level singleton — reset it around tests."""
    reranker_module._model_instance = None
    yield
    reranker_module._model_instance = None


@pytest.fixture
def mock_cross_encoder():
    """Patch CrossEncoder; yield (class_mock, instance_mock)."""
    with patch("app.services.reranker_service.CrossEncoder") as ce_cls:
        instance = MagicMock()
        ce_cls.return_value = instance
        yield ce_cls, instance


def _result(*, content: str, score: float, chunk_number: int = 0) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="doc.txt",
        chunk_number=chunk_number,
        content=content,
        score=score,
        match_type="hybrid",
    )


def test_disabled_is_passthrough_and_never_loads_model(mock_cross_encoder) -> None:
    ce_cls, _instance = mock_cross_encoder
    results = [_result(content="a", score=0.9), _result(content="b", score=0.5)]
    # AI_RERANK_ENABLED defaults to False.
    out = reranker_service.rerank(query="q", results=results, top_n=20)
    assert out is results  # identical object, untouched
    ce_cls.assert_not_called()  # model must NOT be constructed when disabled


def test_single_result_is_passthrough(mock_cross_encoder, monkeypatch: pytest.MonkeyPatch) -> None:
    ce_cls, _instance = mock_cross_encoder
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    results = [_result(content="only", score=0.9)]
    out = reranker_service.rerank(query="q", results=results, top_n=20)
    assert out is results
    ce_cls.assert_not_called()  # <2 results → nothing to rerank, no load


def test_reorders_by_cross_encoder_score(
    mock_cross_encoder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ce_cls, instance = mock_cross_encoder
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    # RRF order is a, b, c; the cross-encoder disagrees: b > c > a.
    results = [
        _result(content="a", score=0.9),
        _result(content="b", score=0.5),
        _result(content="c", score=0.1),
    ]
    instance.predict.return_value = [0.1, 0.9, 0.5]
    out = reranker_service.rerank(query="q", results=results, top_n=20)
    assert [r.content for r in out] == ["b", "c", "a"]
    # score is replaced with the cross-encoder relevance.
    assert [r.score for r in out] == [0.9, 0.5, 0.1]
    # The query/content pairs are exactly the head, in original order.
    (pairs_arg,), _kwargs = instance.predict.call_args
    assert pairs_arg == [("q", "a"), ("q", "b"), ("q", "c")]


def test_top_n_scores_only_head_and_preserves_tail(
    mock_cross_encoder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ce_cls, instance = mock_cross_encoder
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    results = [
        _result(content="a", score=0.90),
        _result(content="b", score=0.80),
        _result(content="c", score=0.70),
        _result(content="d", score=0.60),  # tail
        _result(content="e", score=0.50),  # tail
    ]
    # Only the first 3 are scored; reorder them to c, a, b.
    instance.predict.return_value = [0.2, 0.1, 0.3]
    out = reranker_service.rerank(query="q", results=results, top_n=3)

    # Head reordered by score desc (c=.3, a=.2, b=.1); tail kept in place after.
    assert [r.content for r in out] == ["c", "a", "b", "d", "e"]
    # predict saw only the 3 head pairs.
    (pairs_arg,), _kwargs = instance.predict.call_args
    assert len(pairs_arg) == 3
    # Tail scores are untouched (still their RRF values).
    assert out[3].score == 0.60
    assert out[4].score == 0.50


def test_model_loaded_once_as_singleton(
    mock_cross_encoder, monkeypatch: pytest.MonkeyPatch
) -> None:
    ce_cls, instance = mock_cross_encoder
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    instance.predict.return_value = [0.5, 0.4]
    results = [_result(content="a", score=0.9), _result(content="b", score=0.5)]
    reranker_service.rerank(query="q", results=results, top_n=20)
    reranker_service.rerank(query="q2", results=results, top_n=20)
    assert ce_cls.call_count == 1  # lazy singleton: constructed exactly once


def test_scoring_error_falls_back_to_rrf(
    mock_cross_encoder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ce_cls, instance = mock_cross_encoder
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    instance.predict.side_effect = RuntimeError("boom")
    results = [_result(content="a", score=0.9), _result(content="b", score=0.5)]
    out = reranker_service.rerank(query="q", results=results, top_n=20)
    assert out is results  # unchanged original order — retrieval never breaks


def test_empty_results_passthrough(mock_cross_encoder, monkeypatch: pytest.MonkeyPatch) -> None:
    ce_cls, _instance = mock_cross_encoder
    monkeypatch.setattr(settings, "AI_RERANK_ENABLED", True)
    out = reranker_service.rerank(query="q", results=[], top_n=20)
    assert out == []
    ce_cls.assert_not_called()
