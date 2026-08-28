"""
Database schema tests — Milestone 3.

Verifies that all new models, relationships, constraints, and soft-delete
behaviour work correctly. Tests run against the in-memory SQLite engine
(or PostgreSQL when TEST_DATABASE_URL is set / running in Docker).

Regression: Milestone 2 authentication models are NOT modified by these
tests. The existing test_auth.py continues to own those tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AIConversation
from app.models.ai_embedding import AIEmbedding
from app.models.department import Department
from app.models.document import Document, DocumentStatus, OcrStatus
from app.models.document_chunk import DocumentChunk
from app.models.employee_profile import EmployeeProfile
from app.models.notification import Notification, NotificationChannel, NotificationPriority
from app.models.prediction import Prediction
from app.models.report import Report, ReportStatus
from app.models.setting import Setting
from app.models.user import User, UserStatus
from app.models.workflow import Workflow
from app.models.workflow_execution import ExecutionStatus, WorkflowExecution
from app.models.workflow_step import WorkflowStep
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.employee_profile_repository import EmployeeProfileRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(role_id: uuid.UUID, **kwargs: object) -> User:
    """Create a User instance without committing."""
    return User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="argon2hash",
        first_name="Test",
        last_name="User",
        role_id=role_id,
        status=UserStatus.ACTIVE,
        **kwargs,
    )


_EMPLOYEE_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")


# ===========================================================================
# Department tests
# ===========================================================================


class TestDepartments:
    """Tests for the departments table and DepartmentRepository."""

    async def test_create_department(self, db_session: AsyncSession) -> None:
        """Should persist a department with name and description."""
        repo = DepartmentRepository(db_session)
        dept = await repo.create(name="Engineering", description="Software team")
        await db_session.commit()

        fetched = await repo.get_by_id(dept.id)
        assert fetched is not None
        assert fetched.name == "Engineering"
        assert fetched.description == "Software team"
        assert fetched.deleted_at is None

    async def test_department_name_uniqueness(self, db_session: AsyncSession) -> None:
        """Inserting two departments with the same name must raise IntegrityError."""
        repo = DepartmentRepository(db_session)
        await repo.create(name="Finance")
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(name="Finance")
            await db_session.commit()

    async def test_soft_delete_department(self, db_session: AsyncSession) -> None:
        """Soft-deleted departments should not appear in get_by_id."""
        repo = DepartmentRepository(db_session)
        dept = await repo.create(name="Temp Dept")
        await db_session.commit()

        await repo.soft_delete(dept.id)
        await db_session.commit()

        result = await repo.get_by_id(dept.id)
        assert result is None

    async def test_list_active_departments(self, db_session: AsyncSession) -> None:
        """list_active should exclude soft-deleted entries."""
        repo = DepartmentRepository(db_session)
        await repo.create(name="Alpha")
        d2 = await repo.create(name="Beta")
        await db_session.commit()

        await repo.soft_delete(d2.id)
        await db_session.commit()

        active = await repo.list_active()
        names = [d.name for d in active]
        assert "Alpha" in names
        assert "Beta" not in names

    async def test_get_by_name(self, db_session: AsyncSession) -> None:
        """get_by_name should return correct department."""
        repo = DepartmentRepository(db_session)
        await repo.create(name="Marketing")
        await db_session.commit()

        result = await repo.get_by_name("Marketing")
        assert result is not None
        assert result.name == "Marketing"

    async def test_department_repr(self, db_session: AsyncSession) -> None:
        """Department __repr__ should not raise."""
        dept = Department(name="ReprTest")
        assert "ReprTest" in repr(dept)


# ===========================================================================
# User → Department relationship tests
# ===========================================================================


class TestUserDepartmentRelationship:
    """Tests for the users.department_id FK."""

    async def test_user_with_department(self, db_session: AsyncSession) -> None:
        """A user can be assigned to a department via department_id."""
        dept = Department(name="HR Department")
        db_session.add(dept)
        await db_session.flush()

        user = _make_user(_EMPLOYEE_ROLE_ID, department_id=dept.id)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.department_id == dept.id

    async def test_user_without_department(self, db_session: AsyncSession) -> None:
        """department_id is nullable — user without department is valid."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.department_id is None


# ===========================================================================
# Employee profile tests
# ===========================================================================


