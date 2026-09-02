"""
ORM Models package.

All SQLAlchemy models must be imported here so that:
  1. Alembic's autogenerate can discover schema changes.
  2. SQLAlchemy's relationship registry can resolve forward references.
  3. Base.metadata is complete when migrations run.

Import order respects FK dependencies (parents before children):
  Role          — no FK deps
  Department    — no FK deps
  User          — depends on Role, Department
  RefreshToken  — depends on User
  EmployeeProfile — depends on User
  Document        — depends on User, Department
  DocumentVersion — depends on Document, User
  DocumentShare   — depends on Document, User
  DocumentChunk   — depends on Document, DocumentVersion
  AIEmbedding     — depends on DocumentChunk
  AIConversation  — depends on User
  Workflow        — depends on User
  WorkflowStep    — depends on Workflow
  WorkflowExecution — depends on Workflow, User
  Notification    — depends on User
  Report          — depends on User
  Prediction      — no FK deps (standalone)
  AuditLog        — depends on User
  Setting         — no FK deps (standalone)
"""

from app.models.ai_conversation import AIConversation
from app.models.ai_embedding import AIEmbedding
from app.models.audit_log import AuditLog
from app.models.automation import (
    AutomationExecution,
    AutomationRule,
    AutomationStatus,
)
from app.models.department import Department
from app.models.document import (
    Document,
    DocumentConfidentiality,
    DocumentLifecycleStatus,
    DocumentStatus,
    OcrStatus,
)
from app.models.document_chunk import DocumentChunk
from app.models.document_share import DocumentShare, DocumentSharePermission
from app.models.document_version import DocumentVersion
from app.models.employee_profile import EmployeeProfile
from app.models.event import (
    Event,
    EventStatus,
    OutboxEvent,
)
from app.models.integration import (
    Integration,
    IntegrationProvider,
    IntegrationStatus,
)
from app.models.notification import Notification, NotificationChannel, NotificationPriority
from app.models.prediction import Prediction
from app.models.refresh_token import RefreshToken
from app.models.report import Report, ReportStatus
from app.models.role import Role
from app.models.setting import Setting
from app.models.user import User, UserStatus
from app.models.webhook import (
    Webhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
)
from app.models.workflow import Workflow
from app.models.workflow_execution import ExecutionStatus, WorkflowExecution
from app.models.workflow_step import WorkflowStep

__all__ = [
    # Auth (Milestone 2)
    "Role",
    "User",
    "UserStatus",
    "RefreshToken",
    # Milestone 3 — core entities
    "Department",
    "EmployeeProfile",
    # Documents & Intelligence (Milestones 5, 6, 11)
    "Document",
    "DocumentStatus",
    "OcrStatus",
    "DocumentLifecycleStatus",
    "DocumentConfidentiality",
    "DocumentVersion",
    "DocumentShare",
    "DocumentSharePermission",
    "DocumentChunk",
    "AIEmbedding",
    # AI
    "AIConversation",
    # Workflows
    "Workflow",
    "WorkflowStep",
    "WorkflowExecution",
    "ExecutionStatus",
    # Operational
    "Notification",
    "NotificationChannel",
    "NotificationPriority",
    "Report",
    "ReportStatus",
    "Prediction",
    "AuditLog",
    "Setting",
    # Milestone 13 — Enterprise Integrations & Event Bus
    "Event",
    "OutboxEvent",
    "EventStatus",
    "Webhook",
    "WebhookDelivery",
    "WebhookDeliveryStatus",
    "Integration",
    "IntegrationProvider",
    "IntegrationStatus",
    "AutomationRule",
    "AutomationExecution",
    "AutomationStatus",
]
