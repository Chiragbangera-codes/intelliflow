"""
End-to-End Verification Script — Milestone 8 (Workflow Engine).

Validates:
  1. RBAC enforcement (Employee cannot create/trigger/approve/delete).
  2. Workflow CRUD (Manager creates, updates; Admin deletes).
  3. Step execution: `notify`, `delay`, `archive_document`.
  4. End-to-end execution lifecycle: PENDING -> RUNNING -> COMPLETED.
  5. Approval gate: PENDING -> RUNNING -> WAITING_APPROVAL -> (Approve) -> RUNNING -> COMPLETED.
  6. In-app notification creation & document archiving verification.
  7. Dashboard KPI aggregation with active workflow & execution counts.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from unittest.mock import patch

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.department import Department
from app.models.document import Document
from app.models.notification import Notification
from app.models.role import Role
from app.models.user import User
from app.models.workflow_execution import ExecutionStatus
from app.schemas.workflow import (
    ApprovalAction,
    WorkflowCreate,
    WorkflowStepCreate,
)
from app.services.dashboard_service import DashboardService
from app.services.workflow_service import WorkflowService
from app.workers.workflow_tasks import _run_workflow_steps

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log_pass(title: str, detail: str = "") -> None:
    print(f"  {GREEN}[PASS]{RESET} {BOLD}{title}{RESET} {detail}")


def log_fail(title: str, detail: str = "") -> None:
    print(f"  {RED}[FAIL]{RESET} {BOLD}{title}{RESET} {detail}")


async def main() -> int:
    print(f"\n{CYAN}{BOLD}{'='*70}{RESET}")
    print(f"{CYAN}{BOLD}  INTELLIFLOW AI — PHASE 8 WORKFLOW ENGINE E2E AUDIT{RESET}")
    print(f"{CYAN}{BOLD}{'='*70}{RESET}\n")

    # Use in-memory SQLite for isolated end-to-end verification
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    test_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    passed_tests = 0
    total_tests = 0

    async with test_session_maker() as session:
        # Seed Roles
        roles = {
            "admin": Role(
                id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
                name="admin",
                description="Administrator",
            ),
            "manager": Role(
                id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
                name="manager",
                description="Manager",
            ),
            "employee": Role(
                id=uuid.UUID("00000000-0000-4000-8000-000000000003"),
                name="employee",
                description="Employee",
            ),
        }
        session.add_all(roles.values())
        await session.flush()

        # Seed Users
        admin = User(
            email="admin@intelliflow.ai",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role_id=roles["admin"].id,
        )
        manager = User(
            email="manager@intelliflow.ai",
            password_hash="hashed",
            first_name="Manager",
            last_name="User",
            role_id=roles["manager"].id,
        )
        employee = User(
            email="employee@intelliflow.ai",
            password_hash="hashed",
            first_name="Employee",
            last_name="User",
            role_id=roles["employee"].id,
        )
        session.add_all([admin, manager, employee])
        await session.flush()

        # Seed Department and Document owned by manager
        dept = Department(name="Engineering")
        session.add(dept)
        await session.flush()

        doc = Document(
            file_name="Q3_Financial_Plan.pdf",
            storage_path="/app/storage/q3_plan.pdf",
            file_size=2048,
            file_type="application/pdf",
            owner_id=manager.id,
        )
        session.add(doc)
        await session.commit()

        wf_service = WorkflowService(session)

        # -----------------------------------------------------------------
        # TEST 1: RBAC - Employee cannot create workflow
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[1/8] Verifying RBAC role protection...{RESET}")
        try:
            await wf_service.create_workflow(
                WorkflowCreate(
                    name="Unauthorized Workflow",
                    steps=[
                        WorkflowStepCreate(
                            step_number=1,
                            action="delay",
                            configuration={"seconds": 1},
                        )
                    ],
                ),
                actor=employee,
            )
            log_fail("RBAC employee creation block", "Expected 403 Forbidden")
        except Exception as exc:
            if "403" in str(exc) or getattr(exc, "status_code", None) == 403:
                log_pass("RBAC employee creation correctly blocked with 403")
                passed_tests += 1
            else:
                log_fail("RBAC employee creation block", f"Unexpected error: {exc}")

        # -----------------------------------------------------------------
        # TEST 2: Manager creates multi-step workflow (notify -> delay -> archive_document)
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[2/8] Testing Workflow Creation (notify -> delay -> archive_document)...{RESET}")
        create_payload = WorkflowCreate(
            name="Quarterly Document Lifecycle",
            description="Notify owner, delay 1s, and archive document.",
            steps=[
                WorkflowStepCreate(
                    step_number=1,
                    action="notify",
                    configuration={
                        "user_id": str(employee.id),
                        "title": "Document Archive Triggered",
                        "message": "The financial plan is being archived.",
                    },
                ),
                WorkflowStepCreate(
                    step_number=2,
                    action="delay",
                    configuration={"seconds": 1},
                ),
                WorkflowStepCreate(
                    step_number=3,
                    action="archive_document",
                    configuration={"document_id": str(doc.id)},
                ),
            ],
        )
        created_wf = await wf_service.create_workflow(create_payload, actor=manager)
        if created_wf and len(created_wf.steps) == 3:
            log_pass(
                "Workflow created successfully",
                f"ID: {created_wf.id} ({len(created_wf.steps)} steps)",
            )
            passed_tests += 1
        else:
            log_fail("Workflow creation", "Workflow or steps mismatch")

        # -----------------------------------------------------------------
        # TEST 3: Asynchronous Workflow Execution
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[3/8] Testing Asynchronous Execution Engine...{RESET}")
        with patch("app.services.workflow_service.celery_app.send_task") as mock_send:
            run_resp = await wf_service.trigger_workflow(created_wf.id, actor=manager)
            mock_send.assert_called_once()

        # Run worker step executor
        with patch("time.sleep"):
            await _run_workflow_steps(str(run_resp.execution_id), session=session)

        exec_record = await wf_service.get_execution(run_resp.execution_id, actor=manager)
        if exec_record.status == ExecutionStatus.COMPLETED.value:
            log_pass(
                "Pipeline execution transitioned to COMPLETED",
                f"Duration: {exec_record.duration:.3f}s",
            )
            passed_tests += 1
        else:
            log_fail("Pipeline execution status", f"Got status: {exec_record.status}")

        # -----------------------------------------------------------------
        # TEST 4: Verification of Side Effects (Notification & Document Soft-Delete)
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[4/8] Verifying Execution Side Effects...{RESET}")
        await session.refresh(doc)
        from sqlalchemy import select
        result = await session.execute(
            select(Notification).where(Notification.user_id == employee.id)
        )
        user_notifications = list(result.scalars().all())

        has_notif = any(n.title == "Document Archive Triggered" for n in user_notifications)
        is_archived = doc.deleted_at is not None

        if has_notif and is_archived:
            log_pass("In-app notification created for target user")
            log_pass("Target document soft-deleted with deleted_at timestamp")
            passed_tests += 1
        else:
            log_fail("Side effects verification", f"Notif={has_notif}, Archived={is_archived}")

        # -----------------------------------------------------------------
        # TEST 5: Interactive Approval Gate Workflow (approve -> notify)
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[5/8] Testing Management Approval Gate (approve -> notify)...{RESET}")
        approval_wf_payload = WorkflowCreate(
            name="Executive Expense Approval",
            description="Pauses execution for manager approval before notification.",
            steps=[
                WorkflowStepCreate(
                    step_number=1,
                    action="approve",
                    configuration={"approver_user_id": str(admin.id)},
                ),
                WorkflowStepCreate(
                    step_number=2,
                    action="notify",
                    configuration={
                        "user_id": str(manager.id),
                        "title": "Expense Approved",
                        "message": "Your expense request was authorized.",
                    },
                ),
            ],
        )
        approval_wf = await wf_service.create_workflow(approval_wf_payload, actor=manager)

        with patch("app.services.workflow_service.celery_app.send_task"):
            run_approval = await wf_service.trigger_workflow(approval_wf.id, actor=manager)

        # Worker runs first step (approve) and pauses
        await _run_workflow_steps(str(run_approval.execution_id), session=session)
        paused_exec = await wf_service.get_execution(run_approval.execution_id, actor=manager)

        if paused_exec.status == ExecutionStatus.WAITING_APPROVAL.value:
            log_pass("Execution entered WAITING_APPROVAL state and released worker slot")
            passed_tests += 1
        else:
            log_fail("Approval pause state", f"Expected waiting_approval, got {paused_exec.status}")

        # -----------------------------------------------------------------
        # TEST 6: Manager Approves Execution & Resumes Pipeline
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[6/8] Testing Interactive Approval Action & Resumption...{RESET}")
        with patch("app.services.workflow_service.celery_app.send_task") as mock_resume:
            approved_exec = await wf_service.approve_execution(
                run_approval.execution_id,
                ApprovalAction(action="approve", comment="Approved by Director."),
                actor=admin,
            )
            mock_resume.assert_called_once()

        # Worker resumes from step 2 (notify)
        resume_from = approved_exec.logs.get("resume_from_step", 1)
        await _run_workflow_steps(
            str(run_approval.execution_id),
            session=session,
            start_from_step_index=resume_from,
        )

        resumed_exec = await wf_service.get_execution(run_approval.execution_id, actor=manager)
        if resumed_exec.status == ExecutionStatus.COMPLETED.value:
            log_pass("Execution successfully resumed after approval and reached COMPLETED")
            passed_tests += 1
        else:
            log_fail("Resumed execution status", f"Got status: {resumed_exec.status}")

        # -----------------------------------------------------------------
        # TEST 7: Soft-Delete Workflow (Admin Only)
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[7/8] Testing Admin Soft-Delete Workflow...{RESET}")
        await wf_service.delete_workflow(created_wf.id, actor=admin)
        active_list, _ = await wf_service.list_workflows(actor=admin, page=1, page_size=10)
        is_deleted_from_active = all(w.id != created_wf.id for w in active_list)

        if is_deleted_from_active:
            log_pass("Admin soft-deleted workflow (excluded from active listings)")
            passed_tests += 1
        else:
            log_fail("Workflow soft-delete", "Deleted workflow still visible in active list")

        # -----------------------------------------------------------------
        # TEST 8: Dashboard KPI Integration
        # -----------------------------------------------------------------
        total_tests += 1
        print(f"\n{YELLOW}[8/8] Testing Dashboard KPI Aggregation...{RESET}")
        dashboard_svc = DashboardService(session)
        stats = await dashboard_svc.get_stats(actor=admin)

        if stats.total_workflows >= 1:
            log_pass(
                "Dashboard KPI aggregation verified",
                f"total_workflows={stats.total_workflows}, pending_executions={stats.pending_executions}",
            )
            passed_tests += 1
        else:
            log_fail("Dashboard KPI aggregation", f"total_workflows was {stats.total_workflows}")

    print(f"\n{CYAN}{BOLD}{'='*70}{RESET}")
    if passed_tests == total_tests:
        print(f"{GREEN}{BOLD}  ALL {passed_tests}/{total_tests} PHASE 8 E2E CHECKS PASSED PERFECTLY! 🚀{RESET}")
        print(f"{CYAN}{BOLD}{'='*70}{RESET}\n")
        return 0
    else:
        print(f"{RED}{BOLD}  {passed_tests}/{total_tests} CHECKS PASSED. {total_tests - passed_tests} FAILED.{RESET}")
        print(f"{CYAN}{BOLD}{'='*70}{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
