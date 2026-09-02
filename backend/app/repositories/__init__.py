"""
Repositories package.

The repository layer is the only place that communicates with the database.
Repositories are never called directly from API routes — always from services.
"""

from app.repositories.ai_conversation_repository import AIConversationRepository
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.automation_repository import AutomationRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_share_repository import DocumentShareRepository
from app.repositories.document_version_repository import DocumentVersionRepository
from app.repositories.employee_profile_repository import EmployeeProfileRepository
from app.repositories.event_repository import EventRepository, OutboxRepository
from app.repositories.integration_repository import IntegrationRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.prediction_repository import PredictionRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.search_repository import SearchRepository
from app.repositories.user_repository import UserRepository
from app.repositories.webhook_repository import WebhookRepository

__all__ = [
    # Milestone 2
    "UserRepository",
    "RoleRepository",
    "RefreshTokenRepository",
    # Milestone 3
    "DepartmentRepository",
    "EmployeeProfileRepository",
    "DocumentRepository",
    "AuditLogRepository",
    # Milestone 6
    "DocumentChunkRepository",
    # Milestone 7
    "SearchRepository",
    "AIConversationRepository",
    # Milestone 9
    "AnalyticsRepository",
    "PredictionRepository",
    "ReportRepository",
    # Milestone 10
    "NotificationRepository",
    # Milestone 11
    "DocumentVersionRepository",
    "DocumentShareRepository",
    # Milestone 13
    "EventRepository",
    "OutboxRepository",
    "WebhookRepository",
    "IntegrationRepository",
    "AutomationRepository",
]
