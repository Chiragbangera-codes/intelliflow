"""
Prediction ORM model.

Stores ML prediction history.
Does not implement any prediction algorithms.

Fields per DATABASE_SCHEMA.md §5 (predictions):
  model, input, prediction, confidence, execution_time

JSONB is used for input and prediction to store structured data.
The JSON type is used in the model (works with both SQLite in tests
and PostgreSQL in production); the migration creates JSONB columns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Prediction(Base):
    """Historical record of a single ML model prediction."""

    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Name/version of the ML model (e.g. 'revenue_forecast_v2').",
    )
    input: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Input features as structured JSON (JSONB in PostgreSQL).",
    )
    prediction: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Prediction output as structured JSON (JSONB in PostgreSQL).",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Confidence score (0.0–1.0). NULL when not applicable.",
    )
    execution_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Time taken to compute the prediction, in seconds.",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Prediction id={self.id} model={self.model!r}>"
