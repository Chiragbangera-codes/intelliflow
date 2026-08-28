"""
AIConversation ORM model.

Stores AI chat interaction history.
Does not implement AI functionality — this is the data foundation only.

Fields per DATABASE_SCHEMA.md §5 (ai_conversations):
  user_id, question, answer, prompt_tokens,
  completion_tokens, response_time, created_at
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AIConversation(Base):
    """Record of a single AI question/answer exchange."""

    __tablename__ = "ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="User who initiated the conversation.",
    )
    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="The user's question sent to the AI.",
    )
    answer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="The AI's generated answer. NULL if generation failed.",
    )
    prompt_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Number of tokens in the prompt (input).",
    )
    completion_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Number of tokens in the completion (output).",
    )
    response_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Time taken for the AI to generate the response, in seconds.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
        doc="UTC timestamp of the conversation.",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped[User] = relationship(
        "User",
        back_populates="ai_conversations",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AIConversation id={self.id} user_id={self.user_id}>"
