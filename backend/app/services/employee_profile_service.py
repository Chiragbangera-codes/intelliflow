"""
Employee profile service — business logic for HR employee data.

Authorization rules (server-enforced, never client-supplied):
  - admin / hr : list all, create/update any profile
  - manager    : list all (to see their reports), cannot create/update others
  - employee   : view/create/update ONLY their own profile

user_id for any write operation comes from the URL path, and ownership is
validated here — the API layer must never pass a client-supplied user_id
directly to authorize access.

Architecture: API → EmployeeProfileService → EmployeeProfileRepository → PostgreSQL
"""

import logging
import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.employee_profile_repository import EmployeeProfileRepository
from app.repositories.user_repository import UserRepository
from app.schemas.employee import (
    EmployeeProfileCreate,
    EmployeeProfileResponse,
    EmployeeProfileUpdate,
    PaginatedEmployeeResponse,
)

logger = logging.getLogger(__name__)

# Roles that may access any employee profile (not just their own).
_PRIVILEGED_ROLES = frozenset({"admin", "hr", "manager"})
# Roles that may create or update any employee profile.
_WRITE_PRIVILEGED_ROLES = frozenset({"admin", "hr"})


def _get_role_name(user: User) -> str:
    """Safely extract the role name from a User object."""
    if user.role and hasattr(user.role, "name") and user.role.name:
        return user.role.name.lower()
    return str(getattr(user, "role", "employee")).lower()


def _build_response(profile: EmployeeProfile, user: User) -> EmployeeProfileResponse:
    """
    Construct an EmployeeProfileResponse from an ORM profile and its owner user.

    The profile's `user` relationship is selectin-loaded, but we accept
    the user object explicitly to avoid relying on lazy attribute access.
    """
    # Use the selectin-loaded user relationship if available, else fall back
    owner: User = getattr(profile, "user", None) or user
    return EmployeeProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        employee_code=profile.employee_code,
        date_of_joining=profile.date_of_joining,
        designation=profile.designation,
        salary=profile.salary,
        manager_id=profile.manager_id,
        emergency_contact=profile.emergency_contact,
        address=profile.address,
        profile_photo=profile.profile_photo,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        first_name=owner.first_name,
        last_name=owner.last_name,
        email=owner.email,
        role=_get_role_name(owner),
    )


