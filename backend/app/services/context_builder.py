"""
ContextBuilder — deterministic, secure context string assembly for RAG prompts.

Responsibilities:
  - Accept a list of authorized SearchResult objects.
  - Apply AI_MAX_CONTEXT_CHUNKS and AI_MAX_CONTEXT_CHARACTERS limits.
  - Group chunks from the same document (Phase 7: multi-chunk document reasoning).
  - Format each chunk as a structured XML-delimited SOURCE block (Phase 8).
  - Return the assembled context string and the list of chunks actually used.

Security contract (Phase 8/23):
  - This module NEVER fetches data from the database.
  - It receives ONLY authorized chunks (RBAC is applied upstream).
  - It is purely deterministic: same inputs → same output.
  - XML delimiters (<DOCUMENT_CONTEXT>, <SOURCE>) clearly separate untrusted
    document content from model instructions, making prompt injection harder.
  - Document content is placed inside delimited blocks with explicit labels so
    the system prompt can instruct the model to treat all enclosed content as
    untrusted data, never as instructions.
  - Content is never truncated mid-sentence in the delimiter block — the whole
    chunk is either included or excluded (fits-or-skip semantics).
  - Independently unit-testable — no mocking required.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from app.schemas.search import SearchResult


def build_context(
    results: list[SearchResult],
    *,
    max_chunks: int,
    max_chars: int,
) -> tuple[str, list[SearchResult]]:
    """
    Assemble an LLM context string from a list of authorized search results.

    Applies two independent limits:
      max_chunks — maximum number of SOURCE blocks to include.
      max_chars  — maximum total character count of the assembled string.
                   Chunks are added in order until this budget is exhausted.
                   A chunk is included only if it fits entirely within the budget
                   (fits-or-skip semantics — no mid-chunk truncation).

    Multi-chunk document grouping (Phase 7):
      Chunks from the same document are clustered together, ordered by
      chunk_number ascending. The cluster order is determined by the highest
      RRF/similarity score among the document's chunks (best document first).

    Prompt injection resistance (Phase 8):
      All chunk content lives inside <SOURCE>...</SOURCE> XML blocks inside
      <DOCUMENT_CONTEXT>.
    """
    if not results:
        return "", []

    # Phase 7: Document grouping
    doc_chunks: dict[uuid.UUID, list[SearchResult]] = defaultdict(list)
    doc_first_rank: dict[uuid.UUID, int] = {}

    for rank, result in enumerate(results):
        doc_id = result.document_id
        doc_chunks[doc_id].append(result)
        if doc_id not in doc_first_rank:
            doc_first_rank[doc_id] = rank

    # Order documents by best-ranked chunk
    ordered_docs = sorted(doc_chunks.keys(), key=lambda d: doc_first_rank[d])

    # Within each document, order chunks by chunk_number ascending
    for doc_id in ordered_docs:
        doc_chunks[doc_id].sort(key=lambda r: r.chunk_number)

    grouped_candidates: list[SearchResult] = []
    for doc_id in ordered_docs:
        grouped_candidates.extend(doc_chunks[doc_id])

    # Fit chunks into the budget
    used_chunks: list[SearchResult] = []
    blocks: list[str] = []
    total_chars = 0

    for i, result in enumerate(grouped_candidates):
        if len(used_chunks) >= max_chunks:
            break

        block = _format_source_block(source_number=i + 1, result=result)

        if total_chars + len(block) > max_chars:
            break

        blocks.append(block)
        used_chunks.append(result)
        total_chars += len(block)

    if not blocks:
        return "", []

    inner = "\n".join(blocks)
    context_text = f"<DOCUMENT_CONTEXT>\n{inner}\n</DOCUMENT_CONTEXT>"
    return context_text, used_chunks


def _format_source_block(*, source_number: int, result: SearchResult) -> str:
    """Format one search result as a labelled, XML-delimited SOURCE block."""
    if result.similarity is not None:
        relevance_str = f"{result.similarity:.4f}"
    elif result.score is not None:
        relevance_str = f"{result.score:.6f} (RRF)"
    else:
        relevance_str = "n/a"

    match_str = result.match_type or "semantic"
    content = (result.content or "").strip()

    return (
        f'<SOURCE id="{source_number}">\n'
        f"SOURCE {source_number}:\n"
        f"Document: {result.document_name}\n"
        f"Chunk: {result.chunk_number}\n"
        f"Similarity: {relevance_str}\n"
        f"Match: {match_str}\n"
        f"Content:\n"
        f"{content}\n"
        f"</SOURCE>"
    )
