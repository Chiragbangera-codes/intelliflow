"""
Workflow Engine API routes — Milestone 8.

Endpoints:
  POST   /api/v1/workflows               — create_workflow
  GET    /api/v1/workflows               — list_workflows (paginated)
  GET    /api/v1/workflows/{id}          — get_workflow
  PUT    /api/v1/workflows/{id}          — update_workflow
  DELETE /api/v1/workflows/{id}          — delete_workflow (admin only)

  POST   /api/v1/workflows/{id}/run      — trigger_workflow (returns execution_id)

  GET    /api/v1/workflows/{id}/executions — list_executions
  GET    /api/v1/executions/{id}           — get_execution (status polling)
  POST   /api/v1/executions/{id}/approve   — approve or reject

All routes require JWT authentication.
RBAC is enforced in WorkflowService, not here.
Route handlers are thin: validate → delegate → respond.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.middleware.rate_limit import RateLimiter
from app.models.user import User
from app.schemas.workflow import (
    ApprovalAction,
    WorkflowCreate,
    WorkflowRunRequest,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(tags=["Workflows"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_service(db: AsyncSession = Depends(get_db)) -> WorkflowService:
    """Provide a WorkflowService with the injected DB session."""
    return WorkflowService(db)


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ===========================================================================
# Workflow CRUD
# ===========================================================================


@router.post(
    "/workflows",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workflow",
    description=(
        "Creates a workflow definition with ordered steps. " "Requires manager or admin role."
    ),
    responses={
        201: {"description": "Workflow created successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        422: {"description": "Validation error — invalid step configuration."},
    },
)
async def create_workflow(
    data: WorkflowCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Create a workflow with ordered steps."""
    workflow = await svc.create_workflow(
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Workflow created successfully.",
        "data": workflow.model_dump(mode="json"),
    }


@router.get(
    "/workflows",
    status_code=status.HTTP_200_OK,
    summary="List workflows",
    description="Returns a paginated list of all workflows. All authenticated users may view.",
    responses={
        200: {"description": "Workflows retrieved successfully."},
        401: {"description": "Not authenticated."},
    },
)
async def list_workflows(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """List workflows with pagination."""
    workflows, meta = await svc.list_workflows(
        actor=current_user,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": "Workflows retrieved successfully.",
        "data": [w.model_dump(mode="json") for w in workflows],
        "meta": meta,
    }


@router.get(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a workflow by ID",
    description="Returns a workflow with its steps. All authenticated users may view.",
    responses={
        200: {"description": "Workflow retrieved successfully."},
        401: {"description": "Not authenticated."},
        404: {"description": "Workflow not found."},
    },
)
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Return a single workflow by UUID."""
    workflow = await svc.get_workflow(workflow_id, actor=current_user)
    return {
        "success": True,
        "message": "Workflow retrieved successfully.",
        "data": workflow.model_dump(mode="json"),
    }


@router.put(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a workflow",
    description=(
        "Update workflow metadata and optionally replace steps. " "Requires manager or admin role."
    ),
    responses={
        200: {"description": "Workflow updated successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Workflow not found."},
        422: {"description": "Validation error."},
    },
)
async def update_workflow(
    workflow_id: uuid.UUID,
    data: WorkflowUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Update workflow metadata and optionally replace steps."""
    workflow = await svc.update_workflow(
        workflow_id,
        data,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Workflow updated successfully.",
        "data": workflow.model_dump(mode="json"),
    }


@router.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a workflow",
    description="Soft-deletes a workflow. Admin only.",
    responses={
        200: {"description": "Workflow deleted successfully."},
        401: {"description": "Not authenticated."},
        403: {"description": "Admin role required."},
        404: {"description": "Workflow not found."},
    },
)
async def delete_workflow(
    workflow_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Soft-delete a workflow (admin only)."""
    await svc.delete_workflow(
        workflow_id,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    return {
        "success": True,
        "message": "Workflow deleted successfully.",
    }


# ===========================================================================
# Workflow execution trigger
# ===========================================================================


@router.post(
    "/workflows/{workflow_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(
            RateLimiter(
                max_requests=settings.RATE_LIMIT_WORKFLOWS, window_seconds=60, group="workflow_run"
            )
        )
    ],
    summary="Trigger workflow execution",
    description=(
        "Enqueues a Celery task to execute the workflow. "
        "Returns immediately with the execution_id for status polling. "
        "Requires manager or admin role."
    ),
    responses={
        202: {"description": "Execution enqueued."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Workflow not found."},
        409: {"description": "Workflow is inactive or has no steps."},
    },
)
async def trigger_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowRunRequest | None = None,
    request: Request = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Trigger asynchronous workflow execution."""
    context = body.context if body else None
    run_response = await svc.trigger_workflow(
        workflow_id,
        actor=current_user,
        context=context,
        ip_address=_get_client_ip(request) if request else None,
    )
    return {
        "success": True,
        "message": "Workflow execution enqueued.",
        "data": run_response.model_dump(mode="json"),
    }


# ===========================================================================
# Execution history and polling
# ===========================================================================


@router.get(
    "/workflows/{workflow_id}/executions",
    status_code=status.HTTP_200_OK,
    summary="List workflow executions",
    description="Returns paginated execution history for a workflow.",
    responses={
        200: {"description": "Executions retrieved successfully."},
        401: {"description": "Not authenticated."},
        404: {"description": "Workflow not found."},
    },
)
async def list_executions(
    workflow_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """List execution history for a workflow."""
    executions, meta = await svc.list_executions(
        workflow_id,
        actor=current_user,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": "Executions retrieved successfully.",
        "data": [e.model_dump(mode="json") for e in executions],
        "meta": meta,
    }


@router.get(
    "/executions/{execution_id}",
    status_code=status.HTTP_200_OK,
    summary="Get execution status",
    description="Returns current status and logs for an execution. Used for polling.",
    responses={
        200: {"description": "Execution retrieved successfully."},
        401: {"description": "Not authenticated."},
        404: {"description": "Execution not found."},
    },
)
async def get_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Return execution status and logs for polling."""
    execution = await svc.get_execution(execution_id, actor=current_user)
    return {
        "success": True,
        "message": "Execution retrieved successfully.",
        "data": execution.model_dump(mode="json"),
    }


# ===========================================================================
# Approval gate
# ===========================================================================


@router.post(
    "/executions/{execution_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="Approve or reject a workflow execution",
    description=(
        "Process an approval decision for an execution waiting at an `approve` step. "
        "'approve' resumes the workflow; 'reject' marks it REJECTED. "
        "Requires manager or admin role."
    ),
    responses={
        200: {"description": "Approval decision recorded."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Execution not found."},
        409: {"description": "Execution is not awaiting approval."},
    },
)
async def approve_execution(
    execution_id: uuid.UUID,
    action: ApprovalAction,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: WorkflowService = Depends(_get_service),
) -> dict[str, Any]:
    """Approve or reject an execution awaiting an approval step."""
    execution = await svc.approve_execution(
        execution_id,
        action,
        actor=current_user,
        ip_address=_get_client_ip(request),
    )
    verb = "approved" if action.action == "approve" else "rejected"
    return {
        "success": True,
        "message": f"Execution {verb} successfully.",
        "data": execution.model_dump(mode="json"),
    }
