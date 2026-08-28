"""
Query analysis for document-aware retrieval (Milestone 7 Phase 4).

Goal: detect when a query *refers to a document* — by filename, title, or a
distinctive term likely to appear in a filename — so the hybrid retriever can
surface that document's leading chunks even when neither the semantic nor the
lexical branch ranked them highly.

Design constraints (verbatim intent — Phase 4):
  - GENERIC and data-driven. This module hardcodes NO filename, user name,
    document, query, or test-data keyword. It only extracts candidate terms
    from the query; whether any real document matches is decided later, in SQL,
    against the *authorized* corpus (so RBAC is never bypassed here).
  - The only fixed list is a small set of English function words + generic
    document-reference words ("document", "file", ...). These are query-side
    noise words, not tied to any particular dataset; dropping them stops a
    query like "the report document" from matching every filename containing
    the literal word "document".

Nothing here touches the database, the vector store, or authorization.
"""

from __future__ import annotations

import re

# Runs of word characters excluding underscore — mirrors the lexical repo's
# tokeniser so filename-term extraction and lexical search agree on tokens and
# LIKE metacharacters (%, _) can never leak into a pattern downstream.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Minimum term length. Single/double-character tokens ("a", "of", "id") carry
# almost no filename signal and match far too broadly.
_MIN_TERM_LENGTH = 3

# Generic query-side noise words: English function words plus words people use
# to *refer to* a document ("document", "file", "summarize", ...). This is NOT
# a content stop-word list and is deliberately independent of any dataset — it
# only prevents document-reference phrasing from matching filenames literally.
_NOISE_WORDS = frozenset(
    {
        # articles / conjunctions / prepositions
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "from",
        "by",
        "as",
        "into",
        "about",
        "over",
        "than",
        # pronouns / determiners
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "my",
        "our",
        "your",
        "their",
        "his",
        "her",
        "me",
        "us",
        "you",
        "they",
        "them",
        "we",
        # question / auxiliary words
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "has",
        "have",
        "had",
        # generic document-reference words
        "document",
        "documents",
        "doc",
        "docs",
        "file",
        "files",
        "attachment",
        "summarize",
        "summary",
        "summarise",
        "tell",
        "show",
        "give",
        "list",
        "explain",
        "describe",
        "find",
        "get",
        "please",
        "content",
        "contents",
        "info",
        "information",
        "detail",
        "details",
    }
)

# Upper bound on filename terms extracted from one query. Keeps the downstream
# per-term SQL expansion bounded regardless of query length.
_MAX_FILENAME_TERMS = 8


def extract_filename_terms(query: str, *, max_terms: int = _MAX_FILENAME_TERMS) -> list[str]:
    """
    Extract lowercased, deduplicated candidate terms a document filename might
    contain, in first-seen order.

    A filename-bearing token like "roadmap.docx" naturally yields the stem
    "roadmap" (the extension "docx" is also emitted and simply won't match
    most filenames, which is harmless). Noise words and very short tokens are
    dropped. Returns an empty list when the query carries no distinctive term —
    the signal that this query does not name a document.

    This function makes NO claim that any such document exists; it only proposes
    terms to look up, later, against the authorized corpus.
    """
    seen: list[str] = []
    for token in _TOKEN_RE.findall(query.lower()):
        if len(token) < _MIN_TERM_LENGTH or token in _NOISE_WORDS:
            continue
        if token not in seen:
            seen.append(token)
        if len(seen) >= max_terms:
            break
    return seen
