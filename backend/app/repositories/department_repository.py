"""
Department repository — database access layer for departments.

Provides typed async methods for querying the departments table.
All database access goes through this layer — never from services directly.

Milestone 4 additions:
  - update()       — partial field update for PATCH endpoint
  - count_active() — aggregate COUNT for dashboard stats
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department


class DepartmentRepository:
    """Handles all database operations for the departments table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def get_by_id(self, department_id: uuid.UUID) -> Department | None:
        """
        Return an active (non-deleted) department by its UUID.

        Args:
            department_id: The department's UUID primary key.

        Returns:
            The Department instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(Department).where(
                Department.id == department_id,
                Department.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Department | None:
        """
        Return an active department by its exact name.

        Args:
            name: Department name (case-sensitive).

        Returns:
            The Department instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(Department).where(
                Department.name == name,
                Department.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Department]:
        """
        Return all active (non-deleted) departments ordered by name.

        Returns:
            List of active Department instances.
        """
        result = await self._session.execute(
            select(Department).where(Department.deleted_at.is_(None)).order_by(Department.name)
        )
        return list(result.scalars().all())

    async def create(self, *, name: str, description: str | None = None) -> Department:
        """
        Insert a new department record.

        Args:
            name:        Unique department name.
            description: Optional human-readable description.

        Returns:
            The persisted Department instance with id populated.
        """
        department = Department(name=name, description=description)
        self._session.add(department)
        await self._session.flush()
        await self._session.refresh(department)
        return department

    async def soft_delete(self, department_id: uuid.UUID) -> None:
        """
        Soft-delete a department by setting deleted_at.

        Note: If any active users have department_id pointing to this
        department, the FK RESTRICT on users.department_id will prevent
        physical deletion. This method only sets the soft-delete flag.

        Args:
            department_id: The department's UUID.
        """
        await self._session.execute(
            update(Department)
            .where(Department.id == department_id)
            .values(deleted_at=datetime.now(UTC))
        )

    async def update(
        self,
        department_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Department | None:
        """
        Partially update a department's fields.

        Only provided (non-None) keyword arguments are applied.
        Returns the refreshed Department, or None if not found.

        Args:
            department_id: UUID of the department to update.
            name:          New department name (optional).
            description:   New description (optional).

        Returns:
            Refreshed Department instance, or None if not found.
        """
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description

        await self._session.execute(
            update(Department)
            .where(Department.id == department_id, Department.deleted_at.is_(None))
            .values(**values)
        )
        return await self.get_by_id(department_id)

    async def count_active(self) -> int:
        """
        Return the count of active (non-deleted) departments.

        Used by the dashboard stats endpoint.

        Returns:
            Integer count.
        """
        result = await self._session.execute(
            select(func.count()).select_from(Department).where(Department.deleted_at.is_(None))
        )
        return result.scalar_one()
