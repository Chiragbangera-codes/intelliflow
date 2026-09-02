"""
Workflow repository — database access layer for workflows, steps, and executions.

Provides typed async methods for:
  - Workflow CRUD (create, list, get, update, soft-delete)
  - WorkflowStep management (create-in-bulk, replace)
  - WorkflowExecution lifecycle (create, update-status, list, get)
  - Notification creation (for `notify` step)

Architecture:
  Service layer → WorkflowRepository → PostgreSQL
  Never accessed directly from API routes.

Conventions:
  - Soft-deleted workflows (deleted_at IS NOT NULL) are excluded from all
    normal listings and lookups — consistent with existing repositories.
  - Execution status values come from WorkflowExecution.ExecutionStatus ORM enum.
  - All primary keys are UUIDs.
  - flush() after inserts; commit() is the caller's responsibility.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import Notification, NotificationChannel, NotificationPriority
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_execution import ExecutionStatus, WorkflowExecution
from app.models.workflow_step import WorkflowStep


class WorkflowRepository:
    """Handles all database operations for workflows, steps, and executions."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the async database session."""
        self._session = session

    # =========================================================================
    # Workflow CRUD
    # =========================================================================

    async def create_workflow(
        self,
        *,
        name: str,
        description: str | None,
        created_by: uuid.UUID,
        steps: list[dict[str, Any]],
    ) -> Workflow:
        """
        Create a workflow and its ordered steps atomically.

        Steps are inserted in step_number order. The caller must commit.

        Args:
            name:        Human-readable workflow name.
            description: Optional description.
            created_by:  UUID of the creating user.
            steps:       List of step dicts (step_number, action, configuration,
                         timeout, retry_count).

        Returns:
            Refreshed Workflow with steps loaded.
        """
        workflow = Workflow(
            name=name,
            description=description,
            created_by=created_by,
            is_active=True,
        )
        self._session.add(workflow)
        await self._session.flush()

        for step_data in steps:
            step = WorkflowStep(
                workflow_id=workflow.id,
                step_number=step_data["step_number"],
                action=step_data["action"],
                configuration=step_data.get("configuration"),
                timeout=step_data.get("timeout"),
                retry_count=step_data.get("retry_count", 0),
            )
            self._session.add(step)

        await self._session.flush()
        await self._session.refresh(workflow)
        return workflow

    async def get_by_id(
        self,
        workflow_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Workflow | None:
        """
        Return a workflow by UUID, optionally with steps eager-loaded.

        Args:
            workflow_id:     UUID of the workflow.
            include_deleted: If True, soft-deleted workflows are included.

        Returns:
            Workflow with steps loaded via selectin, or None.
        """
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
            .execution_options(populate_existing=True)
        )
        if not include_deleted:
            stmt = stmt.where(Workflow.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        created_by: uuid.UUID | None = None,
    ) -> list[Workflow]:
        """
        Return a paginated list of non-deleted workflows.

        Args:
            limit:      Maximum records to return.
            offset:     Pagination offset.
            created_by: If set, restrict to workflows created by this user.

        Returns:
            List of Workflow instances with steps loaded.
        """
        effective_limit = min(max(limit, 1), 100)
        stmt = (
            select(Workflow)
            .where(Workflow.deleted_at.is_(None))
            .options(selectinload(Workflow.steps))
            .order_by(Workflow.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        if created_by is not None:
            stmt = stmt.where(Workflow.created_by == created_by)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_workflows(
        self,
        *,
        created_by: uuid.UUID | None = None,
    ) -> int:
        """Return count of active (non-deleted) workflows."""
        stmt = select(func.count()).select_from(Workflow).where(Workflow.deleted_at.is_(None))
        if created_by is not None:
            stmt = stmt.where(Workflow.created_by == created_by)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_active_workflows(self) -> int:
        """Return count of active (is_active=True, non-deleted) workflows for dashboard."""
        result = await self._session.execute(
            select(func.count())
            .select_from(Workflow)
            .where(
                Workflow.deleted_at.is_(None),
                Workflow.is_active.is_(True),
            )
        )
        return result.scalar_one()

    async def update_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> Workflow | None:
        """
        Partially update a workflow's metadata and optionally replace its steps.

        If `steps` is provided, existing steps are deleted and replaced.
        The caller must commit.

        Returns:
            Refreshed Workflow, or None if not found.
        """
        values: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        if is_active is not None:
            values["is_active"] = is_active

        await self._session.execute(
            update(Workflow)
            .where(Workflow.id == workflow_id, Workflow.deleted_at.is_(None))
            .values(**values)
        )

        if steps is not None:
            # Delete existing steps then insert replacements
            existing = await self._session.execute(
                select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id)
            )
            for old_step in existing.scalars().all():
                await self._session.delete(old_step)
            await self._session.flush()

            for step_data in steps:
                self._session.add(
                    WorkflowStep(
                        workflow_id=workflow_id,
                        step_number=step_data["step_number"],
                        action=step_data["action"],
                        configuration=step_data.get("configuration"),
                        timeout=step_data.get("timeout"),
                        retry_count=step_data.get("retry_count", 0),
                    )
                )

        await self._session.flush()
        return await self.get_by_id(workflow_id)

    async def soft_delete_workflow(self, workflow_id: uuid.UUID) -> None:
        """
        Soft-delete a workflow by setting deleted_at.

        Existing executions are preserved for audit purposes.
        """
        await self._session.execute(
            update(Workflow).where(Workflow.id == workflow_id).values(deleted_at=datetime.now(UTC))
        )

    # =========================================================================
    # WorkflowExecution lifecycle
    # =========================================================================

    async def create_execution(
        self,
        *,
        workflow_id: uuid.UUID,
        triggered_by: uuid.UUID | None,
    ) -> WorkflowExecution:
        """
        Create a new WorkflowExecution record in PENDING status.

        Args:
            workflow_id:  UUID of the workflow being executed.
            triggered_by: UUID of the user who triggered it (None for system).

        Returns:
            Refreshed WorkflowExecution in PENDING status.
        """
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            triggered_by=triggered_by,
            status=ExecutionStatus.PENDING,
            logs={"steps": []},
        )
        self._session.add(execution)
        await self._session.flush()
        await self._session.refresh(execution)
        return execution

    async def get_execution_by_id(self, execution_id: uuid.UUID) -> WorkflowExecution | None:
        """Return a WorkflowExecution by UUID."""
        result = await self._session.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        workflow_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        """
        Return paginated execution history for a workflow.

        Args:
            workflow_id: UUID of the workflow.
            limit:       Maximum records to return.
            offset:      Pagination offset.

        Returns:
            List of WorkflowExecution instances ordered by created_at desc.
        """
        effective_limit = min(max(limit, 1), 100)
        result = await self._session.execute(
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.created_at.desc())
            .limit(effective_limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_executions(self, workflow_id: uuid.UUID) -> int:
        """Return the total execution count for a workflow."""
        result = await self._session.execute(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
        )
        return result.scalar_one()

    async def update_execution_status(
        self,
        execution_id: uuid.UUID,
        *,
        status: ExecutionStatus,
        logs: dict[str, Any] | None = None,
        duration: float | None = None,
    ) -> WorkflowExecution | None:
        """
        Atomically update execution status, logs, and optionally duration.

        Args:
            execution_id: UUID of the execution to update.
            status:       New ExecutionStatus value.
            logs:         Full replacement of logs JSON (not merged).
            duration:     Wall-clock seconds for completed/failed executions.

        Returns:
            Refreshed WorkflowExecution, or None if not found.
        """
        values: dict[str, object] = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }
        if logs is not None:
            values["logs"] = logs
        if duration is not None:
            values["duration"] = duration

        await self._session.execute(
            update(WorkflowExecution).where(WorkflowExecution.id == execution_id).values(**values)
        )
        await self._session.flush()
        return await self.get_execution_by_id(execution_id)

    async def count_pending_executions(self) -> int:
        """
        Count executions in non-terminal states for dashboard stats.

        Includes: PENDING, RUNNING, WAITING_APPROVAL (if the enum has it).
        Excludes: COMPLETED, FAILED, CANCELLED, REJECTED.
        """
        active_statuses = [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]
        # Include WAITING_APPROVAL if it exists in the enum
        if hasattr(ExecutionStatus, "WAITING_APPROVAL"):
            active_statuses.append(ExecutionStatus.WAITING_APPROVAL)
        result = await self._session.execute(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(WorkflowExecution.status.in_(active_statuses))
        )
        return result.scalar_one()

    # =========================================================================
    # Notification creation (used by workflow_tasks and service)
    # =========================================================================

    async def create_notification(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> Notification:
        """
        Create an in-app notification record.

        Args:
            user_id:  UUID of the recipient user.
            title:    Short notification title.
            message:  Full notification message.
            priority: Notification priority level.

        Returns:
            Persisted Notification instance.
        """
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            channel=NotificationChannel.IN_APP,
            priority=priority,
        )
        self._session.add(notification)
        await self._session.flush()
        await self._session.refresh(notification)
        return notification

    # =========================================================================
    # User existence check (for `notify` step validation)
    # =========================================================================

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return a non-deleted user by UUID."""
        result = await self._session.execute(
            select(User).where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
