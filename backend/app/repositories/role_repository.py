"""
Role repository — database access layer for roles.

Provides typed methods for querying the roles table.
All database access goes through this layer — never directly from services.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role


class RoleRepository:
    """Handles all database operations for the roles table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def get_by_name(self, name: str) -> Role | None:
        """
        Return a role by its unique name.

        Args:
            name: The role name (e.g. 'admin', 'employee').

        Returns:
            The Role instance, or None if not found.
        """
        result = await self._session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def get_default_role(self) -> Role:
        """
        Return the default role assigned to newly registered users.

        The 'employee' role is the default for self-registration.

        Raises:
            RuntimeError: If the default role is missing (migration not applied).
        """
        role = await self.get_by_name("employee")
        if role is None:
            raise RuntimeError(
                "Default role 'employee' not found. "
                "Ensure the 001_auth migration has been applied."
            )
        return role
