"""
Enterprise Integrations API endpoints.

Endpoints:
  GET    /api/v1/integrations           — List integrations
  POST   /api/v1/integrations           — Create an integration
  GET    /api/v1/integrations/{id}      — Get integration details
  PATCH  /api/v1/integrations/{id}      — Update integration configuration / credentials
  DELETE /api/v1/integrations/{id}      — Delete an integration
  POST   /api/v1/integrations/{id}/test — Test provider connectivity
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.integration import IntegrationProvider, IntegrationStatus
from app.models.user import User
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
    IntegrationTestResponse,
    IntegrationUpdate,
)
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


def _to_response(integration: Any) -> IntegrationResponse:
    """Helper to transform ORM integration into response schema without secrets."""
    has_creds = bool(integration.encrypted_credentials)
    return IntegrationResponse(
        id=integration.id,
        provider=integration.provider,
        name=integration.name,
        description=integration.description,
        status=integration.status,
        configuration=integration.configuration or {},
        has_credentials=has_creds,
        created_by=integration.created_by,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        last_synced_at=integration.last_synced_at,
    )


@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: IntegrationProvider | None = Query(None),
    status_filter: IntegrationStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> IntegrationListResponse:
    """List configured integrations (admin and manager)."""
    service = IntegrationService(db)
    items, total = await service.list_integrations(
        page=page, page_size=page_size, provider=provider, status=status_filter
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return IntegrationListResponse(
        items=[_to_response(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IntegrationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> IntegrationResponse:
    """Create a new integration endpoint (admin only)."""
    service = IntegrationService(db)
    integration = await service.create_integration(
        provider=payload.provider,
        name=payload.name,
        configuration=payload.configuration,
        description=payload.description,
        credentials=payload.credentials,
        status=payload.status,
        created_by=current_user.id,
    )
    return _to_response(integration)


@router.get("/{id}", response_model=IntegrationResponse)
async def get_integration(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> IntegrationResponse:
    """Get integration details by ID (admin and manager)."""
    service = IntegrationService(db)
    integration = await service.get_by_id(id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found.",
        )
    return _to_response(integration)


@router.patch("/{id}", response_model=IntegrationResponse)
async def update_integration(
    id: uuid.UUID,
    payload: IntegrationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> IntegrationResponse:
    """Update an integration configuration or credentials (admin only)."""
    service = IntegrationService(db)
    updated = await service.update_integration(
        integration_id=id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        configuration=payload.configuration,
        credentials=payload.credentials,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found.",
        )
    return _to_response(updated)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_integration(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Response:
    """Delete an integration (admin only)."""
    service = IntegrationService(db)
    deleted = await service.delete_integration(id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id}/test", response_model=IntegrationTestResponse)
async def test_integration(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> IntegrationTestResponse:
    """Test external connection to the integration provider (admin only)."""
    service = IntegrationService(db)
    result = await service.test_connection(id)
    return IntegrationTestResponse(
        success=result.get("success", False),
        status_code=result.get("status_code"),
        response=result.get("response"),
        error=result.get("error"),
        message=result.get("message"),
    )