class TestEmployeeProfiles:
    """Tests for employee_profiles table and EmployeeProfileRepository."""

    async def test_create_employee_profile(self, db_session: AsyncSession) -> None:
        """Should create an employee profile linked to a user."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = EmployeeProfileRepository(db_session)
        await repo.create(
            user_id=user.id,
            employee_code="EMP-001",
            designation="Software Engineer",
        )
        await db_session.commit()

        fetched = await repo.get_by_user_id(user.id)
        assert fetched is not None
        assert fetched.employee_code == "EMP-001"
        assert fetched.designation == "Software Engineer"

    async def test_employee_code_uniqueness(self, db_session: AsyncSession) -> None:
        """Two profiles with the same employee_code must raise IntegrityError."""
        u1 = _make_user(_EMPLOYEE_ROLE_ID)
        u2 = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add_all([u1, u2])
        await db_session.flush()

        repo = EmployeeProfileRepository(db_session)
        await repo.create(user_id=u1.id, employee_code="EMP-DUP")
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(user_id=u2.id, employee_code="EMP-DUP")
            await db_session.commit()

    async def test_one_to_one_constraint(self, db_session: AsyncSession) -> None:
        """A user can only have one employee profile (unique user_id)."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = EmployeeProfileRepository(db_session)
        await repo.create(user_id=user.id, employee_code="EMP-100")
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(user_id=user.id, employee_code="EMP-101")
            await db_session.commit()

    async def test_get_by_employee_code(self, db_session: AsyncSession) -> None:
        """get_by_employee_code should return the matching profile."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = EmployeeProfileRepository(db_session)
        await repo.create(user_id=user.id, employee_code="EMP-999")
        await db_session.commit()

        result = await repo.get_by_employee_code("EMP-999")
        assert result is not None
        assert result.employee_code == "EMP-999"

    async def test_salary_is_decimal(self, db_session: AsyncSession) -> None:
        """Salary should be stored and returned as Decimal (NUMERIC type)."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        profile = EmployeeProfile(
            user_id=user.id,
            salary=Decimal("75000.50"),
        )
        db_session.add(profile)
        await db_session.commit()
        await db_session.refresh(profile)

        # Should come back as Decimal-compatible value
        assert profile.salary is not None
        assert float(profile.salary) == pytest.approx(75000.50, rel=1e-4)

    async def test_manager_relationship(self, db_session: AsyncSession) -> None:
        """manager_id should reference a user (not a profile)."""
        manager = _make_user(_EMPLOYEE_ROLE_ID)
        employee_user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add_all([manager, employee_user])
        await db_session.flush()

        profile = EmployeeProfile(
            user_id=employee_user.id,
            manager_id=manager.id,
        )
        db_session.add(profile)
        await db_session.commit()
        await db_session.refresh(profile)

        assert profile.manager_id == manager.id


# ===========================================================================
# Document tests
# ===========================================================================


