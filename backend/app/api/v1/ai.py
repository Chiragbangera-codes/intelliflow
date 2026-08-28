"""
AI Chat API — POST /api/v1/ai/chat.

Provides:
  POST /api/v1/ai/chat — authenticated RAG-based document QA

Pipeline (in order):
  1. JWT authentication — get_current_user
  2. Validate request (Pydantic AIChatRequest)
  3. If conversation_id provided — verify ownership (403 if wrong user)
  4. Run RAG pipeline — SearchService → ContextBuilder → LLMService
  5. Persist exchange — AIConversationService
  6. Write audit log — AuditLogRepository (safe metadata only)
  7. Return AIChatResponse

Security contract:
  - Authorization happens in SearchService BEFORE any chunk reaches the LLM.
  - The LLM never performs authorization.
  - Cross-user conversation access returns 403 (not 404).
  - LLM unavailability returns 503 with a safe message.
  - Internal errors return 500 with no stack trace exposed.
  - Audit log stores metadata only — no question text, no answer text.

Response codes:
  200 — answer generated (including the no-context fallback case)
  401 — unauthenticated
  403 — conversation belongs to another user
  422 — request validation failure
  503 — LLM provider unavailable
  500 — unexpected internal error (global handler in main.py)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.ai import AIChatRequest, AIChatResponse, AIChatResponseData
from app.services.ai_conversation_service import AIConversationService
from app.services.llm_service import LLMUnavailableError
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI"],
)


# =============================================================================
# Helpers
# =============================================================================


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP address for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _get_rag_service(db: AsyncSession = Depends(get_db)) -> RAGService:
    """Provide a RAGService instance with the injected DB session."""
    return RAGService(db)


def _get_conversation_service(
    db: AsyncSession = Depends(get_db),
) -> AIConversationService:
    """Provide an AIConversationService instance with the injected DB session."""
    return AIConversationService(db)


def _get_audit_repo(db: AsyncSession = Depends(get_db)) -> AuditLogRepository:
    """Provide an AuditLogRepository instance with the injected DB session."""
    return AuditLogRepository(db)


# =============================================================================
# POST /ai/chat
# =============================================================================


@router.post(
    "/chat",
    status_code=status.HTTP_200_OK,
    response_model=AIChatResponse,
    summary="AI document question answering",
    description=(
        "Ask a natural-language question about your authorized documents. "
        "The backend embeds the question using the existing EmbeddingService, "
        "retrieves authorized chunks via FAISS + PostgreSQL RBAC, assembles a "
        "grounded context, and generates an answer via Ollama. "
        "The LLM never performs authorization — RBAC is enforced before the "
        "context is built. If no authorized chunks are found, a deterministic "
        "fallback is returned without calling the LLM."
    ),
    responses={
        200: {"description": "Answer generated (may be the no-context fallback)."},
        401: {"description": "Not authenticated."},
        403: {"description": "Conversation belongs to another user."},
        422: {"description": "Invalid request (blank message, top_k out of range, etc.)."},
        503: {"description": "AI service temporarily unavailable."},
        500: {"description": "Unexpected internal error."},
    },
)
async def ai_chat(
    payload: AIChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    rag_svc: RAGService = Depends(_get_rag_service),
    conv_svc: AIConversationService = Depends(_get_conversation_service),
    audit_repo: AuditLogRepository = Depends(_get_audit_repo),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    RAG-powered document question answering endpoint.

    The authenticated user's JWT determines which documents are accessible.
    The caller must NOT supply owner_id or chunk IDs — authorization is
    derived exclusively from the authenticated token and enforced by
    SearchService before any content reaches the LLM.
    """
    ip_address = _get_client_ip(request)
    started_at = time.monotonic()

    # ------------------------------------------------------------------
    # Step 1 — Verify conversation ownership if conversation_id supplied
    # ------------------------------------------------------------------
    if payload.conversation_id is not None:
        # Raises HTTP 403 if the conversation doesn't exist or belongs to
        # a different user. We verify but don't use the returned exchange
        # for anything in Phase 3's single-exchange design.
        await conv_svc.verify_conversation_ownership(
            conversation_id=payload.conversation_id,
            actor=current_user,
        )

    # ------------------------------------------------------------------
    # Step 2 — Run RAG pipeline
    # ------------------------------------------------------------------
    try:
        rag_result: AIChatResponseData = await rag_svc.answer_question(
            query=payload.message,
            actor=current_user,
            conversation_id=payload.conversation_id,
            top_k=payload.top_k,
            min_score=payload.min_score,
            ip_address=ip_address,
        )
    except LLMUnavailableError:
        logger.warning(
            "LLM unavailable for actor=%s — returning 503.",
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is temporarily unavailable.",
        ) from None

    # ------------------------------------------------------------------
    # Step 3 — Persist the Q&A exchange
    # ------------------------------------------------------------------
    exchange = await conv_svc.save_exchange(
        actor=current_user,
        question=payload.message,
        answer=rag_result.answer,
        started_at=started_at,
    )

    # ------------------------------------------------------------------
    # Step 4 — Write audit log (safe metadata only)
    # ------------------------------------------------------------------
    response_generated = rag_result.retrieved_chunks > 0 or bool(rag_result.answer)
    try:
        await audit_repo.create(
            action="ai.chat",
            user_id=current_user.id,
            table_name="ai_conversations",
            record_id=exchange.id,
            new_value={
                "query_length": len(payload.message),
                "retrieved_chunks": rag_result.retrieved_chunks,
                "source_count": len(rag_result.sources),
                "conversation_id": str(payload.conversation_id)
                if payload.conversation_id
                else None,
                "response_generated": response_generated,
            },
            ip_address=ip_address,
        )
        await db.commit()
    except Exception:
        # Audit failures must never break the chat response
        logger.exception(
            "Failed to write ai.chat audit record for actor=%s",
            current_user.id,
        )
        try:
            await db.rollback()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Step 5 — Assemble final response with real IDs from persisted exchange
    # ------------------------------------------------------------------
    response_data = AIChatResponseData(
        conversation_id=exchange.id,
        message_id=exchange.id,
        answer=rag_result.answer,
        sources=rag_result.sources,
        retrieved_chunks=rag_result.retrieved_chunks,
    )

    return {
        "success": True,
        "message": "Answer generated successfully.",
        "data": response_data.model_dump(mode="json"),
    }
