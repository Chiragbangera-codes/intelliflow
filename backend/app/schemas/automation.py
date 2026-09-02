"""
Automation Rule and Execution Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.automation import AutomationStatus


class AutomationCondition(BaseModel):
    """Condition item for rule evaluation."""

    field: str = Field(
        ..., description="Dot-notation path into event context (e.g. 'payload.confidentiality')"
    )
    operator: str = Field(
        "equals", description="Comparison operator: equals, not_equals, contains, in, gt, lt, etc."
    )
    value: Any = Field(None, description="Expected value for comparison")


class AutomationAction(BaseModel):
    """Action item to execute when conditions match."""

    type: str = Field(
        ...,
        description="Action type: send_notification, send_webhook, send_integration, trigger_workflow, create_report",
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Action configuration parameters"
    )


class AutomationRuleCreate(BaseModel):
    """Payload to create a new automation rule."""

    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    trigger_event: str = Field(..., min_length=2, max_length=100)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class AutomationRuleUpdate(BaseModel):
    """Payload to update an existing automation rule."""

    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    trigger_event: str | None = Field(default=None, min_length=2, max_length=100)
    conditions: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class AutomationRuleResponse(BaseModel):
    """Automation rule details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    trigger_event: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    is_active: bool
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AutomationRuleListResponse(BaseModel):
    """Paginated list of automation rules."""

    items: list[AutomationRuleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AutomationExecutionResponse(BaseModel):
    """Automation execution log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: uuid.UUID
    event_id: uuid.UUID | None = None
    event_type: str
    status: AutomationStatus
    action_results: list[dict[str, Any]]
    error_message: str | None = None
    execution_time_ms: int | None = None
    created_at: datetime


class AutomationExecutionListResponse(BaseModel):
    """Paginated list of execution logs."""

    items: list[AutomationExecutionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AutomationTestRequest(BaseModel):
    """Payload for dry-run testing of rule conditions."""

    event_context: dict[str, Any] = Field(default_factory=dict)


class AutomationTestResponse(BaseModel):
    """Result of dry-run evaluation."""

    rule_id: str
    matched: bool
    conditions_met: bool
    dry_run: bool = True
    actions_to_execute: int = 0
    duration_ms: int = 0
