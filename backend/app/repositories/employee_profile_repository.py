"""
EmployeeProfile repository — database access layer for employee profiles.

Provides typed async methods for the employee_profiles table.
The one-to-one relationship with users requires careful FK handling.

Milestone 4 additions:
  - list_active()  — paginated list of all active profiles
  - update()       — partial field update for PATCH endpoint
  - soft_delete()  — set deleted_at (admin/hr only)
  - count_active() — aggregate COUNT for dashboard stats
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile


class EmployeeProfileRepository:
    """Handles all database operations for the employee_profiles table."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> EmployeeProfile | None:
        """
        Return the active employee profile for a given user.

        Args:
            user_id: The user's UUID.

        Returns:
            The EmployeeProfile instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.user_id == user_id,
                EmployeeProfile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_employee_code(self, employee_code: str) -> EmployeeProfile | None:
        """
        Return an active employee profile by employee code.

        Args:
            employee_code: The unique employee identifier (e.g. 'EMP-0042').

        Returns:
            The EmployeeProfile instance, or None if not found or soft-deleted.
        """
        result = await self._session.execute(
            select(EmployeeProfile).where(
                EmployeeProfile.employee_code == employee_code,
                EmployeeProfile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        employee_code: str | None = None,
        date_of_joining: date | None = None,
        designation: str | None = None,
        salary: Decimal | None = None,
        manager_id: uuid.UUID | None = None,
        emergency_contact: str | None = None,
        address: str | None = None,
        profile_photo: str | None = None,
    ) -> EmployeeProfile:
        """
        Insert a new employee profile record.

        Args:
            user_id:           UUID of the associated user (one-to-one).
            employee_code:     Optional unique employee code.
            date_of_joining:   Optional employee start date.
            designation:       Optional job title.
            salary:            Optional gross salary.
            manager_id:        Optional UUID of the manager user.
            emergency_contact: Optional emergency contact details.
            address:           Optional residential address.
            profile_photo:     Optional profile photo path.

        Returns:
            The persisted EmployeeProfile instance with id populated.
        """
        profile = EmployeeProfile(
            user_id=user_id,
            employee_code=employee_code,
            date_of_joining=date_of_joining,
            designation=designation,
            salary=salary,
            manager_id=manager_id,
            emergency_contact=emergency_contact,
            address=address,
            profile_photo=profile_photo,
        )
        self._session.add(profile)
        await self._session.flush()
        await self._session.refresh(profile)
        return profile

    async def list_active(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[EmployeeProfile]:
        """
        Return all active (non-deleted) employee profiles ordered by created_at.

        Args:
            limit:  Maximum records to return (default 20, max 100).
            offset: Pagination offset.

        Returns:
            List of active EmployeeProfile instances.
        """
        effective_limit = min(limit, 100)
        result = await self._session.execute(
            select(EmployeeProfile)
            .where(EmployeeProfile.deleted_at.is_(None))
            .order_by(EmployeeProfile.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update(
        self,
        user_id: uuid.UUID,
        *,
        employee_code: str | None = None,
        date_of_joining: date | None = None,
        designation: str | None = None,
        salary: Decimal | None = None,
        manager_id: uuid.UUID | None = None,
        emergency_contact: str | None = None,
        address: str | None = None,
        profile_photo: str | None = None,
    ) -> EmployeeProfile | None:
        """
        Partially update an employee profile identified by user_id.

        Only fields explicitly passed as keyword arguments are applied.

        Args:
            user_id: UUID of the associated user.
            **kwargs: Fields to update.

        Returns:
            Refreshed EmployeeProfile, or None if not found.
        """
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if employee_code is not None:
            values["employee_code"] = employee_code
        if date_of_joining is not None:
            values["date_of_joining"] = date_of_joining
        if designation is not None:
            values["designation"] = designation
        if salary is not None:
            values["salary"] = salary
        if manager_id is not None:
            values["manager_id"] = manager_id
        if emergency_contact is not None:
            values["emergency_contact"] = emergency_contact
        if address is not None:
            values["address"] = address
        if profile_photo is not None:
            values["profile_photo"] = profile_photo

        await self._session.execute(
            update(EmployeeProfile)
            .where(
                EmployeeProfile.user_id == user_id,
                EmployeeProfile.deleted_at.is_(None),
            )
            .values(**values)
        )
        return await self.get_by_user_id(user_id)

    async def soft_delete(self, user_id: uuid.UUID) -> None:
        """
        Soft-delete an employee profile by user_id.

        Args:
            user_id: UUID of the associated user.
        """
        await self._session.execute(
            update(EmployeeProfile)
            .where(EmployeeProfile.user_id == user_id)
            .values(deleted_at=datetime.now(UTC))
        )

    async def count_active(self) -> int:
        """
        Return the count of active (non-deleted) employee profiles.

        Used by the dashboard stats endpoint.

        Returns:
            Integer count.
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(EmployeeProfile)
            .where(EmployeeProfile.deleted_at.is_(None))
        )
        return result.scalar_one()
