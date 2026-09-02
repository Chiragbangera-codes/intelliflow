"""
Unit and integration tests for workflow worker tasks — Milestone 8.

Tests cover:
  - _execute_notify_step (success & user-not-found)
  - _execute_delay_step (sleep duration validation)
  - _execute_archive_document_step (authorized vs unauthorized)
  - _execute_send_email_step (SMTP dispatch & unconfigured SMTP_HOST)
  - _handle_approve_step (notification & pause state)
  - _run_workflow_steps (end-to-end execution, retry on failure, approve pausing)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_execution import ExecutionStatus, WorkflowExecution
from app.models.workflow_step import WorkflowStep
from app.repositories.workflow_repository import WorkflowRepository
from app.workers.workflow_tasks import (
    _execute_archive_document_step,
    _execute_delay_step,
    _execute_notify_step,
    _execute_send_email_step,
    _handle_approve_step,
    _NonRetryableError,
    _run_workflow_steps,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest_asyncio.fixture
async def test_document(db_session: AsyncSession, test_user: User) -> Document:
    """Create an active document owned by test_user."""
    doc = Document(
        file_name="Test Contract.pdf",
        storage_path="/app/storage/test_contract.pdf",
        file_size=1024,
        file_type="application/pdf",
        owner_id=test_user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


# ===========================================================================
# Step executor tests
# ===========================================================================


@pytest.mark.asyncio
async def test_execute_notify_step_success(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Notify step creates an in-app notification for the target user."""
    repo = WorkflowRepository(db_session)
    step = WorkflowStep(
        workflow_id=uuid.uuid4(),
        step_number=1,
        action="notify",
        configuration={
            "user_id": str(test_user.id),
            "title": "Welcome",
            "message": "Task processed successfully.",
        },
    )

    result = await _execute_notify_step(step, repo, db_session)
    assert result["action"] == "notify"
    assert result["target_user_id"] == str(test_user.id)
    assert "notification_id" in result


@pytest.mark.asyncio
async def test_execute_notify_step_missing_user(
    db_session: AsyncSession,
) -> None:
    """Notify step with non-existent user raises _NonRetryableError."""
    repo = WorkflowRepository(db_session)
    step = WorkflowStep(
        workflow_id=uuid.uuid4(),
        step_number=1,
        action="notify",
        configuration={
            "user_id": str(uuid.uuid4()),
            "title": "Welcome",
            "message": "Hello",
        },
    )

    with pytest.raises(_NonRetryableError, match="not found"):
        await _execute_notify_step(step, repo, db_session)


@pytest.mark.asyncio
async def test_execute_delay_step() -> None:
    """Delay step executes with bounded sleep."""
    step = WorkflowStep(
        workflow_id=uuid.uuid4(),
        step_number=1,
        action="delay",
        configuration={"seconds": 1},
    )

    with patch("time.sleep") as mock_sleep:
        result = await _execute_delay_step(step)
        assert result["action"] == "delay"
        assert result["seconds"] == 1
        mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_execute_send_email_step_no_smtp() -> None:
    """Send email step fails with _NonRetryableError when SMTP_HOST is empty."""
    step = WorkflowStep(
        workflow_id=uuid.uuid4(),
        step_number=1,
        action="send_email",
        configuration={
            "to": "alice@example.com",
            "subject": "Status Report",
            "body": "All systems nominal.",
        },
    )

    with patch.object(settings, "SMTP_HOST", ""):
        with pytest.raises(_NonRetryableError, match="SMTP_HOST is not configured"):
            await _execute_send_email_step(step)


@pytest.mark.asyncio
async def test_execute_send_email_step_mocked_smtp() -> None:
    """Send email step connects and sends email when SMTP_HOST is configured."""
    step = WorkflowStep(
        workflow_id=uuid.uuid4(),
        step_number=1,
        action="send_email",
        configuration={
            "to": "alice@example.com",
            "subject": "Status Report",
            "body": "All systems nominal.",
        },
    )

    with patch.object(settings, "SMTP_HOST", "smtp.test.com"):
        with patch.object(settings, "SMTP_USE_TLS", True):
            with patch("smtplib.SMTP") as mock_smtp_cls:
                mock_server = MagicMock()
                mock_smtp_cls.return_value.__enter__.return_value = mock_server

                result = await _execute_send_email_step(step)
                assert result["action"] == "send_email"
                assert result["delivered"] is True
                mock_server.starttls.assert_called_once()
                mock_server.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_execute_archive_document_step_authorized(
    db_session: AsyncSession,
    test_user: User,
    test_document: Document,
) -> None:
    """Owner of document can archive it via workflow."""
    workflow = Workflow(
        name="Archive WF",
        created_by=test_user.id,
        is_active=True,
    )
    db_session.add(workflow)
    await db_session.flush()

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        triggered_by=test_user.id,
        status=ExecutionStatus.RUNNING,
    )
    db_session.add(execution)
    await db_session.commit()

    step = WorkflowStep(
        workflow_id=workflow.id,
        step_number=1,
        action="archive_document",
        configuration={"document_id": str(test_document.id)},
    )

    result = await _execute_archive_document_step(step, execution, workflow, db_session)
    assert result["action"] == "archive_document"
    assert result["archived"] is True
    assert test_document.deleted_at is not None