class EmployeeProfileService:
    """Encapsulates all employee profile business logic."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the database session and initialise repositories."""
        self._session = session
        self._profiles = EmployeeProfileRepository(session)
        self._users = UserRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Read — list
    # ------------------------------------------------------------------

    async def list_profiles(
        self,
        *,
        actor: User,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedEmployeeResponse:
        """
        Return a paginated list of employee profiles.

        Access:
          - admin / hr / manager : all active profiles
          - employee             : only their own profile (single-item list)

        Args:
            actor:     Authenticated user.
            page:      1-based page number.
            page_size: Records per page (max 100).
        """
        effective_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * effective_size
        actor_role = _get_role_name(actor)

        if actor_role in _PRIVILEGED_ROLES:
            profiles = await self._profiles.list_active(limit=effective_size, offset=offset)
            # For total count use a separate count query via count_active
            total = await self._profiles.count_active()
        else:
            # Employee: only their own profile
            profile = await self._profiles.get_by_user_id(actor.id)
            profiles = [profile] if profile is not None else []
            total = len(profiles)

        total_pages = max(math.ceil(total / effective_size), 1) if total else 1

        data = []
        for p in profiles:
            owner = await self._users.get_by_id(p.user_id)
            if owner is not None:
                data.append(_build_response(p, owner))

        return PaginatedEmployeeResponse(
            data=data,
            meta={
                "page": page,
                "page_size": effective_size,
                "total_items": total,
                "total_pages": total_pages,
            },
        )

    # ------------------------------------------------------------------
    # Read — single
    # ------------------------------------------------------------------

    async def get_profile(
        self,
        target_user_id: uuid.UUID,
        *,
        actor: User,
    ) -> EmployeeProfileResponse:
        """
        Return a single employee profile by target user's UUID.

        Access:
          - admin / hr / manager : any profile
          - employee             : only own profile

        Raises:
            HTTPException 403: Employee attempting to access another's profile.
            HTTPException 404: Profile not found.
        """
        actor_role = _get_role_name(actor)

        if actor_role not in _PRIVILEGED_ROLES and actor.id != target_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this profile.",
            )

        profile = await self._profiles.get_by_user_id(target_user_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee profile not found.",
            )

        owner = await self._users.get_by_id(target_user_id)
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated user not found.",
            )

        return _build_response(profile, owner)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_profile(
        self,
        target_user_id: uuid.UUID,
        data: EmployeeProfileCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> EmployeeProfileResponse:
        """
        Create an employee profile for the target user.

        Access:
          - admin / hr   : can create for any user
          - employee     : can create only for themselves
          - manager      : not allowed (403)

        Raises:
            HTTPException 403: Insufficient role.
            HTTPException 404: Target user not found.
            HTTPException 409: Profile already exists for this user.
        """
        actor_role = _get_role_name(actor)

        # Authorization: only admin/hr or the user themselves
        if actor_role not in _WRITE_PRIVILEGED_ROLES and actor.id != target_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to create a profile for this user.",
            )

        target_user = await self._users.get_by_id(target_user_id)
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        existing = await self._profiles.get_by_user_id(target_user_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An employee profile already exists for this user.",
            )

        # Validate employee_code uniqueness if provided
        if data.employee_code:
            code_conflict = await self._profiles.get_by_employee_code(data.employee_code)
            if code_conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Employee code '{data.employee_code}' is already in use.",
                )

        # Validate manager_id points to a real user if provided
        if data.manager_id is not None:
            manager = await self._users.get_by_id(data.manager_id)
            if manager is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Manager user not found.",
                )

        profile = await self._profiles.create(
            user_id=target_user_id,
            employee_code=data.employee_code,
            date_of_joining=data.date_of_joining,
            designation=data.designation,
            salary=data.salary,
            manager_id=data.manager_id,
            emergency_contact=data.emergency_contact,
            address=data.address,
            profile_photo=data.profile_photo,
        )

        await self._audit.create(
            action="employee_profile.create",
            user_id=actor.id,
            table_name="employee_profiles",
            record_id=profile.id,
            new_value={"user_id": str(target_user_id), "employee_code": data.employee_code},
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(profile)

        logger.info(
            "Employee profile created: user_id=%s actor=%s",
            target_user_id,
            actor.id,
        )
        return _build_response(profile, target_user)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_profile(
        self,
        target_user_id: uuid.UUID,
        data: EmployeeProfileUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> EmployeeProfileResponse:
        """
        Partially update an employee profile.

        Access:
          - admin / hr : can update any profile
          - employee   : can update only their own profile

        Raises:
            HTTPException 403: Insufficient role.
            HTTPException 404: Profile not found.
            HTTPException 409: Employee code already in use.
        """
        actor_role = _get_role_name(actor)

        if actor_role not in _WRITE_PRIVILEGED_ROLES and actor.id != target_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this profile.",
            )

        profile = await self._profiles.get_by_user_id(target_user_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee profile not found.",
            )

        if data.employee_code is not None and data.employee_code != profile.employee_code:
            code_conflict = await self._profiles.get_by_employee_code(data.employee_code)
            if code_conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Employee code '{data.employee_code}' is already in use.",
                )

        if data.manager_id is not None:
            manager = await self._users.get_by_id(data.manager_id)
            if manager is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Manager user not found.",
                )

        old_value = {
            "employee_code": profile.employee_code,
            "designation": profile.designation,
        }

        updated = await self._profiles.update(
            target_user_id,
            employee_code=data.employee_code,
            date_of_joining=data.date_of_joining,
            designation=data.designation,
            salary=data.salary,
            manager_id=data.manager_id,
            emergency_contact=data.emergency_contact,
            address=data.address,
            profile_photo=data.profile_photo,
        )

        audit_new_value: dict[str, object] = {}
        if data.employee_code is not None:
            audit_new_value["employee_code"] = data.employee_code
        if data.designation is not None:
            audit_new_value["designation"] = data.designation

        await self._audit.create(
            action="employee_profile.update",
            user_id=actor.id,
            table_name="employee_profiles",
            record_id=profile.id,
            old_value=old_value,
            new_value=audit_new_value,
            ip_address=ip_address,
        )

        await self._session.commit()

        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee profile not found after update.",
            )

        await self._session.refresh(updated)
        owner = await self._users.get_by_id(target_user_id)
        if owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        logger.info("Employee profile updated: user_id=%s actor=%s", target_user_id, actor.id)
        return _build_response(updated, owner)
