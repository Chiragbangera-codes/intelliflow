"""
Automation Rules API endpoints.

Endpoints:
  GET    /api/v1/automations                 — List automation rules
  POST   /api/v1/automations                 — Create an automation rule
  GET    /api/v1/automations/{id}            — Get rule details
  PATCH  /api/v1/automations/{id}            — Update rule conditions/actions
  DELETE /api/v1/automations/{id}            — Delete rule
  GET    /api/v1/automations/{id}/executions — List rule execution history
  POST   /api/v1/automations/{id}/test       — Dry-run condition evaluation
"""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.dependencies.permissions import require_role
from app.models.automation import AutomationStatus
from app.models.user import User
from app.schemas.automation import (
    AutomationExecutionListResponse,
    AutomationExecutionResponse,
    AutomationRuleCreate,
    AutomationRuleListResponse,
    AutomationRuleResponse,
    AutomationRuleUpdate,
    AutomationTestRequest,
    AutomationTestResponse,
)
from app.services.automation_service import AutomationService

router = APIRouter(prefix="/automations", tags=["Automations"])


@router.get("", response_model=AutomationRuleListResponse)
async def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trigger_event: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> AutomationRuleListResponse:
    """List automation rules (admin and manager)."""
    service = AutomationService(db)
    items, total = await service.list_rules(
        page=page, page_size=page_size, trigger_event=trigger_event, is_active=is_active
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return AutomationRuleListResponse(
        items=[AutomationRuleResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: AutomationRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> AutomationRuleResponse:
    """Create a new automation rule (admin only)."""
    service = AutomationService(db)
    rule = await service.create_rule(
        name=payload.name,
        trigger_event=payload.trigger_event,
        conditions=payload.conditions,
        actions=payload.actions,
        description=payload.description,
        is_active=payload.is_active,
        created_by=current_user.id,
    )
    return AutomationRuleResponse.model_validate(rule)


@router.get("/{id}", response_model=AutomationRuleResponse)
async def get_rule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> AutomationRuleResponse:
    """Get automation rule details (admin and manager)."""
    service = AutomationService(db)
    rule = await service.get_rule_by_id(id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found.",
        )
    return AutomationRuleResponse.model_validate(rule)


@router.patch("/{id}", response_model=AutomationRuleResponse)
async def update_rule(
    id: uuid.UUID,
    payload: AutomationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> AutomationRuleResponse:
    """Update an automation rule (admin only)."""
    service = AutomationService(db)
    updated = await service.update_rule(
        rule_id=id,
        name=payload.name,
        description=payload.description,
        trigger_event=payload.trigger_event,
        conditions=payload.conditions,
        actions=payload.actions,
        is_active=payload.is_active,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found.",
        )
    return AutomationRuleResponse.model_validate(updated)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_rule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Response:
    """Delete an automation rule (admin only)."""
    service = AutomationService(db)
    deleted = await service.delete_rule(id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{id}/executions", response_model=AutomationExecutionListResponse)
async def list_executions(
    id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: AutomationStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "manager")),
) -> AutomationExecutionListResponse:
    """List execution history for an automation rule (admin and manager)."""
    service = AutomationService(db)
    rule = await service.get_rule_by_id(id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found.",
        )

    items, total = await service.list_executions(
        rule_id=id, page=page, page_size=page_size, status=status_filter
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return AutomationExecutionListResponse(
        items=[AutomationExecutionResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/{id}/test", response_model=AutomationTestResponse)
async def test_rule(
    id: uuid.UUID,
    payload: AutomationTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> AutomationTestResponse:
    """Dry-run test automation rule conditions against sample event context (admin only)."""
    service = AutomationService(db)
    rule = await service.get_rule_by_id(id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found.",
        )

    result = await service.evaluate_and_run_rule(
        rule=rule,
        event_context=payload.event_context,
        dry_run=True,
    )
    if isinstance(result, dict):
        return AutomationTestResponse(
            rule_id=str(rule.id),
            matched=result.get("matched", False),
            conditions_met=result.get("conditions_met", False),
            dry_run=True,
            actions_to_execute=result.get("actions_to_execute", 0),
            duration_ms=result.get("duration_ms", 0),
        )
    return AutomationTestResponse(
        rule_id=str(rule.id),
        matched=True,
        conditions_met=True,
        dry_run=True,
        actions_to_execute=len(rule.actions or []),
        duration_ms=0,
    )
