"""
AI/RAG Pydantic schemas — Milestone 7 Phase 3.

Request and response models for the AI chat endpoint.

Conversation design:
  Each AIConversation row = one complete Q&A exchange.
  The returned conversation_id IS the AIConversation.id.
  Passing conversation_id back verifies ownership of that previous exchange.
  No multi-turn grouping is implied by the existing schema.

Validation rules:
  message:   2–4000 characters, non-blank/whitespace-only.
  top_k:     1–10 inclusive.
  min_score: 0–1 inclusive, or None (no filter).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Request
# =============================================================================


class AIChatRequest(BaseModel):
    """
    Payload for POST /api/v1/ai/chat.

    Validation:
      - message: 2–4000 characters, not blank or whitespace-only.
      - top_k:   1–10 (prevents unbounded FAISS scans).
      - min_score: 0–1 (similarity scale). None = no threshold.
      - conversation_id: if provided, ownership is verified server-side.
    """

    conversation_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "ID of a previous Q&A exchange. If supplied, ownership is verified. "
            "If None, a new exchange is created."
        ),
    )
    message: str = Field(
        ...,
        min_length=2,
        max_length=4000,
        description="Natural-language question (2–4000 characters, non-blank).",
        examples=["What is our employee leave policy?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of authorized document chunks to retrieve (1–10).",
        examples=[5],
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum similarity threshold (0–1, inclusive). "
            "Chunks with similarity < min_score are excluded. "
            "None = no threshold."
        ),
        examples=[None],
    )

    @field_validator("message")
    @classmethod
    def message_not_whitespace(cls, v: str) -> str:
        """Reject messages that are blank or consist solely of whitespace."""
        if not v.strip():
            raise ValueError("Message must not be blank or whitespace-only.")
        return v


# =============================================================================
# Response — individual source
# =============================================================================


class AISource(BaseModel):
    """
    A single document chunk that was used to construct the LLM context.

    Carries enough metadata for the UI to display a cited source. Score fields
    are optional because a cited chunk may originate from the semantic branch,
    the lexical branch, or both (hybrid retrieval).
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_number: int
    content: str
    similarity: float | None = Field(
        default=None,
        description="Bounded similarity score: 1 / (1 + L2_distance). None for lexical-only.",
    )
    distance: float | None = Field(
        default=None,
        description="Raw FAISS L2 distance. Lower = more similar. None for lexical-only.",
    )
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


class AIChatResponseData(BaseModel):
    """
    Data payload embedded in AIChatResponse.

    conversation_id = message_id = ID of the AIConversation row just created.
    sources = chunks that reached the LLM context (empty if no chunks found).
    retrieved_chunks = len(sources).
    """

    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    sources: list[AISource]
    retrieved_chunks: int


# =============================================================================
# Response — full API envelope
# =============================================================================


class AIChatResponse(BaseModel):
    """
    Envelope for POST /api/v1/ai/chat.

    Follows the project-wide response convention:
      { "success": true, "message": "...", "data": { ... } }
    """

    success: bool = True
    message: str = "Answer generated successfully."
    data: AIChatResponseData
