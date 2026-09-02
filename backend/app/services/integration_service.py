"""
Integration Service.

Manages external integration endpoints, credential encryption at rest,
and external message dispatching.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_json, encrypt_data
from app.models.integration import Integration, IntegrationProvider, IntegrationStatus
from app.repositories.integration_repository import IntegrationRepository
from app.services.integration_providers import get_integration_provider

logger = logging.getLogger(__name__)


class IntegrationService:
    """Service for managing external integrations with encrypted credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = IntegrationRepository(session)

    async def create_integration(
        self,
        provider: IntegrationProvider,
        name: str,
        configuration: dict[str, Any],
        description: str | None = None,
        credentials: dict[str, Any] | None = None,
        status: IntegrationStatus = IntegrationStatus.ACTIVE,
        created_by: uuid.UUID | None = None,
    ) -> Integration:
        """
        Create a new integration and encrypt its credentials at rest.
        """
        encrypted_creds = encrypt_data(credentials) if credentials else None

        integration = await self.repo.create(
            provider=provider,
            name=name.strip(),
            description=description.strip() if description else None,
            configuration=configuration or {},
            encrypted_credentials=encrypted_creds,
            status=status,
            created_by=created_by,
        )
        await self.session.commit()
        return integration

    async def get_by_id(self, integration_id: uuid.UUID) -> Integration | None:
        """Fetch an integration by ID."""
        return await self.repo.get_by_id(integration_id)

    async def list_integrations(
        self,
        page: int = 1,
        page_size: int = 20,
        provider: IntegrationProvider | None = None,
        status: IntegrationStatus | None = None,
    ) -> tuple[list[Integration], int]:
        """List integrations with filtering and pagination."""
        return await self.repo.list_integrations(
            page=page, page_size=page_size, provider=provider, status=status
        )

    async def update_integration(
        self,
        integration_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        status: IntegrationStatus | None = None,
        configuration: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> Integration | None:
        """
        Update integration configuration or credentials.
        """
        encrypted_creds = encrypt_data(credentials) if credentials is not None else None

        updated = await self.repo.update(
            integration_id=integration_id,
            name=name.strip() if name is not None else None,
            description=description.strip() if description is not None else None,
            status=status,
            configuration=configuration,
            encrypted_credentials=encrypted_creds,
        )
        if updated:
            await self.session.commit()
        return updated

    async def delete_integration(self, integration_id: uuid.UUID) -> bool:
        """Delete an integration."""
        deleted = await self.repo.delete(integration_id)
        if deleted:
            await self.session.commit()
        return deleted

    async def test_connection(
        self, integration_id: uuid.UUID, allow_test_local: bool = False
    ) -> dict[str, Any]:
        """Test connectivity and authentication for an integration."""
        integration = await self.get_by_id(integration_id)
        if not integration:
            return {"success": False, "error": "Integration not found."}

        creds = decrypt_json(integration.encrypted_credentials)
        provider_handler = get_integration_provider(integration.provider)

        result = await provider_handler.test_connection(
            configuration=integration.configuration,
            credentials=creds,
            allow_test_local=allow_test_local,
        )

        if result.get("success"):
            await self.repo.update_last_synced_at(integration.id, datetime.now(UTC))
            await self.session.commit()

        return result

    async def dispatch(
        self,
        integration_id: uuid.UUID,
        payload: dict[str, Any],
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        """Dispatch a message to the external provider."""
        integration = await self.get_by_id(integration_id)
        if not integration:
            return {"success": False, "error": "Integration not found."}

        if integration.status != IntegrationStatus.ACTIVE:
            return {"success": False, "error": f"Integration is {integration.status.value}."}

        creds = decrypt_json(integration.encrypted_credentials)
        provider_handler = get_integration_provider(integration.provider)

        result = await provider_handler.send_message(
            payload=payload,
            configuration=integration.configuration,
            credentials=creds,
            allow_test_local=allow_test_local,
        )

        if result.get("success"):
            await self.repo.update_last_synced_at(integration.id, datetime.now(UTC))
            await self.session.commit()

        return result
