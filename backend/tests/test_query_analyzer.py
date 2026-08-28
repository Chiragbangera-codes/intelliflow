"""
Unit tests for query_analyzer.extract_filename_terms (Milestone 7 Phase 4).

Pure function — no DB, no mocks. Verifies the term extraction is generic
(hardcodes no dataset value), drops noise/short tokens, dedupes, and bounds.
"""

from __future__ import annotations

from app.services.query_analyzer import extract_filename_terms


def test_extracts_distinctive_terms() -> None:
    assert extract_filename_terms("onboarding roadmap") == ["onboarding", "roadmap"]


def test_drops_noise_words() -> None:
    # Articles, pronouns, question words, and document-reference words go away.
    assert extract_filename_terms("what is in the roadmap document") == ["roadmap"]


def test_drops_short_tokens() -> None:
    # Tokens under 3 characters carry no filename signal.
    assert extract_filename_terms("id of q4 plan") == ["plan"]


def test_dedupes_preserving_order() -> None:
    assert extract_filename_terms("budget budget forecast budget") == ["budget", "forecast"]


def test_filename_token_yields_stem() -> None:
    # A filename-like token splits on the dot; the stem is a strong signal.
    terms = extract_filename_terms("summarize placement_roadmap.docx please")
    assert "placement" in terms
    assert "roadmap" in terms


def test_noise_only_query_returns_empty() -> None:
    assert extract_filename_terms("what is in the document") == []


def test_empty_and_whitespace_return_empty() -> None:
    assert extract_filename_terms("") == []
    assert extract_filename_terms("    ") == []


def test_respects_max_terms() -> None:
    query = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
    terms = extract_filename_terms(query, max_terms=3)
    assert terms == ["alpha", "bravo", "charlie"]


def test_case_insensitive() -> None:
    assert extract_filename_terms("ROADMAP Onboarding") == ["roadmap", "onboarding"]


def test_strips_punctuation_and_underscores() -> None:
    # Underscore is a token separator (matches the lexical tokeniser), and
    # punctuation never survives — so LIKE metacharacters can't leak.
    assert extract_filename_terms("q3-report_final!!!") == ["report", "final"]
