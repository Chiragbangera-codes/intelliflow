"""
Celery background tasks for asynchronous workflow execution (Milestone 8).

Tasks:
  tasks.execute_workflow(execution_id: str)
    Entry point for a new execution. Runs all steps sequentially from
    the beginning. Transitions execution through:
      PENDING → RUNNING → (WAITING_APPROVAL | COMPLETED | FAILED)

  tasks.resume_workflow(execution_id: str)
    Resumes an execution after an approve step has been approved.
    Continues from the step immediately after the approve step.

Architecture:
  API dispatches execute_workflow → task loops through steps →
  on `approve` step: task exits, sets WAITING_APPROVAL, creates notification →
  approver calls /api/v1/executions/{id}/approve →
  service dispatches resume_workflow → task continues from next step.

  This design releases the Celery worker slot during approval waits.
  There is NO infinite sleep. No DB transaction is held open during I/O.

Approval state persistence:
  The step index to resume from is stored in execution.logs["resume_from_step"].
  resume_workflow reads this to skip already-completed steps.

Retry semantics:
  retry_count = N means: initial attempt + up to N retries = N+1 total attempts.
  Only transient failures (non-authorization, non-validation) are retried.
  Authorization/validation failures never retry and immediately mark FAILED.

Security:
  - SMTP credentials are read from settings, never from workflow configuration.
  - archive_document performs ownership checks before soft-deleting.
  - Stack traces go to worker logs only; only safe messages reach execution logs.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.notification import NotificationPriority
from app.models.workflow import Workflow
from app.models.workflow_execution import ExecutionStatus, WorkflowExecution
from app.models.workflow_step import WorkflowStep
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.workers.celery_app import celery_app
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Non-retryable error sentinel
# ---------------------------------------------------------------------------


class _NonRetryableError(Exception):
    """Raised for auth/validation failures that must not be retried."""


# ===========================================================================
# Step executors
# ===========================================================================


async def _execute_notify_step(
    step: WorkflowStep,
    workflow_repo: WorkflowRepository,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Execute a `notify` step.

    Creates an in-app notification for the target user.
    Validates the target user exists before writing.

    Returns:
        Step result dict for the execution log.
    """
    cfg: dict[str, Any] = step.configuration or {}
    user_id = uuid.UUID(str(cfg["user_id"]))
    title = str(cfg["title"])
    message = str(cfg["message"])

    # Validate target user exists
    target_user = await workflow_repo.get_user_by_id(user_id)
    if target_user is None:
        raise _NonRetryableError(
            f"notify step: target user {user_id} not found or has been deleted."
        )

    notification = await workflow_repo.create_notification(
        user_id=user_id,
        title=title,
        message=message,
        priority=NotificationPriority.MEDIUM,
    )
    await session.commit()

    logger.info(
        "Notify step created notification %s for user %s.",
        notification.id,
        user_id,
    )
    return {
        "action": "notify",
        "notification_id": str(notification.id),
        "target_user_id": str(user_id),
    }


