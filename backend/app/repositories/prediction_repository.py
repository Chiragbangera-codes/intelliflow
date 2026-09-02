"""
Prediction repository — database access layer for predictions table.

Architecture:
  PredictionService → PredictionRepository → PostgreSQL
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prediction import Prediction


class PredictionRepository:
    """Handles all database operations for the predictions table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def create(self, prediction: Prediction) -> Prediction:
        """
        Persist a new Prediction record.

        The caller must commit after calling this method.
        """
        self._session.add(prediction)
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction

    async def get_by_id(self, prediction_id: uuid.UUID) -> Prediction | None:
        """Return a Prediction by UUID, or None if not found."""
        result = await self._session.execute(
            select(Prediction).where(Prediction.id == prediction_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Prediction]:
        """
        Return a paginated list of predictions ordered by created_at desc.

        Args:
            limit:  Maximum records to return (capped at 100).
            offset: Pagination offset.
        """
        effective_limit = min(max(limit, 1), 100)
        result = await self._session.execute(
            select(Prediction)
            .order_by(Prediction.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        """Return total number of prediction records."""
        from sqlalchemy import func

        result = await self._session.execute(select(func.count()).select_from(Prediction))
        return result.scalar_one()
