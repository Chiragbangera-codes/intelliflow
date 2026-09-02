"""
Workflow service — business logic for the workflow engine (Milestone 8).

Responsibilities:
  - Enforce RBAC (create/run: manager+admin; delete: admin only;
    approve: manager+admin; view: all authenticated).
  - Validate workflow integrity before persisting.
  - Dispatch Celery execution tasks without blocking the API request.
  - Manage the approval gate lifecycle.
  - Write audit log entries for all mutating operations.
  - Delegate all database access to WorkflowRepository.

Architecture:
  API (thin route) → WorkflowService → WorkflowRepository → PostgreSQL
                                     ↘ Celery (fire-and-forget)

Security:
  - RBAC is enforced here using the authenticated actor, never from
    caller-supplied role strings.
  - Document ownership is verified server-side before archiving.
  - SMTP credentials are never exposed in responses or logs.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workflow_execution import ExecutionStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import (
    ApprovalAction,
    WorkflowCreate,
    WorkflowExecutionResponse,
    WorkflowResponse,
    WorkflowRunResponse,
    WorkflowUpdate,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Roles permitted to create and trigger workflows
_CREATE_RUN_ROLES = frozenset({"manager", "admin"})
# Roles permitted to approve/reject execution approval steps
_APPROVE_ROLES = frozenset({"manager", "admin"})
# Roles permitted to delete workflows
_DELETE_ROLES = frozenset({"admin"})
# Roles with global visibility (see all workflows)
_ADMIN_ROLES = frozenset({"admin", "hr"})


def _require_role(actor: User, allowed: frozenset[str], detail: str = "") -> None:
    """Raise 403 if actor's role is not in the allowed set."""
    role_name = (
        actor.role.name.lower()
        if actor.role and hasattr(actor.role, "name") and actor.role.name
        else str(getattr(actor, "role", "")).lower()
    )
    if role_name not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail or "You do not have permission to perform this action.",
        )