async def _execute_send_email_step(
    step: WorkflowStep,
) -> dict[str, Any]:
    """
    Execute a `send_email` step using SMTP settings from configuration.

    SMTP credentials are never logged or exposed in return values.
    If SMTP_HOST is not configured, the step fails with a controlled error.

    Returns:
        Step result dict for the execution log.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    cfg: dict[str, Any] = step.configuration or {}
    to_addr = str(cfg["to"])
    subject = str(cfg["subject"])
    body = str(cfg["body"])

    if not settings.SMTP_HOST:
        raise _NonRetryableError(
            "send_email step: SMTP_HOST is not configured. "
            "Set SMTP_HOST in environment to enable email sending."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain"))

    try:
        if settings.SMTP_USE_TLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                smtp.starttls()
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.sendmail(settings.SMTP_FROM, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.sendmail(settings.SMTP_FROM, [to_addr], msg.as_string())
    except smtplib.SMTPException as exc:
        # Log only safe details — never the credentials
        logger.error(
            "send_email step SMTP error for step %s: %s",
            step.id,
            type(exc).__name__,
        )
        raise RuntimeError(f"Email delivery failed: {type(exc).__name__}") from exc

    logger.info("send_email step: sent email to %s (subject redacted).", to_addr)
    return {
        "action": "send_email",
        "to": to_addr,
        "delivered": True,
    }


async def _execute_archive_document_step(
    step: WorkflowStep,
    execution: WorkflowExecution,
    workflow: Workflow,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Execute an `archive_document` step.

    Authorization: the document must be accessible.
    The document is soft-deleted via DocumentRepository.
    The triggered_by user is used for the RBAC check — a workflow cannot
    be used to bypass document ownership restrictions.

    Returns:
        Step result dict for the execution log.
    """
    cfg: dict[str, Any] = step.configuration or {}
    document_id = uuid.UUID(str(cfg["document_id"]))

    doc_repo = DocumentRepository(session)
    document = await doc_repo.get_by_id(document_id)

    if document is None:
        raise _NonRetryableError(
            f"archive_document step: document {document_id} not found or already deleted."
        )

    # Authorization: only admin/hr may archive any document; others only their own.
    triggered_by_id = execution.triggered_by
    _ADMIN_ROLES_SET = {"admin", "hr"}

    if triggered_by_id is not None:
        from app.repositories.workflow_repository import WorkflowRepository as WR

        wf_repo = WR(session)
        triggering_user = await wf_repo.get_user_by_id(triggered_by_id)
        if triggering_user is not None:
            user_role = (
                triggering_user.role.name.lower()
                if triggering_user.role
                and hasattr(triggering_user.role, "name")
                and triggering_user.role.name
                else str(getattr(triggering_user, "role", "employee")).lower()
            )
            if user_role not in _ADMIN_ROLES_SET and document.owner_id != triggered_by_id:
                raise _NonRetryableError(
                    "archive_document step: the triggering user does not own "
                    "this document and lacks admin/hr privileges. "
                    "Authorization denied."
                )

    await doc_repo.soft_delete(document_id)
    await session.commit()

    audit_repo = AuditLogRepository(session)
    await audit_repo.create(
        action="document.archived_by_workflow",
        user_id=execution.triggered_by,
        table_name="documents",
        record_id=document_id,
        new_value={
            "workflow_id": str(workflow.id),
            "execution_id": str(execution.id),
        },
    )
    await session.commit()

    logger.info(
        "archive_document step: soft-deleted document %s via workflow execution %s.",
        document_id,
        execution.id,
    )
    return {
        "action": "archive_document",
        "document_id": str(document_id),
        "archived": True,
    }


async def _execute_delay_step(step: WorkflowStep) -> dict[str, Any]:
    """
    Execute a `delay` step.

    Uses time.sleep() since Celery countdown/ETA would require splitting the
    task chain, which introduces complexity for short delays. For delays within
    the 1–300 second range, a synchronous sleep is the safest non-blocking
    approach within the existing single-task architecture.

    Returns:
        Step result dict for the execution log.
    """
    cfg: dict[str, Any] = step.configuration or {}
    seconds = int(cfg.get("seconds", 1))

    # Re-validate bounds defensively (schema already checked, but belt-and-suspenders)
    max_delay = settings.WORKFLOW_MAX_DELAY_SECONDS
    seconds = max(1, min(seconds, max_delay))

    logger.info("delay step: sleeping for %d seconds.", seconds)
    time.sleep(seconds)
    logger.info("delay step: sleep completed.")

    return {
        "action": "delay",
        "seconds": seconds,
    }


