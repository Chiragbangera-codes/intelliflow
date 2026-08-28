"""
AIConversationRepository — database access layer for ai_conversations.

Each AIConversation row represents one complete Q&A exchange:
  - user_id:       who asked
  - question:      the user's message
  - answer:        the AI's generated response (None if generation failed)
  - response_time: wall-clock seconds for the full RAG pipeline

Conversation design (Phase 3):
  - AIConversation.id IS the conversation_id returned to the client.
  - Each new chat creates a new row.
  - Passing a previous conversation_id just verifies ownership of that exchange.
  - No multi-turn threading is stored in this schema.
  - A future migration will add a session_id for proper conversation history.

This repository is the only place that touches the ai_conversations table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AIConversation


class AIConversationRepository:
    """Handles all database operations for the ai_conversations table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        question: str,
        answer: str | None,
        response_time: float | None = None,
    ) -> AIConversation:
        """
        Insert a new Q&A exchange row.

        Args:
            user_id:       UUID of the authenticated user who asked.
            question:      The user's message (stored for conversation history).
            answer:        The AI-generated response. None if generation failed.
            response_time: Wall-clock seconds for the full RAG pipeline.

        Returns:
            The persisted AIConversation with its generated UUID id.
        """
        exchange = AIConversation(
            user_id=user_id,
            question=question,
            answer=answer,
            response_time=response_time,
        )
        self._session.add(exchange)
        await self._session.flush()
        await self._session.refresh(exchange)
        return exchange

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        conversation_id: uuid.UUID,
    ) -> AIConversation | None:
        """
        Fetch a single AIConversation by its primary key.

        The user relationship is NOT eagerly loaded here (it is lazy="raise"
        on the model) to avoid accidental bulk loads. Ownership check is done
        by comparing the returned row's user_id against the actor's id.

        Args:
            conversation_id: UUID primary key of the ai_conversations row.

        Returns:
            AIConversation instance, or None if not found.
        """
        result = await self._session.execute(
            select(AIConversation).where(AIConversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[AIConversation]:
        """
        Return Q&A exchange rows for a specific user, newest first.

        Args:
            user_id: The authenticated user's UUID.
            limit:   Maximum rows to return (capped at 100).
            offset:  Pagination offset.

        Returns:
            List of AIConversation instances ordered by created_at descending.
        """
        effective_limit = min(limit, 100)
        result = await self._session.execute(
            select(AIConversation)
            .where(AIConversation.user_id == user_id)
            .order_by(AIConversation.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_recent_by_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int,
    ) -> list[AIConversation]:
        """
        Return the most recent Q&A exchanges for a user, oldest-first.

        Used by RAGService to inject prior conversation context into the
        system prompt for follow-up question awareness. Returns exchanges in
        chronological order (oldest first) so the LLM sees the conversation
        flow naturally.

        Security: only exchanges owned by user_id are returned (SQL WHERE
        clause). This method cannot access another user's conversations.

        Args:
            user_id: The authenticated user's UUID.
            limit:   Maximum number of recent exchanges to return.
                     Bounded to settings.AI_MAX_HISTORY_EXCHANGES by the caller.

        Returns:
            List of AIConversation instances in ascending created_at order
            (oldest → newest, at most `limit` items). Empty list if none exist.
        """
        effective_limit = max(1, min(limit, 20))  # Safety cap at 20
        # Fetch newest-first, then reverse so oldest comes first in the output.
        result = await self._session.execute(
            select(AIConversation)
            .where(AIConversation.user_id == user_id)
            .order_by(AIConversation.created_at.desc())
            .limit(effective_limit)
        )
        rows = list(result.scalars().all())
        # Reverse so the list is oldest-first for the history prefix formatter.
        rows.reverse()
        return rows