class WorkflowService:
    """Encapsulates all workflow business logic for Milestone 8."""

    def __init__(self, session: AsyncSession) -> None:
        """Inject the database session and initialise repositories."""
        self._session = session
        self._workflows = WorkflowRepository(session)
        self._documents = DocumentRepository(session)
        self._audit = AuditLogRepository(session)

    # =========================================================================
    # Workflow CRUD
    # =========================================================================

    async def create_workflow(
        self,
        data: WorkflowCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> WorkflowResponse:
        """
        Create a new workflow with ordered steps.

        RBAC: manager, admin.

        Args:
            data:       Validated WorkflowCreate payload.
            actor:      Authenticated requesting user.
            ip_address: Client IP for audit.

        Returns:
            WorkflowResponse of the created workflow.
        """
        _require_role(actor, _CREATE_RUN_ROLES, "Only managers and admins may create workflows.")

        steps = [
            {
                "step_number": s.step_number,
                "action": s.action,
                "configuration": s.configuration,
                "timeout": s.timeout,
                "retry_count": s.retry_count,
            }
            for s in data.steps
        ]

        workflow = await self._workflows.create_workflow(
            name=data.name,
            description=data.description,
            created_by=actor.id,
            steps=steps,
        )
        await self._audit.create(
            action="workflow.created",
            user_id=actor.id,
            table_name="workflows",
            record_id=workflow.id,
            new_value={
                "name": workflow.name,
                "step_count": len(steps),
                "actor_id": str(actor.id),
            },
            ip_address=ip_address,
        )
        await self._session.commit()
        await self._session.refresh(workflow)

        # Reload with steps for response
        refreshed = await self._workflows.get_by_id(workflow.id)
        assert refreshed is not None
        return WorkflowResponse.from_orm_with_creator(refreshed)

    async def list_workflows(
        self,
        *,
        actor: User,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WorkflowResponse], dict[str, int]]:
        """
        Return a paginated list of workflows scoped by role.

        admin/hr: see all workflows.
        manager:  see all workflows (for Phase 8 scope).
        employee: see all workflows (read-only).

        Args:
            actor:     Authenticated user.
            page:      1-based page number.
            page_size: Records per page (max 100).

        Returns:
            Tuple of (workflow list, pagination meta dict).
        """
        effective_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * effective_size

        workflows = await self._workflows.list_workflows(
            limit=effective_size,
            offset=offset,
        )
        total = await self._workflows.count_workflows()
        total_pages = max(math.ceil(total / effective_size), 1) if total else 1

        data = [WorkflowResponse.from_orm_with_creator(w) for w in workflows]
        meta = {
            "page": page,
            "page_size": effective_size,
            "total_items": total,
            "total_pages": total_pages,
        }
        return data, meta

    async def get_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        actor: User,
    ) -> WorkflowResponse:
        """
        Return a single workflow by UUID.

        All authenticated users may view workflows (read-only).
        Returns 404 if not found or soft-deleted.

        Args:
            workflow_id: UUID of the target workflow.
            actor:       Authenticated user.

        Returns:
            WorkflowResponse with steps.
        """
        workflow = await self._workflows.get_by_id(workflow_id)
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found.",
            )
        return WorkflowResponse.from_orm_with_creator(workflow)

    async def update_workflow(
        self,
        workflow_id: uuid.UUID,
        data: WorkflowUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> WorkflowResponse:
        """
        Update workflow metadata and optionally replace steps.

        RBAC: manager, admin.

        Args:
            workflow_id: UUID of the workflow to update.
            data:        Validated WorkflowUpdate payload.
            actor:       Authenticated user.
            ip_address:  Client IP for audit.

        Returns:
            Updated WorkflowResponse.
        """
        _require_role(actor, _CREATE_RUN_ROLES, "Only managers and admins may update workflows.")

        # Verify workflow exists
        existing = await self._workflows.get_by_id(workflow_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found.",
            )

        steps: list[dict[str, Any]] | None = None
        if data.steps is not None:
            steps = [
                {
                    "step_number": s.step_number,
                    "action": s.action,
                    "configuration": s.configuration,
                    "timeout": s.timeout,
                    "retry_count": s.retry_count,
                }
                for s in data.steps
            ]

        updated = await self._workflows.update_workflow(
            workflow_id,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            steps=steps,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found.",
            )

        await self._audit.create(
            action="workflow.updated",
            user_id=actor.id,
            table_name="workflows",
            record_id=workflow_id,
            new_value={
                "name": data.name,
                "is_active": data.is_active,
                "steps_replaced": data.steps is not None,
                "actor_id": str(actor.id),
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        refreshed = await self._workflows.get_by_id(workflow_id)
        assert refreshed is not None
        return WorkflowResponse.from_orm_with_creator(refreshed)

    async def delete_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """
        Soft-delete a workflow.

        RBAC: admin only.

        Args:
            workflow_id: UUID of the workflow to delete.
            actor:       Authenticated user.
            ip_address:  Client IP for audit.
        """
        _require_role(actor, _DELETE_ROLES, "Only admins may delete workflows.")

        existing = await self._workflows.get_by_id(workflow_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found.",
            )

        await self._workflows.soft_delete_workflow(workflow_id)
        await self._audit.create(
            action="workflow.deleted",
            user_id=actor.id,
            table_name="workflows",
            record_id=workflow_id,
            new_value={"actor_id": str(actor.id)},
            ip_address=ip_address,
        )
        await self._session.commit()

    # =========================================================================
    # Workflow execution
    # =========================================================================

    async def trigger_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        actor: User,
        context: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> WorkflowRunResponse:
        """
        Trigger a workflow execution asynchronously.

        RBAC: manager, admin.

        Creates a WorkflowExecution record in PENDING status, commits,
        then dispatches the Celery task. Returns immediately without
        waiting for the task to complete.

        Args:
            workflow_id: UUID of the workflow to run.
            actor:       Authenticated user triggering the execution.
            context:     Optional runtime context (passed to task).
            ip_address:  Client IP for audit.

        Returns:
            WorkflowRunResponse with the new execution_id.
        """
        _require_role(actor, _CREATE_RUN_ROLES, "Only managers and admins may trigger workflows.")

        workflow = await self._workflows.get_by_id(workflow_id)
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found.",
            )
        if not workflow.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot execute an inactive workflow. Activate the workflow first.",
            )
        if not workflow.steps:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot execute a workflow with no steps.",
            )

        # Create execution record before dispatching the task
        execution = await self._workflows.create_execution(
            workflow_id=workflow_id,
            triggered_by=actor.id,
        )
        await self._audit.create(
            action="workflow.triggered",
            user_id=actor.id,
            table_name="workflow_executions",
            record_id=execution.id,
            new_value={
                "workflow_id": str(workflow_id),
                "workflow_name": workflow.name,
                "actor_id": str(actor.id),
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        # Dispatch Celery task — fire-and-forget
        execution_id_str = str(execution.id)
        try:
            celery_app.send_task(
                "tasks.execute_workflow",
                args=[execution_id_str],
            )
            logger.info(
                "Dispatched workflow execution task execution_id=%s workflow_id=%s",
                execution_id_str,
                workflow_id,
            )
        except Exception as exc:
            # Task dispatch failure must not fail the API request — the
            # execution record is in PENDING; an operator can retry manually.
            logger.error(
                "Failed to dispatch workflow task for execution %s: %s",
                execution_id_str,
                exc,
            )

        return WorkflowRunResponse(
            execution_id=execution.id,
            status=ExecutionStatus.PENDING.value,
        )

    async def get_execution(
        self,
        execution_id: uuid.UUID,
        *,
        actor: User,
    ) -> WorkflowExecutionResponse:
        """
        Return a single execution record for status polling.

        All authenticated users may view executions.

        Args:
            execution_id: UUID of the execution.
            actor:        Authenticated user.

        Returns:
            WorkflowExecutionResponse.
        """
        execution = await self._workflows.get_execution_by_id(execution_id)
        if execution is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution not found.",
            )
        return WorkflowExecutionResponse.model_validate(execution)

    async def list_executions(
        self,
        workflow_id: uuid.UUID,
        *,
        actor: User,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WorkflowExecutionResponse], dict[str, int]]:
        """
        Return paginated execution history for a workflow.

        All authenticated users may view execution history.

        Args:
            workflow_id: UUID of the workflow.
            actor:       Authenticated user.
            page:        1-based page number.
            page_size:   Records per page.

        Returns:
            Tuple of (execution list, pagination meta dict).
        """
        # Verify workflow exists
        workflow = await self._workflows.get_by_id(workflow_id)
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found.",
            )

        effective_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * effective_size

        executions = await self._workflows.list_executions(
            workflow_id,
            limit=effective_size,
            offset=offset,
        )
        total = await self._workflows.count_executions(workflow_id)
        total_pages = max(math.ceil(total / effective_size), 1) if total else 1

        data = [WorkflowExecutionResponse.model_validate(e) for e in executions]
        meta = {
            "page": page,
            "page_size": effective_size,
            "total_items": total,
            "total_pages": total_pages,
        }
        return data, meta

    # =========================================================================
    # Approval gate
    # =========================================================================

    async def approve_execution(
        self,
        execution_id: uuid.UUID,
        action: ApprovalAction,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> WorkflowExecutionResponse:
        """
        Process an approve or reject decision for an awaiting execution.

        RBAC: manager, admin.

        The execution must currently be in WAITING_APPROVAL status.
        Duplicate approvals are rejected with 409 Conflict.
        After persisting the decision, the appropriate Celery task is
        dispatched to resume or terminate the execution.

        Args:
            execution_id: UUID of the execution to approve/reject.
            action:       ApprovalAction with action and optional comment.
            actor:        Authenticated user making the decision.
            ip_address:   Client IP for audit.

        Returns:
            Updated WorkflowExecutionResponse.
        """
        _require_role(
            actor, _APPROVE_ROLES, "Only managers and admins may approve workflow executions."
        )

        execution = await self._workflows.get_execution_by_id(execution_id)
        if execution is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution not found.",
            )

        if execution.status != ExecutionStatus.WAITING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Execution is not awaiting approval "
                    f"(current status: {execution.status.value})."
                ),
            )

        # Update logs to record the approval decision
        existing_logs: dict[str, Any] = dict(execution.logs or {})
        existing_logs["approval"] = {
            "decision": action.action,
            "approved_by": str(actor.id),
            "approved_at": datetime.now(UTC).isoformat(),
            "comment": action.comment,
        }

        if action.action == "approve":
            new_status = ExecutionStatus.RUNNING
            audit_action = "workflow.approved"
            logger.info(
                "Execution %s approved by user %s. Dispatching resume task.",
                execution_id,
                actor.id,
            )
        else:
            new_status = ExecutionStatus.REJECTED
            audit_action = "workflow.rejected"
            existing_logs["error"] = "Execution rejected by approver."
            logger.info(
                "Execution %s rejected by user %s.",
                execution_id,
                actor.id,
            )

        updated = await self._workflows.update_execution_status(
            execution_id,
            status=new_status,
            logs=existing_logs,
        )

        await self._audit.create(
            action=audit_action,
            user_id=actor.id,
            table_name="workflow_executions",
            record_id=execution_id,
            new_value={
                "decision": action.action,
                "actor_id": str(actor.id),
                "comment": action.comment,
            },
            ip_address=ip_address,
        )
        await self._session.commit()

        # Dispatch resume task only when approved
        if action.action == "approve":
            try:
                celery_app.send_task(
                    "tasks.resume_workflow",
                    args=[str(execution_id)],
                )
            except Exception as exc:
                logger.error(
                    "Failed to dispatch resume task for execution %s: %s",
                    execution_id,
                    exc,
                )

        assert updated is not None
        return WorkflowExecutionResponse.model_validate(updated)
