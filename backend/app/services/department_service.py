"""
Department service — business logic for department management.

Responsibilities:
  - Enforce name uniqueness (409 on duplicate).
  - Delegate all DB access to DepartmentRepository.
  - Write audit log entries for mutating operations.
  - Never execute SQL directly.

Architecture: API → DepartmentService → DepartmentRepository → PostgreSQL
"""

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.department_repository import DepartmentRepository
from app.schemas.department import DepartmentCreate, DepartmentResponse, DepartmentUpdate

logger = logging.getLogger(__name__)


class DepartmentService:
    """Encapsulates all department business logic."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the database session and initialise repositories."""
        self._session = session
        self._departments = DepartmentRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_departments(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DepartmentResponse], dict[str, int]]:
        """
        Return a paginated list of active departments.

        Args:
            page:      1-based page number.
            page_size: Records per page (max 100).

        Returns:
            Tuple of (department list, pagination meta dict).
        """
        effective_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * effective_size

        departments = await self._departments.list_active()
        total = len(departments)

        # Apply pagination manually on the in-memory list
        # (list_active returns all; for large datasets this would use limit/offset)
        page_items = departments[offset : offset + effective_size]

        import math

        total_pages = max(math.ceil(total / effective_size), 1) if total else 1

        data = [DepartmentResponse.model_validate(d) for d in page_items]
        meta = {
            "page": page,
            "page_size": effective_size,
            "total_items": total,
            "total_pages": total_pages,
        }
        return data, meta

    async def get_department(self, department_id: uuid.UUID) -> DepartmentResponse:
        """
        Return a single active department by UUID.

        Raises:
            HTTPException 404: If not found or soft-deleted.
        """
        dept = await self._departments.get_by_id(department_id)
        if dept is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found.",
            )
        return DepartmentResponse.model_validate(dept)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_department(
        self,
        data: DepartmentCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DepartmentResponse:
        """
        Create a new department.

        Flow:
          1. Check name uniqueness → 409 if duplicate.
          2. Persist department.
          3. Write audit log.
          4. Commit.
          5. Return response.

        Args:
            data:       Validated creation payload.
            actor:      Authenticated user performing the action.
            ip_address: Client IP for audit log.

        Raises:
            HTTPException 409: If a department with the same name exists.
        """
        existing = await self._departments.get_by_name(data.name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A department named '{data.name}' already exists.",
            )

        dept = await self._departments.create(
            name=data.name,
            description=data.description,
        )

        await self._audit.create(
            action="department.create",
            user_id=actor.id,
            table_name="departments",
            record_id=dept.id,
            new_value={"name": dept.name, "description": dept.description},
            ip_address=ip_address,
        )

        await self._session.commit()
        await self._session.refresh(dept)

        logger.info("Department created: id=%s name=%r actor=%s", dept.id, dept.name, actor.id)
        return DepartmentResponse.model_validate(dept)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_department(
        self,
        department_id: uuid.UUID,
        data: DepartmentUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> DepartmentResponse:
        """
        Partially update a department.

        Raises:
            HTTPException 404: If not found.
            HTTPException 409: If the new name conflicts with another department.
        """
        dept = await self._departments.get_by_id(department_id)
        if dept is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found.",
            )

        if data.name is not None and data.name != dept.name:
            conflict = await self._departments.get_by_name(data.name)
            if conflict is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A department named '{data.name}' already exists.",
                )

        old_value = {"name": dept.name, "description": dept.description}

        updated = await self._departments.update(
            department_id,
            name=data.name,
            description=data.description,
        )

        await self._audit.create(
            action="department.update",
            user_id=actor.id,
            table_name="departments",
            record_id=department_id,
            old_value=old_value,
            new_value={"name": data.name, "description": data.description},
            ip_address=ip_address,
        )

        await self._session.commit()

        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found.",
            )

        await self._session.refresh(updated)
        logger.info("Department updated: id=%s actor=%s", department_id, actor.id)
        return DepartmentResponse.model_validate(updated)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_department(
        self,
        department_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """
        Soft-delete a department.

        Note: If the department has active users, the DB FK RESTRICT will
        raise an IntegrityError — let it propagate as a 500 (the caller
        should check for users first in future milestones).

        Raises:
            HTTPException 404: If not found.
        """
        dept = await self._departments.get_by_id(department_id)
        if dept is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found.",
            )

        await self._departments.soft_delete(department_id)

        await self._audit.create(
            action="department.delete",
            user_id=actor.id,
            table_name="departments",
            record_id=department_id,
            old_value={"name": dept.name},
            ip_address=ip_address,
        )

        await self._session.commit()
        logger.info("Department soft-deleted: id=%s actor=%s", department_id, actor.id)
