"""
Integration tests for the Workflow Engine API — Milestone 8.

Tests cover:
  - POST   /api/v1/workflows               (CRUD)
  - GET    /api/v1/workflows
  - GET    /api/v1/workflows/{id}
  - PUT    /api/v1/workflows/{id}
  - DELETE /api/v1/workflows/{id}
  - POST   /api/v1/workflows/{id}/run
  - GET    /api/v1/workflows/{id}/executions
  - GET    /api/v1/executions/{id}
  - POST   /api/v1/executions/{id}/approve

Test strategy:
  - Celery tasks are NOT dispatched in tests — they would require a live Redis
    broker. Instead, the execution record is created by the service and its
    status is verified directly.
  - Approval gate is tested by manually setting WAITING_APPROVAL status via
    the repository and then calling the approve endpoint.
  - RBAC rules are verified with employee (should 403) vs manager (should 201).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workflow_execution import ExecutionStatus

# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _minimal_workflow_payload(**overrides: object) -> dict:
    base = {
        "name": "Test Workflow",
        "description": "A workflow for testing.",
        "steps": [
            {
                "step_number": 1,
                "action": "notify",
                "configuration": {
                    "user_id": "00000000-0000-0000-0000-000000000001",
                    "title": "Hello",
                    "message": "World",
                },
            }
        ],
    }
    base.update(overrides)
    return base


def _delay_workflow_payload() -> dict:
    return {
        "name": "Delay Workflow",
        "steps": [
            {
                "step_number": 1,
                "action": "delay",
                "configuration": {"seconds": 1},
            }
        ],
    }


# ===========================================================================
# POST /api/v1/workflows — create
# ===========================================================================


@pytest.mark.asyncio
async def test_create_workflow_manager(
    async_client: AsyncClient,
    manager_user: User,
    manager_headers: dict,
) -> None:
    """Manager should be able to create a workflow."""
    payload = _minimal_workflow_payload()
    # Patch the notify user lookup to avoid validation failure in tests
    response = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers=manager_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["name"] == "Test Workflow"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["action"] == "notify"


@pytest.mark.asyncio
async def test_create_workflow_admin(
    async_client: AsyncClient,
    admin_user: User,
    admin_headers: dict,
) -> None:
    """Admin should be able to create a workflow."""
    response = await async_client.post(
        "/api/v1/workflows",
        json=_minimal_workflow_payload(name="Admin Workflow"),
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "Admin Workflow"


@pytest.mark.asyncio
async def test_create_workflow_employee_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
) -> None:
    """Employee (default test_user) must receive 403 when creating a workflow."""
    response = await async_client.post(
        "/api/v1/workflows",
        json=_minimal_workflow_payload(),
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_workflow_unauthenticated(async_client: AsyncClient) -> None:
    """Unauthenticated request must receive 401."""
    response = await async_client.post(
        "/api/v1/workflows",
        json=_minimal_workflow_payload(),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_workflow_invalid_action(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Unknown action type must result in 422."""
    payload = {
        "name": "Bad Workflow",
        "steps": [{"step_number": 1, "action": "fly_to_moon", "configuration": None}],
    }
    response = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers=manager_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_workflow_duplicate_step_numbers(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Non-contiguous step numbers must result in 422."""
    payload = {
        "name": "Bad Steps",
        "steps": [
            {
                "step_number": 1,
                "action": "delay",
                "configuration": {"seconds": 1},
            },
            {
                "step_number": 1,  # duplicate
                "action": "delay",
                "configuration": {"seconds": 2},
            },
        ],
    }
    response = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers=manager_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_workflow_missing_delay_config(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """delay step without configuration must result in 422."""
    payload = {
        "name": "Bad Delay",
        "steps": [{"step_number": 1, "action": "delay", "configuration": None}],
    }
    response = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers=manager_headers,
    )
    assert response.status_code == 422


# ===========================================================================
# GET /api/v1/workflows — list
# ===========================================================================


@pytest.mark.asyncio
async def test_list_workflows_empty(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """List returns empty result when no workflows exist."""
    response = await async_client.get("/api/v1/workflows", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert body["meta"]["total_items"] == 0


@pytest.mark.asyncio
async def test_list_workflows_after_create(
    async_client: AsyncClient,
    manager_user: User,
    manager_headers: dict,
    auth_headers: dict,
) -> None:
    """After creation, workflow appears in list for all authenticated users."""
    # Create as manager
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    assert create_resp.status_code == 201

    # List as employee
    list_resp = await async_client.get("/api/v1/workflows", headers=auth_headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["meta"]["total_items"] == 1
    assert body["data"][0]["name"] == "Delay Workflow"


# ===========================================================================
# GET /api/v1/workflows/{id} — get single
# ===========================================================================


@pytest.mark.asyncio
async def test_get_workflow_not_found(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Non-existent workflow must return 404."""
    response = await async_client.get(
        f"/api/v1/workflows/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_workflow_by_id(
    async_client: AsyncClient,
    manager_headers: dict,
    auth_headers: dict,
) -> None:
    """Created workflow is accessible by its UUID."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    get_resp = await async_client.get(
        f"/api/v1/workflows/{workflow_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    assert data["id"] == workflow_id
    assert len(data["steps"]) == 1


# ===========================================================================
# PUT /api/v1/workflows/{id} — update
# ===========================================================================


@pytest.mark.asyncio
async def test_update_workflow_metadata(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Manager may update workflow name."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    update_resp = await async_client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"name": "Updated Name"},
        headers=manager_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_workflow_steps(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Updating with a new steps list replaces existing steps."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    update_resp = await async_client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={
            "steps": [
                {
                    "step_number": 1,
                    "action": "delay",
                    "configuration": {"seconds": 5},
                },
                {
                    "step_number": 2,
                    "action": "delay",
                    "configuration": {"seconds": 10},
                },
            ]
        },
        headers=manager_headers,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()["data"]
    assert len(data["steps"]) == 2


@pytest.mark.asyncio
async def test_update_workflow_not_found(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Updating a non-existent workflow returns 404."""
    response = await async_client.put(
        f"/api/v1/workflows/{uuid.uuid4()}",
        json={"name": "Ghost"},
        headers=manager_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_workflow_employee_forbidden(
    async_client: AsyncClient,
    manager_headers: dict,
    auth_headers: dict,
) -> None:
    """Employee may not update a workflow."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    response = await async_client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"name": "Hacked"},
        headers=auth_headers,
    )
    assert response.status_code == 403


# ===========================================================================
# DELETE /api/v1/workflows/{id} — soft-delete
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_workflow_admin_only(
    async_client: AsyncClient,
    manager_headers: dict,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Only admin may delete; manager and employee receive 403."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    # Employee: 403
    resp_employee = await async_client.delete(
        f"/api/v1/workflows/{workflow_id}",
        headers=auth_headers,
    )
    assert resp_employee.status_code == 403

    # Manager: 403
    resp_manager = await async_client.delete(
        f"/api/v1/workflows/{workflow_id}",
        headers=manager_headers,
    )
    assert resp_manager.status_code == 403

    # Admin: 200
    resp_admin = await async_client.delete(
        f"/api/v1/workflows/{workflow_id}",
        headers=admin_headers,
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["success"] is True

    # Deleted workflow is no longer visible
    get_resp = await async_client.get(
        f"/api/v1/workflows/{workflow_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404


# ===========================================================================
# POST /api/v1/workflows/{id}/run — trigger execution
# ===========================================================================


@pytest.mark.asyncio
async def test_trigger_workflow_employee_forbidden(
    async_client: AsyncClient,
    manager_headers: dict,
    auth_headers: dict,
) -> None:
    """Employee may not trigger a workflow."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    resp = await async_client.post(
        f"/api/v1/workflows/{workflow_id}/run",
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trigger_workflow_creates_execution(
    async_client: AsyncClient,
    manager_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Triggering a workflow returns an execution_id and creates an execution record."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    # Patch Celery dispatch so we don't need a broker
    with patch("app.services.workflow_service.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        run_resp = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/run",
            headers=manager_headers,
        )

    assert run_resp.status_code == 202
    body = run_resp.json()
    assert body["success"] is True
    execution_id = body["data"]["execution_id"]
    assert execution_id is not None

    # Verify execution record was created
    get_resp = await async_client.get(
        f"/api/v1/executions/{execution_id}",
        headers=manager_headers,
    )
    assert get_resp.status_code == 200
    exec_data = get_resp.json()["data"]
    assert exec_data["id"] == execution_id
    assert exec_data["status"] in ("pending", "running", "completed")


@pytest.mark.asyncio
async def test_trigger_inactive_workflow_rejected(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Inactive workflows cannot be triggered — returns 409."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    # Deactivate it
    await async_client.put(
        f"/api/v1/workflows/{workflow_id}",
        json={"is_active": False},
        headers=manager_headers,
    )

    run_resp = await async_client.post(
        f"/api/v1/workflows/{workflow_id}/run",
        headers=manager_headers,
    )
    assert run_resp.status_code == 409


# ===========================================================================
# GET /api/v1/workflows/{id}/executions — execution history
# ===========================================================================


@pytest.mark.asyncio
async def test_list_executions_empty(
    async_client: AsyncClient,
    manager_headers: dict,
    auth_headers: dict,
) -> None:
    """Newly created workflow has empty execution history."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    list_resp = await async_client.get(
        f"/api/v1/workflows/{workflow_id}/executions",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["meta"]["total_items"] == 0


# ===========================================================================
# POST /api/v1/executions/{id}/approve — approval gate
# ===========================================================================


@pytest.mark.asyncio
async def test_approve_execution_not_waiting(
    async_client: AsyncClient,
    manager_headers: dict,
) -> None:
    """Approving an execution that is not WAITING_APPROVAL must return 409."""
    # Create workflow and trigger it (creates PENDING execution)
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    with patch("app.services.workflow_service.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        run_resp = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/run",
            headers=manager_headers,
        )
    execution_id = run_resp.json()["data"]["execution_id"]

    # Try to approve a PENDING execution (wrong state)
    approve_resp = await async_client.post(
        f"/api/v1/executions/{execution_id}/approve",
        json={"action": "approve"},
        headers=manager_headers,
    )
    assert approve_resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_execution_employee_forbidden(
    async_client: AsyncClient,
    manager_headers: dict,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Employee may not approve an execution."""
    # Create workflow and execution
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    with patch("app.services.workflow_service.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        run_resp = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/run",
            headers=manager_headers,
        )
    execution_id = run_resp.json()["data"]["execution_id"]

    # Set execution to WAITING_APPROVAL manually
    from sqlalchemy import update as sa_update

    from app.models.workflow_execution import WorkflowExecution as WE

    await db_session.execute(
        sa_update(WE)
        .where(WE.id == uuid.UUID(execution_id))
        .values(status=ExecutionStatus.WAITING_APPROVAL)
    )
    await db_session.commit()

    approve_resp = await async_client.post(
        f"/api/v1/executions/{execution_id}/approve",
        json={"action": "approve"},
        headers=auth_headers,
    )
    assert approve_resp.status_code == 403


@pytest.mark.asyncio
async def test_approve_execution_waiting_approval(
    async_client: AsyncClient,
    manager_user: User,
    manager_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Manager may approve an execution in WAITING_APPROVAL state."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    with patch("app.services.workflow_service.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        run_resp = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/run",
            headers=manager_headers,
        )
    execution_id = run_resp.json()["data"]["execution_id"]

    # Set to WAITING_APPROVAL
    from sqlalchemy import update as sa_update

    from app.models.workflow_execution import WorkflowExecution as WE

    await db_session.execute(
        sa_update(WE)
        .where(WE.id == uuid.UUID(execution_id))
        .values(status=ExecutionStatus.WAITING_APPROVAL)
    )
    await db_session.commit()

    with patch("app.services.workflow_service.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        approve_resp = await async_client.post(
            f"/api/v1/executions/{execution_id}/approve",
            json={"action": "approve", "comment": "Looks good"},
            headers=manager_headers,
        )

    assert approve_resp.status_code == 200
    body = approve_resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "running"


@pytest.mark.asyncio
async def test_reject_execution_waiting_approval(
    async_client: AsyncClient,
    manager_headers: dict,
    db_session: AsyncSession,
) -> None:
    """Manager may reject an execution in WAITING_APPROVAL state."""
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )
    workflow_id = create_resp.json()["data"]["id"]

    with patch("app.services.workflow_service.celery_app") as mock_celery:
        mock_celery.send_task.return_value = None
        run_resp = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/run",
            headers=manager_headers,
        )
    execution_id = run_resp.json()["data"]["execution_id"]

    from sqlalchemy import update as sa_update

    from app.models.workflow_execution import WorkflowExecution as WE

    await db_session.execute(
        sa_update(WE)
        .where(WE.id == uuid.UUID(execution_id))
        .values(status=ExecutionStatus.WAITING_APPROVAL)
    )
    await db_session.commit()

    reject_resp = await async_client.post(
        f"/api/v1/executions/{execution_id}/approve",
        json={"action": "reject", "comment": "Not approved"},
        headers=manager_headers,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["data"]["status"] == "rejected"


# ===========================================================================
# Dashboard — workflow stats
# ===========================================================================


@pytest.mark.asyncio
async def test_dashboard_includes_workflow_stats(
    async_client: AsyncClient,
    manager_headers: dict,
    auth_headers: dict,
) -> None:
    """Dashboard stats must include total_workflows and pending_executions fields."""
    # Create a workflow to ensure count > 0
    await async_client.post(
        "/api/v1/workflows",
        json=_delay_workflow_payload(),
        headers=manager_headers,
    )

    resp = await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_workflows" in data
    assert "pending_executions" in data
    assert data["total_workflows"] >= 1
    assert data["pending_executions"] >= 0
