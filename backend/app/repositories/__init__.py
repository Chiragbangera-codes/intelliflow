"""
Repositories package.

The repository layer is the only place that communicates with the database.
Repositories are never called directly from API routes — always from services.

Architecture pattern:
    class SomeRepository:
        def __init__(self, db: AsyncSession) -> None:
            self._session = db

        async def get_by_id(self, record_id: UUID) -> Model | None:
            ...

Milestone 2 repositories:
    UserRepository         — users table
    RoleRepository         — roles table
    RefreshTokenRepository — refresh_tokens table

Milestone 3 repositories:
    DepartmentRepository      — departments table
    EmployeeProfileRepository — employee_profiles table
    DocumentRepository        — documents table
    AuditLogRepository        — audit_logs table (append-only)
"""

from app.repositories.ai_conversation_repository import AIConversationRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.employee_profile_repository import EmployeeProfileRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.search_repository import SearchRepository
from app.repositories.user_repository import UserRepository

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
    # Milestone 7 Phase 2
    "SearchRepository",
    # Milestone 7 Phase 3
    "AIConversationRepository",
]
