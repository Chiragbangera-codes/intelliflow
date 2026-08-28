"""
Search Pydantic schemas — Milestone 7 Phase 2.

Defines request and response models for the semantic search endpoint.

Score semantics (documented explicitly):
  distance   — Raw FAISS IndexFlatL2 distance.  Lower = more similar.
  similarity — Bounded monotonic transform: 1 / (1 + distance).
               Range: (0, 1].  Higher = more similar.
               This is NOT cosine similarity; it is a convenience
               human-readable score derived deterministically from distance.

min_score filtering operates on similarity (not distance), so values
outside [0, 1] are meaningless and are rejected by validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Request
# =============================================================================


class SearchRequest(BaseModel):
    """
    Payload for POST /api/v1/search.

    Validation rules:
      - query: 2–1000 characters, must not be blank/whitespace-only.
      - top_k: 1–20 inclusive.  Prevents unbounded index scans.
      - min_score: 0–1 inclusive (similarity scale).  None = no threshold.
    """

    query: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="Natural-language question to search for in document chunks.",
        examples=["What vector database does IntelliFlow use?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of ranked results to return (1–20).",
        examples=[5],
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum similarity threshold (0–1, inclusive). "
            "Results with similarity < min_score are excluded. "
            "Similarity = 1 / (1 + L2_distance).  None = no threshold."
        ),
        examples=[0.5],
    )

    @field_validator("query")
    @classmethod
    def query_not_whitespace(cls, v: str) -> str:
        """Reject queries that are blank or consist solely of whitespace."""
        if not v.strip():
            raise ValueError("Query must not be blank or whitespace-only.")
        return v


# =============================================================================
# Response — individual result
# =============================================================================


class SearchResult(BaseModel):
    """
    A single ranked search result.

    Scores (all optional — a result may come from the semantic branch, the
    lexical branch, or both):
      distance   — FAISS L2 distance (semantic branch). None for lexical-only.
      similarity — 1 / (1 + distance), range (0, 1]. None for lexical-only.
      score      — Fusion/rerank relevance score (RRF, or cross-encoder when
                   reranking is enabled). Higher = more relevant.
      match_type — How the chunk was retrieved: "semantic", "lexical", or
                   "hybrid" (surfaced in both branches).
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_number: int
    content: str
    distance: float | None = Field(
        default=None,
        description="Raw FAISS L2 distance (semantic branch). Lower = more similar. None for lexical-only.",
    )
    similarity: float | None = Field(
        default=None,
        description=(
            "Bounded similarity score: 1 / (1 + distance). "
            "Range (0, 1].  Higher = more similar.  Not cosine similarity.  "
            "None for lexical-only matches."
        ),
    )
    file_type: str | None = None
    created_at: datetime | None = None
    score: float | None = Field(
        default=None,
        description="Fusion/rerank relevance score (RRF or cross-encoder). Higher = more relevant.",
    )
    match_type: str | None = Field(
        default=None,
        description='Retrieval origin: "semantic", "lexical", or "hybrid".',
    )


# =============================================================================
# Response — data envelope payload
# =============================================================================


class SearchData(BaseModel):
    """Data payload embedded in SearchResponse."""

    query: str
    results: list[SearchResult]
    total_results: int


# =============================================================================
# Response — full API envelope
# =============================================================================


class SearchResponse(BaseModel):
    """
    Envelope for POST /api/v1/search.

    Follows the project-wide response convention:
      { "success": true, "message": "...", "data": { ... } }
    """

    success: bool = True
    message: str = "Search completed successfully."
    data: SearchData
