"""
AIConversationService — conversation management for the AI chat endpoint.

Responsibilities:
  - Verify ownership of an existing conversation (cross-user access prevention).
  - Persist a completed Q&A exchange to the ai_conversations table.
  - Return the saved exchange's UUID as both conversation_id and message_id.

Conversation design (Phase 3):
  - AIConversation row = one Q&A exchange.
  - conversation_id in the API response = AIConversation.id of the new row.
  - If the request includes a previous conversation_id, this service verifies
    that it belongs to the authenticated user (HTTP 403 if not).
  - No multi-turn threading: each call creates exactly one new row.

Security:
  - A user can never access another user's conversation via conversation_id.
  - Ownership check: row.user_id == actor.id  (simple, reliable, no ambiguity).
  - 403 is returned — not 404 — to avoid leaking conversation existence.

Architecture:
  API → AIConversationService → AIConversationRepository → Database
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AIConversation
from app.models.user import User
from app.repositories.ai_conversation_repository import AIConversationRepository

logger = logging.getLogger(__name__)


class AIConversationService:
    """
    Manages conversation ownership verification and exchange persistence.

    This service contains no retrieval or generation logic. Its sole concern
    is the ai_conversations table and ownership rules.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._session = db
        self._repo = AIConversationRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify_conversation_ownership(
        self,
        *,
        conversation_id: uuid.UUID,
        actor: User,
    ) -> AIConversation:
        """
        Verify that the authenticated user owns the specified conversation.

        Args:
            conversation_id: UUID of the AIConversation row to check.
            actor:           The authenticated user performing the request.

        Returns:
            The AIConversation row (may be used by caller for context).

        Raises:
            HTTPException 403: If the conversation does not exist OR belongs
                               to a different user.
                               (403 rather than 404 to avoid leaking existence.)
        """
        exchange = await self._repo.get_by_id(conversation_id)

        if exchange is None or exchange.user_id != actor.id:
            logger.warning(
                "Conversation ownership check failed: "
                "conversation_id=%s actor=%s (not found or wrong owner).",
                conversation_id,
                actor.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this conversation.",
            )

        logger.debug(
            "Conversation ownership verified: conversation_id=%s actor=%s",
            conversation_id,
            actor.id,
        )
        return exchange

    async def save_exchange(
        self,
        *,
        actor: User,
        question: str,
        answer: str | None,
        started_at: float,
    ) -> AIConversation:
        """
        Persist a Q&A exchange to the database and commit.

        Args:
            actor:      The authenticated user who asked the question.
            question:   The user's original message.
            answer:     The AI-generated answer. None if generation failed.
            started_at: time.monotonic() timestamp from before RAG started,
                        used to compute response_time in seconds.

        Returns:
            The newly persisted AIConversation row with its generated UUID.
        """
        elapsed = time.monotonic() - started_at

        exchange = await self._repo.create(
            user_id=actor.id,
            question=question,
            answer=answer,
            response_time=round(elapsed, 3),
        )

        try:
            await self._session.commit()
            await self._session.refresh(exchange)
        except Exception:
            await self._session.rollback()
            raise

        logger.info(
            "AI exchange persisted: id=%s actor=%s response_time=%.3fs",
            exchange.id,
            actor.id,
            elapsed,
        )
        return exchange
