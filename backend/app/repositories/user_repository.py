"""
User repository — database access layer for users.

All user-related database operations are centralised here.
Only this repository communicates with the users table.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserStatus


class UserRepository:
    """Handles all database operations for the users table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        """
        Return a non-deleted user by their normalised email address.

        Soft-deleted users (deleted_at IS NOT NULL) are excluded.
        The caller should normalise the email before calling this method.

        Args:
            email: Normalised (lowercase) email address.

        Returns:
            The User instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(User)
            .options(
                selectinload(User.role),
                selectinload(User.department),
                selectinload(User.employee_profile),
            )
            .where(
                User.email == email,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """
        Return a non-deleted user by their UUID.

        Args:
            user_id: The user's UUID primary key.

        Returns:
            The User instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(User)
            .options(
                selectinload(User.role),
                selectinload(User.department),
                selectinload(User.employee_profile),
            )
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        role_id: uuid.UUID,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        """
        Insert a new user record.

        Args:
            email:         Normalised email address.
            password_hash: Argon2id hash of the plaintext password.
            first_name:    User's given name.
            last_name:     User's family name.
            role_id:       UUID of the assigned role.
            status:        Account status (default: ACTIVE).

        Returns:
            The persisted User instance with id populated.
        """
        user = User(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            role_id=role_id,
            status=status,
        )
        self._session.add(user)
        await self._session.flush()  # Populate id without committing the transaction
        await self._session.refresh(user)
        return user

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """
        Stamp the last_login timestamp for the given user.

        Called on every successful authentication.

        Args:
            user_id: The user's UUID.
        """
        await self._session.execute(
            update(User).where(User.id == user_id).values(last_login=datetime.now(UTC))
        )

    async def soft_delete(self, user_id: uuid.UUID) -> None:
        """
        Soft-delete a user by setting deleted_at.

        Per DATABASE_SCHEMA.md §9, users are never physically deleted.

        Args:
            user_id: The user's UUID.
        """
        await self._session.execute(
            update(User).where(User.id == user_id).values(deleted_at=datetime.now(UTC))
        )
