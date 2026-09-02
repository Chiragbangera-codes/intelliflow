"""
RefreshToken repository — database access layer for refresh tokens.

Manages server-side refresh token lifecycle:
  - Creation (storing hash, never raw token)
  - Lookup by hash (for validation on refresh)
  - Revocation (on logout or rotation)
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """Handles all database operations for the refresh_tokens table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        token_hash: str,
    ) -> RefreshToken:
        """
        Persist a new refresh token hash.

        The expiry is computed from settings.REFRESH_TOKEN_EXPIRE_DAYS.

        Args:
            user_id:    The user this token belongs to.
            token_hash: SHA-256 hex digest of the raw token sent to the client.

        Returns:
            The persisted RefreshToken instance.
        """
        expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """
        Look up a refresh token by its SHA-256 hash.

        Used during the /auth/refresh flow to validate the presented token.

        Args:
            token_hash: SHA-256 hex digest of the raw token from the client.

        Returns:
            The RefreshToken instance, or None if not found.
        """
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, token_id: uuid.UUID) -> None:
        """
        Revoke a specific refresh token by setting its revoked_at timestamp.

        Used on:
          - Explicit logout (client-initiated)
          - Token rotation (old token revoked after successful refresh)

        Args:
            token_id: The UUID of the RefreshToken to revoke.
        """
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """
        Revoke all active refresh tokens for a given user.

        Useful for:
          - Force-logout (admin action)
          - Password change
          - Account suspension

        Args:
            user_id: The UUID of the user whose tokens should be revoked.
        """
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def get_active_sessions_for_user(self, user_id: uuid.UUID) -> list[RefreshToken]:
        """Return all active, non-expired, unrevoked refresh tokens for a user."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list(result.scalars().all())