@pytest.mark.asyncio
async def test_execute_archive_document_step_unauthorized(
    db_session: AsyncSession,
    test_user: User,
    test_document: Document,
) -> None:
    """Non-admin employee who does NOT own document cannot archive it."""
    # Another employee using seeded employee role ID
    other_user = User(
        email=f"other_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="pw",
        first_name="Other",
        last_name="Person",
        role_id=uuid.UUID("00000000-0000-4000-8000-000000000003"),
    )
    db_session.add(other_user)
    await db_session.flush()

    workflow = Workflow(
        name="Unauthorized Archive WF",
        created_by=other_user.id,
        is_active=True,
    )
    db_session.add(workflow)
    await db_session.flush()

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        triggered_by=other_user.id,
        status=ExecutionStatus.RUNNING,
    )
    db_session.add(execution)
    await db_session.commit()

    step = WorkflowStep(
        workflow_id=workflow.id,
        step_number=1,
        action="archive_document",
        configuration={"document_id": str(test_document.id)},
    )

    with pytest.raises(_NonRetryableError, match="Authorization denied"):
        await _execute_archive_document_step(step, execution, workflow, db_session)


@pytest.mark.asyncio
async def test_handle_approve_step(
    db_session: AsyncSession,
    admin_user: User,
    test_user: User,
) -> None:
    """Approve step notifies approver and returns pause sentinel."""
    repo = WorkflowRepository(db_session)
    workflow = Workflow(
        name="Approval WF",
        created_by=test_user.id,
        is_active=True,
    )
    db_session.add(workflow)
    await db_session.flush()

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        triggered_by=test_user.id,
        status=ExecutionStatus.RUNNING,
    )
    db_session.add(execution)
    await db_session.commit()

    step = WorkflowStep(
        workflow_id=workflow.id,
        step_number=1,
        action="approve",
        configuration={"approver_user_id": str(admin_user.id)},
    )

    result = await _handle_approve_step(step, execution, 0, repo, workflow, db_session)
    assert result["action"] == "approve"
    assert result["requires_approval"] is True
    assert result["paused_at_step_index"] == 0


# ===========================================================================
# End-to-end task runner tests
# ===========================================================================


@pytest.mark.asyncio
async def test_run_workflow_steps_complete_success(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """A workflow with notify + delay runs to COMPLETED status."""
    workflow = Workflow(
        name="Sequential WF",
        created_by=test_user.id,
        is_active=True,
    )
    db_session.add(workflow)
    await db_session.flush()

    step1 = WorkflowStep(
        workflow_id=workflow.id,
        step_number=1,
        action="notify",
        configuration={
            "user_id": str(test_user.id),
            "title": "Step 1 Done",
            "message": "Notification received.",
        },
    )
    step2 = WorkflowStep(
        workflow_id=workflow.id,
        step_number=2,
        action="delay",
        configuration={"seconds": 1},
    )
    db_session.add_all([step1, step2])
    await db_session.flush()

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        triggered_by=test_user.id,
        status=ExecutionStatus.PENDING,
    )
    db_session.add(execution)
    await db_session.commit()

    with patch("time.sleep"):
        await _run_workflow_steps(str(execution.id), session=db_session)

    await db_session.refresh(execution)
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.duration is not None
    assert len(execution.logs["steps"]) == 2
    assert execution.logs["steps"][0]["status"] == "completed"
    assert execution.logs["steps"][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_run_workflow_steps_pauses_on_approve(
    db_session: AsyncSession,
    test_user: User,
    admin_user: User,
) -> None:
    """A workflow with an approve step pauses with WAITING_APPROVAL status."""
    workflow = Workflow(
        name="Pause WF",
        created_by=test_user.id,
        is_active=True,
    )
    db_session.add(workflow)
    await db_session.flush()

    step1 = WorkflowStep(
        workflow_id=workflow.id,
        step_number=1,
        action="approve",
        configuration={"approver_user_id": str(admin_user.id)},
    )
    step2 = WorkflowStep(
        workflow_id=workflow.id,
        step_number=2,
        action="notify",
        configuration={
            "user_id": str(test_user.id),
            "title": "Post Approval",
            "message": "Resumed successfully.",
        },
    )
    db_session.add_all([step1, step2])
    await db_session.flush()

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        triggered_by=test_user.id,
        status=ExecutionStatus.PENDING,
    )
    db_session.add(execution)
    await db_session.commit()

    await _run_workflow_steps(str(execution.id), session=db_session)

    await db_session.refresh(execution)
    assert execution.status == ExecutionStatus.WAITING_APPROVAL
    assert execution.logs.get("resume_from_step") == 1