async def _handle_approve_step(
    step: WorkflowStep,
    execution: WorkflowExecution,
    step_index: int,
    workflow_repo: WorkflowRepository,
    workflow: Workflow,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Handle an `approve` step.

    Sets execution to WAITING_APPROVAL and creates a notification for the
    approver (if approver_user_id is configured). Returns a sentinel dict
    indicating the task should exit — resume_workflow will handle continuation.

    Returns:
        Step result dict with 'requires_approval': True.
    """
    cfg: dict[str, Any] = step.configuration or {}
    approver_user_id_str: str | None = cfg.get("approver_user_id")

    # Notify the approver (if specified)
    if approver_user_id_str:
        try:
            approver_id = uuid.UUID(approver_user_id_str)
            approver = await workflow_repo.get_user_by_id(approver_id)
            if approver:
                await workflow_repo.create_notification(
                    user_id=approver_id,
                    title="Workflow Approval Required",
                    message=(
                        f"Workflow '{workflow.name}' is awaiting your approval. "
                        f"Execution ID: {execution.id}"
                    ),
                    priority=NotificationPriority.HIGH,
                )
                await session.commit()
        except Exception as exc:
            logger.warning(
                "approve step: failed to notify approver %s: %s",
                approver_user_id_str,
                exc,
            )

    # Notify the workflow creator / triggering user
    notify_user_id = execution.triggered_by or workflow.created_by
    if notify_user_id:
        try:
            await workflow_repo.create_notification(
                user_id=notify_user_id,
                title="Workflow Awaiting Approval",
                message=(
                    f"Workflow '{workflow.name}' has paused and requires approval "
                    f"to continue. Execution ID: {execution.id}"
                ),
                priority=NotificationPriority.HIGH,
            )
            await session.commit()
        except Exception as exc:
            logger.warning(
                "approve step: failed to notify trigger user %s: %s",
                notify_user_id,
                exc,
            )

    logger.info(
        "approve step reached for execution %s at step_index %d. " "Setting WAITING_APPROVAL.",
        execution.id,
        step_index,
    )

    return {
        "action": "approve",
        "requires_approval": True,
        "paused_at_step_index": step_index,
    }


# ===========================================================================
# Core execution logic
# ===========================================================================


async def _run_workflow_steps(
    execution_id_str: str,
    *,
    session: AsyncSession,
    start_from_step_index: int = 0,
) -> None:
    """
    Execute or resume workflow steps from `start_from_step_index`.

    This is the shared core used by both execute_workflow and resume_workflow.

    State machine:
      RUNNING → step loop → on approve: WAITING_APPROVAL (exit task)
                          → on all done: COMPLETED
                          → on failure: FAILED

    Args:
        execution_id_str:     String UUID of the execution.
        session:              Async database session.
        start_from_step_index: 0-based index to resume from (0 = start).
    """
    execution_id = uuid.UUID(execution_id_str)
    workflow_repo = WorkflowRepository(session)

    # Load execution
    execution = await workflow_repo.get_execution_by_id(execution_id)
    if execution is None:
        logger.error("Execution %s not found. Aborting.", execution_id)
        return

    # Load workflow with steps
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.workflow import Workflow as WorkflowModel

    stmt = (
        select(WorkflowModel)
        .where(WorkflowModel.id == execution.workflow_id)
        .options(selectinload(WorkflowModel.steps))
    )
    result = await session.execute(stmt)
    workflow = result.scalar_one_or_none()

    if workflow is None:
        logger.error(
            "Workflow %s for execution %s not found. Marking FAILED.",
            execution.workflow_id,
            execution_id,
        )
        await workflow_repo.update_execution_status(
            execution_id,
            status=ExecutionStatus.FAILED,
            logs={"error": "Workflow not found."},
        )
        await session.commit()
        return

    # Sort steps by step_number
    steps = sorted(workflow.steps, key=lambda s: s.step_number)

    # Transition to RUNNING
    existing_logs: dict[str, Any] = dict(execution.logs or {"steps": []})
    await workflow_repo.update_execution_status(
        execution_id,
        status=ExecutionStatus.RUNNING,
        logs=existing_logs,
    )
    await session.commit()

    wall_start = time.monotonic()

    for step_index, step in enumerate(steps):
        if step_index < start_from_step_index:
            # Skip already-completed steps
            continue

        step_log: dict[str, Any] = {
            "step_number": step.step_number,
            "action": step.action,
            "status": "running",
            "started_at": time.monotonic() - wall_start,
        }
        logger.info(
            "Execution %s: running step %d (%s) [index %d].",
            execution_id,
            step.step_number,
            step.action,
            step_index,
        )

        # Retry loop
        max_attempts = 1 + step.retry_count  # initial + retries
        last_error: str = ""

        for attempt in range(max_attempts):
            try:
                if step.action == "notify":
                    result_dict = await _execute_notify_step(step, workflow_repo, session)

                elif step.action == "send_email":
                    result_dict = await _execute_send_email_step(step)

                elif step.action == "archive_document":
                    result_dict = await _execute_archive_document_step(
                        step, execution, workflow, session
                    )

                elif step.action == "approve":
                    result_dict = await _handle_approve_step(
                        step, execution, step_index, workflow_repo, workflow, session
                    )
                    # Persist WAITING_APPROVAL and resume position
                    existing_logs_reload = await workflow_repo.get_execution_by_id(execution_id)
                    logs_to_save: dict[str, Any] = dict(
                        (existing_logs_reload.logs if existing_logs_reload else {}) or {}
                    )
                    steps_log = logs_to_save.get("steps", [])
                    step_log["status"] = "waiting_approval"
                    step_log["result"] = result_dict
                    steps_log.append(step_log)
                    logs_to_save["steps"] = steps_log
                    logs_to_save["resume_from_step"] = step_index + 1  # next step after approve
                    await workflow_repo.update_execution_status(
                        execution_id,
                        status=ExecutionStatus.WAITING_APPROVAL,
                        logs=logs_to_save,
                    )
                    await session.commit()
                    logger.info(
                        "Execution %s paused at step %d (approve). "
                        "Will resume from step_index %d.",
                        execution_id,
                        step.step_number,
                        step_index + 1,
                    )
                    return  # Exit the task; resume_workflow will continue

                elif step.action == "delay":
                    result_dict = await _execute_delay_step(step)

                else:
                    raise _NonRetryableError(f"Unknown action type: {step.action!r}")

                # Step succeeded — record and break retry loop
                step_log["status"] = "completed"
                step_log["result"] = result_dict
                step_log["elapsed_seconds"] = time.monotonic() - wall_start
                last_error = ""
                break

            except _NonRetryableError as exc:
                # Auth/validation failure — do not retry
                error_msg = str(exc)
                logger.error(
                    "Execution %s step %d (%s) non-retryable failure: %s",
                    execution_id,
                    step.step_number,
                    step.action,
                    error_msg,
                )
                step_log["status"] = "failed"
                step_log["error"] = error_msg
                step_log["elapsed_seconds"] = time.monotonic() - wall_start

                # Reload logs and persist FAILED
                execution_now = await workflow_repo.get_execution_by_id(execution_id)
                logs_now: dict[str, Any] = dict((execution_now.logs if execution_now else {}) or {})
                steps_list = logs_now.get("steps", [])
                steps_list.append(step_log)
                logs_now["steps"] = steps_list
                logs_now["error"] = f"Step {step.step_number} ({step.action}) failed: {error_msg}"

                duration = time.monotonic() - wall_start
                await workflow_repo.update_execution_status(
                    execution_id,
                    status=ExecutionStatus.FAILED,
                    logs=logs_now,
                    duration=duration,
                )
                await session.commit()

                # Audit log
                audit_repo = AuditLogRepository(session)
                await audit_repo.create(
                    action="workflow.failed",
                    user_id=execution.triggered_by,
                    table_name="workflow_executions",
                    record_id=execution_id,
                    new_value={
                        "step_number": step.step_number,
                        "action": step.action,
                        "error": error_msg,
                    },
                )
                await session.commit()
                return

            except Exception as exc:
                error_msg = str(exc)
                last_error = error_msg
                if attempt < max_attempts - 1:
                    wait = 2**attempt  # exponential backoff: 1s, 2s, 4s …
                    logger.warning(
                        "Execution %s step %d attempt %d/%d failed: %s. " "Retrying in %ds.",
                        execution_id,
                        step.step_number,
                        attempt + 1,
                        max_attempts,
                        error_msg,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Execution %s step %d (%s) failed after %d attempt(s): %s",
                        execution_id,
                        step.step_number,
                        step.action,
                        max_attempts,
                        error_msg,
                    )

        if last_error:
            # All retries exhausted
            step_log["status"] = "failed"
            step_log["error"] = last_error
            step_log["elapsed_seconds"] = time.monotonic() - wall_start

            execution_now = await workflow_repo.get_execution_by_id(execution_id)
            logs_now = dict((execution_now.logs if execution_now else {}) or {})
            steps_list = logs_now.get("steps", [])
            steps_list.append(step_log)
            logs_now["steps"] = steps_list
            logs_now["error"] = (
                f"Step {step.step_number} ({step.action}) failed after "
                f"{max_attempts} attempt(s): {last_error}"
            )
            duration = time.monotonic() - wall_start
            await workflow_repo.update_execution_status(
                execution_id,
                status=ExecutionStatus.FAILED,
                logs=logs_now,
                duration=duration,
            )
            await session.commit()

            audit_repo = AuditLogRepository(session)
            await audit_repo.create(
                action="workflow.failed",
                user_id=execution.triggered_by,
                table_name="workflow_executions",
                record_id=execution_id,
                new_value={
                    "step_number": step.step_number,
                    "action": step.action,
                    "error": last_error,
                },
            )
            await session.commit()
            return

        # Append step log to the execution logs
        execution_now = await workflow_repo.get_execution_by_id(execution_id)
        logs_now = dict((execution_now.logs if execution_now else {}) or {})
        steps_list = logs_now.get("steps", [])
        steps_list.append(step_log)
        logs_now["steps"] = steps_list
        await workflow_repo.update_execution_status(
            execution_id,
            status=ExecutionStatus.RUNNING,
            logs=logs_now,
        )
        await session.commit()

    # All steps completed successfully
    duration = time.monotonic() - wall_start
    execution_final = await workflow_repo.get_execution_by_id(execution_id)
    logs_final = dict((execution_final.logs if execution_final else {}) or {})

    await workflow_repo.update_execution_status(
        execution_id,
        status=ExecutionStatus.COMPLETED,
        logs=logs_final,
        duration=duration,
    )

    audit_repo = AuditLogRepository(session)
    await audit_repo.create(
        action="workflow.completed",
        user_id=execution.triggered_by,
        table_name="workflow_executions",
        record_id=execution_id,
        new_value={
            "duration_seconds": duration,
            "step_count": len(steps),
        },
    )
    await session.commit()

    logger.info(
        "Execution %s COMPLETED in %.2fs (%d steps).",
        execution_id,
        duration,
        len(steps),
    )


# ===========================================================================
# Celery tasks
# ===========================================================================


async def _async_execute_workflow(execution_id_str: str) -> dict[str, Any]:
    """Async wrapper for execute_workflow Celery task."""
    async with AsyncSessionLocal() as session:
        await _run_workflow_steps(
            execution_id_str,
            session=session,
            start_from_step_index=0,
        )
    return {"execution_id": execution_id_str, "dispatched": True}


async def _async_resume_workflow(execution_id_str: str) -> dict[str, Any]:
    """
    Async wrapper for resume_workflow Celery task.

    Reads `resume_from_step` from the execution logs to determine the step
    index to continue from.
    """
    async with AsyncSessionLocal() as session:
        workflow_repo = WorkflowRepository(session)
        execution_id = uuid.UUID(execution_id_str)
        execution = await workflow_repo.get_execution_by_id(execution_id)

        if execution is None:
            logger.error("resume_workflow: execution %s not found.", execution_id)
            return {"execution_id": execution_id_str, "error": "not_found"}

        if execution.status != ExecutionStatus.RUNNING:
            logger.warning(
                "resume_workflow: execution %s has unexpected status %s. Expected RUNNING.",
                execution_id,
                execution.status,
            )
            # Status was set to RUNNING by the approve service before dispatch
            # If it differs, something went wrong — log and exit.
            if execution.status not in (ExecutionStatus.RUNNING,):
                return {"execution_id": execution_id_str, "skipped": True}

        logs = dict(execution.logs or {})
        resume_from = int(logs.get("resume_from_step", 0))

        logger.info(
            "resume_workflow: resuming execution %s from step_index %d.",
            execution_id,
            resume_from,
        )

        await _run_workflow_steps(
            execution_id_str,
            session=session,
            start_from_step_index=resume_from,
        )

    return {"execution_id": execution_id_str, "resumed": True}


@celery_app.task(name="tasks.execute_workflow", bind=True)
def execute_workflow(self: Any, execution_id: str) -> dict[str, Any]:
    """
    Celery task: execute a workflow from the beginning.

    Args:
        execution_id: String UUID of the WorkflowExecution record.

    Returns:
        Summary dict.
    """
    logger.info(
        "Celery execute_workflow task %s: execution_id=%s",
        self.request.id,
        execution_id,
    )
    return run_in_worker(_async_execute_workflow(execution_id))


@celery_app.task(name="tasks.resume_workflow", bind=True)
def resume_workflow(self: Any, execution_id: str) -> dict[str, Any]:
    """
    Celery task: resume a workflow after approval.

    Args:
        execution_id: String UUID of the WorkflowExecution record.

    Returns:
        Summary dict.
    """
    logger.info(
        "Celery resume_workflow task %s: execution_id=%s",
        self.request.id,
        execution_id,
    )
    return run_in_worker(_async_resume_workflow(execution_id))
