"""
Integration repository.

Provides database operations for external integration provider endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import Integration, IntegrationProvider, IntegrationStatus


class IntegrationRepository:
    """Repository for managing Integration records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        provider: IntegrationProvider,
        name: str,
        configuration: dict[str, Any],
        description: str | None = None,
        encrypted_credentials: str | None = None,
        status: IntegrationStatus = IntegrationStatus.ACTIVE,
        created_by: uuid.UUID | None = None,
    ) -> Integration:
        """Create and persist a new Integration."""
        integration = Integration(
            provider=provider,
            name=name,
            description=description,
            status=status,
            configuration=configuration,
            encrypted_credentials=encrypted_credentials,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(integration)
        await self.session.flush()
        return integration

    async def get_by_id(self, integration_id: uuid.UUID) -> Integration | None:
        """Fetch an integration by ID."""
        stmt = select(Integration).where(Integration.id == integration_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_integrations(
        self,
        page: int = 1,
        page_size: int = 20,
        provider: IntegrationProvider | None = None,
        status: IntegrationStatus | None = None,
    ) -> tuple[list[Integration], int]:
        """List integrations with filtering and pagination."""
        stmt = select(Integration)
        count_stmt = select(func.count(Integration.id))

        if provider is not None:
            stmt = stmt.where(Integration.provider == provider)
            count_stmt = count_stmt.where(Integration.provider == provider)
        if status is not None:
            stmt = stmt.where(Integration.status == status)
            count_stmt = count_stmt.where(Integration.status == status)

        total_res = await self.session.execute(count_stmt)
        total_items = total_res.scalar() or 0

        stmt = (
            stmt.order_by(Integration.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items_res = await self.session.execute(stmt)
        integrations = list(items_res.scalars().all())

        return integrations, total_items

    async def update(
        self,
        integration_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        status: IntegrationStatus | None = None,
        configuration: dict[str, Any] | None = None,
        encrypted_credentials: str | None = None,
    ) -> Integration | None:
        """Update integration configuration or credentials."""
        integration = await self.get_by_id(integration_id)
        if not integration:
            return None

        if name is not None:
            integration.name = name
        if description is not None:
            integration.description = description
        if status is not None:
            integration.status = status
        if configuration is not None:
            integration.configuration = configuration
        if encrypted_credentials is not None:
            integration.encrypted_credentials = encrypted_credentials

        integration.updated_at = datetime.now(UTC)
        await self.session.flush()
        return integration

    async def delete(self, integration_id: uuid.UUID) -> bool:
        """Delete an integration."""
        integration = await self.get_by_id(integration_id)
        if not integration:
            return False
        await self.session.delete(integration)
        await self.session.flush()
        return True

    async def update_last_synced_at(
        self, integration_id: uuid.UUID, timestamp: datetime | None = None
    ) -> None:
        """Update last sync timestamp."""
        integration = await self.get_by_id(integration_id)
        if integration:
            integration.last_synced_at = timestamp or datetime.now(UTC)
            await self.session.flush()
