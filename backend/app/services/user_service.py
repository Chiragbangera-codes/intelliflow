"""
User service — thin facade over UserRepository.

Provides user-related business operations that don't belong to auth.
Expanded in future milestones (user management, profile updates, etc.).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    """Handles user-related business operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the database session."""
        self._session = session
        self._users = UserRepository(session)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Return a user by UUID, or None if not found.

        Args:
            user_id: The user's UUID.

        Returns:
            User instance or None.
        """
        return await self._users.get_by_id(user_id)

    async def get_by_email(self, email: str) -> User | None:
        """
        Return a user by normalised email, or None if not found.

        Args:
            email: Normalised (lowercase) email address.

        Returns:
            User instance or None.
        """
        return await self._users.get_by_email(email)