class TestDocuments:
    """Tests for the documents table and DocumentRepository."""

    async def test_create_document_metadata(self, db_session: AsyncSession) -> None:
        """Should create a document metadata record."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = DocumentRepository(db_session)
        doc = await repo.create(
            file_name="report.pdf",
            storage_path="uploads/report.pdf",
            owner_id=user.id,
            file_type="application/pdf",
            file_size=204800,
            checksum="abc123" * 10,
        )
        await db_session.commit()

        fetched = await repo.get_by_id(doc.id)
        assert fetched is not None
        assert fetched.file_name == "report.pdf"
        assert fetched.status == DocumentStatus.PENDING
        assert fetched.ocr_status == OcrStatus.PENDING

    async def test_document_owner_relationship(self, db_session: AsyncSession) -> None:
        """Owner user should be loaded via selectin."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = DocumentRepository(db_session)
        doc = await repo.create(
            file_name="test.pdf",
            storage_path="uploads/test.pdf",
            owner_id=user.id,
        )
        await db_session.commit()

        fetched = await repo.get_by_id(doc.id)
        assert fetched is not None
        assert fetched.owner_id == user.id

    async def test_document_soft_delete(self, db_session: AsyncSession) -> None:
        """Soft-deleted documents should not appear in get_by_id."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = DocumentRepository(db_session)
        doc = await repo.create(
            file_name="todelete.pdf",
            storage_path="uploads/todelete.pdf",
            owner_id=user.id,
        )
        await db_session.commit()

        await repo.soft_delete(doc.id)
        await db_session.commit()

        assert await repo.get_by_id(doc.id) is None

    async def test_get_documents_by_owner(self, db_session: AsyncSession) -> None:
        """get_by_owner should return documents for the correct user."""
        u1 = _make_user(_EMPLOYEE_ROLE_ID)
        u2 = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add_all([u1, u2])
        await db_session.flush()

        repo = DocumentRepository(db_session)
        await repo.create(file_name="a.pdf", storage_path="a", owner_id=u1.id)
        await repo.create(file_name="b.pdf", storage_path="b", owner_id=u1.id)
        await repo.create(file_name="c.pdf", storage_path="c", owner_id=u2.id)
        await db_session.commit()

        u1_docs = await repo.get_by_owner(u1.id)
        assert len(u1_docs) == 2
        assert all(d.owner_id == u1.id for d in u1_docs)


# ===========================================================================
# Document chunk tests
# ===========================================================================


class TestDocumentChunks:
    """Tests for the document_chunks table."""

    async def _create_doc(self, db_session: AsyncSession) -> Document:
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()
        doc = Document(
            file_name="chunked.pdf",
            storage_path="uploads/chunked.pdf",
            owner_id=user.id,
        )
        db_session.add(doc)
        await db_session.flush()
        return doc

    async def test_create_chunks(self, db_session: AsyncSession) -> None:
        """Should create ordered chunks for a document."""
        doc = await self._create_doc(db_session)

        chunks = [
            DocumentChunk(document_id=doc.id, chunk_number=i, content=f"chunk {i}")
            for i in range(3)
        ]
        db_session.add_all(chunks)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_number)
        )
        fetched = list(result.scalars().all())
        assert len(fetched) == 3
        assert [c.chunk_number for c in fetched] == [0, 1, 2]

    async def test_duplicate_chunk_number_rejected(self, db_session: AsyncSession) -> None:
        """Duplicate (document_id, chunk_number) must raise IntegrityError."""
        doc = await self._create_doc(db_session)

        db_session.add(DocumentChunk(document_id=doc.id, chunk_number=0, content="first"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(DocumentChunk(document_id=doc.id, chunk_number=0, content="duplicate"))
            await db_session.flush()

    async def test_chunk_document_relationship(self, db_session: AsyncSession) -> None:
        """Chunk should track its document_id FK."""
        doc = await self._create_doc(db_session)
        chunk = DocumentChunk(document_id=doc.id, chunk_number=0, content="test")
        db_session.add(chunk)
        await db_session.commit()
        await db_session.refresh(chunk)

        assert chunk.document_id == doc.id


# ===========================================================================
# AI embedding tests
# ===========================================================================


class TestAIEmbeddings:
    """Tests for the ai_embeddings table."""

    async def test_create_embedding_metadata(self, db_session: AsyncSession) -> None:
        """Should create embedding metadata for a chunk."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        doc = Document(file_name="e.pdf", storage_path="e", owner_id=user.id)
        db_session.add(doc)
        await db_session.flush()

        chunk = DocumentChunk(document_id=doc.id, chunk_number=0, content="text")
        db_session.add(chunk)
        await db_session.flush()

        embedding = AIEmbedding(
            document_chunk_id=chunk.id,
            vector_reference="faiss-idx-42",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
        db_session.add(embedding)
        await db_session.commit()
        await db_session.refresh(embedding)

        assert embedding.document_chunk_id == chunk.id
        assert embedding.vector_reference == "faiss-idx-42"

    async def test_embedding_one_to_one_chunk(self, db_session: AsyncSession) -> None:
        """Each chunk can only have one embedding (unique document_chunk_id)."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        doc = Document(file_name="uniq.pdf", storage_path="uniq", owner_id=user.id)
        db_session.add(doc)
        await db_session.flush()

        chunk = DocumentChunk(document_id=doc.id, chunk_number=0, content="txt")
        db_session.add(chunk)
        await db_session.flush()

        db_session.add(AIEmbedding(document_chunk_id=chunk.id))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(AIEmbedding(document_chunk_id=chunk.id))
            await db_session.flush()

    async def test_no_circular_fk(self, db_session: AsyncSession) -> None:
        """document_chunks should have NO embedding_id column."""
        chunk = DocumentChunk(document_id=uuid.uuid4(), chunk_number=0, content="test")
        # Verify there is no embedding_id attribute on the model
        assert not hasattr(chunk, "embedding_id"), (
            "DocumentChunk must not have an embedding_id column. "
            "The relationship flows via ai_embeddings.document_chunk_id only."
        )


# ===========================================================================
# Workflow tests
# ===========================================================================


class TestWorkflows:
    """Tests for workflow, workflow_steps, and workflow_executions tables."""

    async def test_create_workflow(self, db_session: AsyncSession) -> None:
        """Should create a workflow definition."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(name="Invoice Approval", created_by=user.id, is_active=True)
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        assert wf.name == "Invoice Approval"
        assert wf.is_active is True
        assert wf.version == 1
        assert wf.deleted_at is None

    async def test_workflow_steps_ordering(self, db_session: AsyncSession) -> None:
        """Workflow steps should be unique per (workflow_id, step_number)."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(name="Pipeline", created_by=user.id)
        db_session.add(wf)
        await db_session.flush()

        steps = [
            WorkflowStep(workflow_id=wf.id, step_number=i, action=f"action_{i}")
            for i in range(1, 4)
        ]
        db_session.add_all(steps)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == wf.id)
            .order_by(WorkflowStep.step_number)
        )
        fetched = list(result.scalars().all())
        assert [s.step_number for s in fetched] == [1, 2, 3]

    async def test_duplicate_step_number_rejected(self, db_session: AsyncSession) -> None:
        """Duplicate (workflow_id, step_number) must raise IntegrityError."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(name="DupTest", created_by=user.id)
        db_session.add(wf)
        await db_session.flush()

        db_session.add(WorkflowStep(workflow_id=wf.id, step_number=1, action="ocr"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(WorkflowStep(workflow_id=wf.id, step_number=1, action="dup"))
            await db_session.flush()

    async def test_workflow_execution_status(self, db_session: AsyncSession) -> None:
        """Should persist execution records with status enum."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(name="ExecTest", created_by=user.id)
        db_session.add(wf)
        await db_session.flush()

        execution = WorkflowExecution(
            workflow_id=wf.id,
            triggered_by=user.id,
            status=ExecutionStatus.COMPLETED,
            duration=1.23,
        )
        db_session.add(execution)
        await db_session.commit()
        await db_session.refresh(execution)

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.duration == pytest.approx(1.23)

    async def test_workflow_soft_delete(self, db_session: AsyncSession) -> None:
        """Soft-deleting a workflow sets deleted_at."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(name="ToDelete", created_by=user.id)
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        wf.deleted_at = datetime.now(UTC)
        await db_session.commit()
        await db_session.refresh(wf)

        assert wf.deleted_at is not None

    async def test_step_json_configuration(self, db_session: AsyncSession) -> None:
        """WorkflowStep.configuration should store and retrieve JSON."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        wf = Workflow(name="JsonTest", created_by=user.id)
        db_session.add(wf)
        await db_session.flush()

        config = {"timeout": 30, "recipients": ["a@b.com"]}
        step = WorkflowStep(
            workflow_id=wf.id,
            step_number=1,
            action="send_email",
            configuration=config,
        )
        db_session.add(step)
        await db_session.commit()
        await db_session.refresh(step)

        assert step.configuration == config


# ===========================================================================
# Notification tests
# ===========================================================================


class TestNotifications:
    """Tests for the notifications table."""

    async def test_create_notification(self, db_session: AsyncSession) -> None:
        """Should create a notification for a user."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        notif = Notification(
            user_id=user.id,
            title="Welcome",
            message="Your account is ready.",
            channel=NotificationChannel.IN_APP,
            priority=NotificationPriority.LOW,
        )
        db_session.add(notif)
        await db_session.commit()
        await db_session.refresh(notif)

        assert notif.is_read is False
        assert notif.channel == NotificationChannel.IN_APP

    async def test_mark_notification_read(self, db_session: AsyncSession) -> None:
        """is_read flag should be updatable."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        notif = Notification(
            user_id=user.id,
            title="Alert",
            message="Action required.",
        )
        db_session.add(notif)
        await db_session.commit()

        notif.is_read = True
        await db_session.commit()
        await db_session.refresh(notif)

        assert notif.is_read is True

    async def test_notification_user_relationship(self, db_session: AsyncSession) -> None:
        """Notification should track its user_id FK."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        notif = Notification(user_id=user.id, title="T", message="M")
        db_session.add(notif)
        await db_session.commit()
        await db_session.refresh(notif)

        assert notif.user_id == user.id

    async def test_notification_priority_enum(self, db_session: AsyncSession) -> None:
        """All priority levels should persist correctly."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        for priority in NotificationPriority:
            notif = Notification(
                user_id=user.id,
                title=f"P:{priority.value}",
                message="test",
                priority=priority,
            )
            db_session.add(notif)

        await db_session.commit()


# ===========================================================================
# Report tests
# ===========================================================================


class TestReports:
    """Tests for the reports table."""

    async def test_create_report(self, db_session: AsyncSession) -> None:
        """Should create a report metadata record."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        report = Report(
            report_type="revenue_monthly",
            generated_by=user.id,
            status=ReportStatus.PENDING,
        )
        db_session.add(report)
        await db_session.commit()
        await db_session.refresh(report)

        assert report.report_type == "revenue_monthly"
        assert report.status == ReportStatus.PENDING
        assert report.file_path is None

    async def test_report_status_transitions(self, db_session: AsyncSession) -> None:
        """Report status should be updatable through lifecycle."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        report = Report(report_type="test_report", generated_by=user.id)
        db_session.add(report)
        await db_session.commit()

        report.status = ReportStatus.COMPLETED
        report.generated_at = datetime.now(UTC)
        report.file_path = "reports/test_report_2026.pdf"
        await db_session.commit()
        await db_session.refresh(report)

        assert report.status == ReportStatus.COMPLETED
        assert report.generated_at is not None

    async def test_report_user_relationship(self, db_session: AsyncSession) -> None:
        """Report should track its generated_by FK."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        report = Report(report_type="hr_report", generated_by=user.id)
        db_session.add(report)
        await db_session.commit()
        await db_session.refresh(report)

        assert report.generated_by == user.id


# ===========================================================================
# Prediction tests
# ===========================================================================


class TestPredictions:
    """Tests for the predictions table, specifically JSONB fields."""

    async def test_create_prediction_with_json(self, db_session: AsyncSession) -> None:
        """Should store and retrieve structured JSON input/prediction data."""
        prediction = Prediction(
            model="revenue_forecast_v2",
            input={"department": "sales", "month": "2026-08"},
            prediction={"revenue": 125000.0, "growth": 0.12},
            confidence=0.87,
            execution_time=0.045,
        )
        db_session.add(prediction)
        await db_session.commit()
        await db_session.refresh(prediction)

        assert prediction.model == "revenue_forecast_v2"
        assert prediction.input is not None
        assert prediction.input["department"] == "sales"
        assert prediction.prediction is not None
        assert prediction.prediction["revenue"] == pytest.approx(125000.0)
        assert prediction.confidence == pytest.approx(0.87)

    async def test_prediction_nullable_fields(self, db_session: AsyncSession) -> None:
        """input, prediction, confidence, and execution_time can all be null."""
        prediction = Prediction(model="simple_model")
        db_session.add(prediction)
        await db_session.commit()
        await db_session.refresh(prediction)

        assert prediction.input is None
        assert prediction.prediction is None
        assert prediction.confidence is None
        assert prediction.execution_time is None

    async def test_prediction_repr(self) -> None:
        """Prediction __repr__ should not raise."""
        p = Prediction(model="test_model")
        assert "test_model" in repr(p)


# ===========================================================================
# Audit log tests
# ===========================================================================


class TestAuditLogs:
    """Tests for the audit_logs table and AuditLogRepository."""

    async def test_create_audit_log(self, db_session: AsyncSession) -> None:
        """Should create an audit log entry with JSON values."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        repo = AuditLogRepository(db_session)
        log = await repo.create(
            action="user.login",
            user_id=user.id,
            table_name="users",
            record_id=user.id,
            old_value=None,
            new_value={"last_login": "2026-08-16T13:00:00Z"},
            ip_address="192.168.1.1",
        )
        await db_session.commit()

        assert log.action == "user.login"
        assert log.new_value is not None
        assert log.new_value["last_login"] == "2026-08-16T13:00:00Z"

    async def test_system_audit_log_no_user(self, db_session: AsyncSession) -> None:
        """Audit logs with no user (system events) should be valid."""
        repo = AuditLogRepository(db_session)
        log = await repo.create(
            action="system.startup",
            user_id=None,
        )
        await db_session.commit()

        assert log.user_id is None
        assert log.action == "system.startup"

    async def test_record_id_no_fk(self, db_session: AsyncSession) -> None:
        """record_id can reference a UUID from any table — no FK enforced."""
        fake_record_id = uuid.uuid4()  # Does not exist in any table
        repo = AuditLogRepository(db_session)
        log = await repo.create(
            action="document.delete",
            record_id=fake_record_id,
            table_name="documents",
        )
        await db_session.commit()

        # Should not raise IntegrityError — no FK constraint on record_id
        assert log.record_id == fake_record_id

    async def test_get_audit_logs_by_user(self, db_session: AsyncSession) -> None:
        """get_by_user should return logs for the correct user."""
        u1 = _make_user(_EMPLOYEE_ROLE_ID)
        u2 = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add_all([u1, u2])
        await db_session.flush()

        repo = AuditLogRepository(db_session)
        await repo.create(action="a.one", user_id=u1.id)
        await repo.create(action="a.two", user_id=u1.id)
        await repo.create(action="b.one", user_id=u2.id)
        await db_session.commit()

        u1_logs = await repo.get_by_user(u1.id)
        assert len(u1_logs) == 2
        assert all(log.user_id == u1.id for log in u1_logs)

    async def test_json_old_new_values(self, db_session: AsyncSession) -> None:
        """old_value and new_value should store and retrieve nested JSON."""
        repo = AuditLogRepository(db_session)
        log = await repo.create(
            action="user.update",
            old_value={"first_name": "John", "department": None},
            new_value={"first_name": "Jane", "department": "Engineering"},
        )
        await db_session.commit()
        await db_session.refresh(log)

        assert log.old_value is not None
        assert log.old_value["first_name"] == "John"
        assert log.new_value is not None
        assert log.new_value["department"] == "Engineering"


# ===========================================================================
# Settings tests
# ===========================================================================


class TestSettings:
    """Tests for the settings table."""

    async def test_create_setting(self, db_session: AsyncSession) -> None:
        """Should create a setting key/value pair."""
        setting = Setting(
            key="company_name",
            value="IntelliFlow Corp",
            description="The legal company name.",
            is_public=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        assert setting.key == "company_name"
        assert setting.value == "IntelliFlow Corp"
        assert setting.is_public is True

    async def test_setting_key_uniqueness(self, db_session: AsyncSession) -> None:
        """Duplicate setting keys must raise IntegrityError."""
        db_session.add(Setting(key="theme", value="dark"))
        await db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(Setting(key="theme", value="light"))
            await db_session.flush()

    async def test_setting_nullable_value(self, db_session: AsyncSession) -> None:
        """Setting value can be null (placeholder for future configuration)."""
        setting = Setting(key="smtp_from_name", value=None, is_public=False)
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        assert setting.value is None

    async def test_setting_is_not_for_secrets(self) -> None:
        """
        Verify the docstring on Setting warns against storing secrets.

        This is a documentation-level safety check, not a DB constraint.
        Sensitive values must live in environment variables / Settings class.
        """
        doc = Setting.__doc__ or ""
        assert "NEVER" in doc or "never" in doc.lower()


# ===========================================================================
# AI conversation tests
# ===========================================================================


class TestAIConversations:
    """Tests for the ai_conversations table."""

    async def test_create_conversation(self, db_session: AsyncSession) -> None:
        """Should persist a question/answer exchange."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        conv = AIConversation(
            user_id=user.id,
            question="What is the revenue for Q3?",
            answer="The revenue for Q3 was $500,000.",
            prompt_tokens=42,
            completion_tokens=18,
            response_time=0.82,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.question == "What is the revenue for Q3?"
        assert conv.prompt_tokens == 42
        assert conv.response_time == pytest.approx(0.82)

    async def test_conversation_user_relationship(self, db_session: AsyncSession) -> None:
        """Conversation should track its user_id FK."""
        user = _make_user(_EMPLOYEE_ROLE_ID)
        db_session.add(user)
        await db_session.flush()

        conv = AIConversation(user_id=user.id, question="Q?")
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        assert conv.user_id == user.id


# ===========================================================================
# Repository foundation tests
# ===========================================================================


class TestRepositoryFoundations:
    """Basic tests that all repositories initialise correctly."""

    async def test_department_repo_initialises(self, db_session: AsyncSession) -> None:
        repo = DepartmentRepository(db_session)
        assert repo is not None

    async def test_employee_profile_repo_initialises(self, db_session: AsyncSession) -> None:
        repo = EmployeeProfileRepository(db_session)
        assert repo is not None

    async def test_document_repo_initialises(self, db_session: AsyncSession) -> None:
        repo = DocumentRepository(db_session)
        assert repo is not None

    async def test_audit_log_repo_initialises(self, db_session: AsyncSession) -> None:
        repo = AuditLogRepository(db_session)
        assert repo is not None

    async def test_get_by_id_nonexistent_returns_none(self, db_session: AsyncSession) -> None:
        """Querying a non-existent UUID should return None, not raise."""
        repo = DepartmentRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None
