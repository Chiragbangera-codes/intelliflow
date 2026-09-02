"""
Workflow Pydantic schemas — Milestone 8.

Request and response models for the workflow engine API.

Validation rules enforced here:
  - name:          1–200 chars, non-blank.
  - description:   0–2000 chars when provided.
  - steps:         1–WORKFLOW_MAX_STEPS steps, step_number must be unique
                   and form a contiguous 1-based sequence.
  - action:        Must be one of the 5 supported action types.
  - configuration: Action-specific validation (see _validate_config()).
  - timeout:       1–3600 seconds when provided.
  - retry_count:   0–5 retries maximum.
  - delay.seconds: 1–WORKFLOW_MAX_DELAY_SECONDS.

Security:
  - No stack traces, secrets, or SMTP credentials are ever serialised.
  - Malformed configurations are rejected with 422 before reaching the service.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings

# ---------------------------------------------------------------------------
# Supported action types (single source of truth)
# ---------------------------------------------------------------------------
SUPPORTED_ACTIONS = frozenset({"notify", "send_email", "archive_document", "approve", "delay"})


# ---------------------------------------------------------------------------
# Step configuration validators
# ---------------------------------------------------------------------------


def _validate_notify_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate `notify` step configuration."""
    required = {"user_id", "title", "message"}
    missing = required - cfg.keys()
    if missing:
        raise ValueError(f"notify configuration missing required keys: {sorted(missing)}")
    if not isinstance(cfg["title"], str) or not cfg["title"].strip():
        raise ValueError("notify.title must be a non-blank string")
    if not isinstance(cfg["message"], str) or not cfg["message"].strip():
        raise ValueError("notify.message must be a non-blank string")
    if len(cfg["title"]) > 500:
        raise ValueError("notify.title must not exceed 500 characters")
    if len(cfg["message"]) > 5000:
        raise ValueError("notify.message must not exceed 5000 characters")
    # Validate user_id is a valid UUID string
    try:
        uuid.UUID(str(cfg["user_id"]))
    except (ValueError, AttributeError) as exc:
        raise ValueError("notify.user_id must be a valid UUID") from exc
    return cfg


def _validate_send_email_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate `send_email` step configuration."""
    required = {"to", "subject", "body"}
    missing = required - cfg.keys()
    if missing:
        raise ValueError(f"send_email configuration missing required keys: {sorted(missing)}")
    if not isinstance(cfg["to"], str) or "@" not in cfg["to"]:
        raise ValueError("send_email.to must be a valid email address")
    if not isinstance(cfg["subject"], str) or not cfg["subject"].strip():
        raise ValueError("send_email.subject must be a non-blank string")
    if not isinstance(cfg["body"], str) or not cfg["body"].strip():
        raise ValueError("send_email.body must be a non-blank string")
    if len(cfg["subject"]) > 998:
        raise ValueError("send_email.subject must not exceed 998 characters")
    return cfg


def _validate_archive_document_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate `archive_document` step configuration."""
    if "document_id" not in cfg:
        raise ValueError("archive_document configuration must include 'document_id'")
    try:
        uuid.UUID(str(cfg["document_id"]))
    except (ValueError, AttributeError) as exc:
        raise ValueError("archive_document.document_id must be a valid UUID") from exc
    return cfg


def _validate_approve_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate `approve` step configuration (approver_user_id is optional)."""
    if "approver_user_id" in cfg:
        try:
            uuid.UUID(str(cfg["approver_user_id"]))
        except (ValueError, AttributeError) as exc:
            raise ValueError("approve.approver_user_id must be a valid UUID") from exc
    return cfg


def _validate_delay_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate `delay` step configuration."""
    if "seconds" not in cfg:
        raise ValueError("delay configuration must include 'seconds'")
    seconds = cfg["seconds"]
    if not isinstance(seconds, int | float):
        raise ValueError("delay.seconds must be a number")
    seconds = int(seconds)
    if seconds < 1:
        raise ValueError("delay.seconds must be >= 1")
    if seconds > settings.WORKFLOW_MAX_DELAY_SECONDS:
        raise ValueError(
            f"delay.seconds must not exceed {settings.WORKFLOW_MAX_DELAY_SECONDS} "
            f"(configured WORKFLOW_MAX_DELAY_SECONDS)"
        )
    cfg["seconds"] = seconds  # normalise to int
    return cfg


_CONFIG_VALIDATORS = {
    "notify": _validate_notify_config,
    "send_email": _validate_send_email_config,
    "archive_document": _validate_archive_document_config,
    "approve": _validate_approve_config,
    "delay": _validate_delay_config,
}


# ===========================================================================
# Step schemas
# ===========================================================================


class WorkflowStepCreate(BaseModel):
    """
    Schema for creating a single workflow step.

    step_number must be a 1-based integer unique within the workflow.
    action must be one of the 5 supported types.
    configuration is validated per action type.
    """

    step_number: int = Field(
        ...,
        ge=1,
        le=100,
        description="1-based ordering position of this step within the workflow.",
    )
    action: str = Field(
        ...,
        description=f"Action type. One of: {', '.join(sorted(SUPPORTED_ACTIONS))}.",
    )
    configuration: dict[str, Any] | None = Field(
        default=None,
        description="Action-specific configuration object. Validated per action type.",
    )
    timeout: int | None = Field(
        default=None,
        ge=1,
        le=3600,
        description="Maximum execution time in seconds (1–3600). None = no timeout.",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Number of retry attempts on failure (0–5). 0 = no retries.",
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Reject unsupported action types immediately."""
        normalised = v.strip().lower()
        if normalised not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"Unsupported action '{v}'. "
                f"Supported actions: {', '.join(sorted(SUPPORTED_ACTIONS))}."
            )
        return normalised

    @model_validator(mode="after")
    def validate_configuration(self) -> WorkflowStepCreate:
        """Validate configuration dict against action-specific rules."""
        action = self.action
        config = self.configuration or {}

        # `approve` and `delay` require a configuration dict
        if action == "delay" and not config:
            raise ValueError("delay step requires a configuration with 'seconds'")
        if action == "notify" and not config:
            raise ValueError("notify step requires a configuration with user_id, title, message")
        if action == "send_email" and not config:
            raise ValueError("send_email step requires a configuration with to, subject, body")
        if action == "archive_document" and not config:
            raise ValueError("archive_document step requires a configuration with document_id")

        if config and action in _CONFIG_VALIDATORS:
            self.configuration = _CONFIG_VALIDATORS[action](config)

        return self


class WorkflowStepResponse(BaseModel):
    """Response schema for a single workflow step."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    step_number: int
    action: str
    configuration: dict[str, Any] | None = None
    timeout: int | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# Workflow schemas
# ===========================================================================


class WorkflowCreate(BaseModel):
    """
    Request body for POST /api/v1/workflows.

    Steps must form a complete, contiguous 1-based sequence.
    At least 1 step is required; maximum is WORKFLOW_MAX_STEPS.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable workflow name (1–200 chars).",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional description (0–2000 chars).",
    )
    steps: list[WorkflowStepCreate] = Field(
        ...,
        min_length=1,
        description="Ordered workflow steps (at least 1 required).",
    )

    @field_validator("name")
    @classmethod
    def name_not_whitespace(cls, v: str) -> str:
        """Reject blank or whitespace-only names."""
        if not v.strip():
            raise ValueError("Workflow name must not be blank or whitespace-only.")
        return v.strip()

    @model_validator(mode="after")
    def validate_steps(self) -> WorkflowCreate:
        """Validate step count and that step_numbers form a contiguous 1-based sequence."""
        max_steps = settings.WORKFLOW_MAX_STEPS
        if len(self.steps) > max_steps:
            raise ValueError(f"A workflow may not have more than {max_steps} steps.")
        numbers = sorted(s.step_number for s in self.steps)
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(
                "step_number values must form a contiguous 1-based sequence "
                f"(e.g. 1, 2, 3 …). Got: {numbers}"
            )
        return self


class WorkflowUpdate(BaseModel):
    """
    Request body for PUT /api/v1/workflows/{id}.

    All fields are optional. If `steps` is provided, existing steps are
    replaced entirely.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
    )
    is_active: bool | None = Field(
        default=None,
        description="Set to false to disable triggering without deleting.",
    )
    steps: list[WorkflowStepCreate] | None = Field(
        default=None,
        description="If provided, replaces all existing steps.",
    )

    @field_validator("name")
    @classmethod
    def name_not_whitespace(cls, v: str | None) -> str | None:
        """Reject blank or whitespace-only names."""
        if v is not None and not v.strip():
            raise ValueError("Workflow name must not be blank or whitespace-only.")
        return v.strip() if v else v

    @model_validator(mode="after")
    def validate_steps(self) -> WorkflowUpdate:
        """Validate replacement steps if provided."""
        if self.steps is None:
            return self
        max_steps = settings.WORKFLOW_MAX_STEPS
        if len(self.steps) > max_steps:
            raise ValueError(f"A workflow may not have more than {max_steps} steps.")
        if len(self.steps) < 1:
            raise ValueError("At least one step is required.")
        numbers = sorted(s.step_number for s in self.steps)
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("step_number values must form a contiguous 1-based sequence.")
        return self


class WorkflowResponse(BaseModel):
    """
    Response schema for a workflow.

    steps is always populated (eager-loaded by repository).
    creator_name is denormalised for display convenience.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    is_active: bool
    version: int
    created_by: uuid.UUID | None = None
    creator_name: str | None = Field(
        default=None,
        description="Full name of the creating user, if available.",
    )
    steps: list[WorkflowStepResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_creator(cls, workflow: Any) -> WorkflowResponse:
        """Build response from ORM, resolving creator full name."""
        creator_name = None
        if workflow.creator is not None:
            creator_name = f"{workflow.creator.first_name} {workflow.creator.last_name}".strip()
        steps = sorted(workflow.steps, key=lambda s: s.step_number)
        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            is_active=workflow.is_active,
            version=workflow.version,
            created_by=workflow.created_by,
            creator_name=creator_name,
            steps=[WorkflowStepResponse.model_validate(s) for s in steps],
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )


# ===========================================================================
# Execution schemas
# ===========================================================================


class WorkflowRunRequest(BaseModel):
    """Request body for POST /api/v1/workflows/{id}/run."""

    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional runtime context passed to the execution task.",
    )


class WorkflowRunResponse(BaseModel):
    """Response for POST /api/v1/workflows/{id}/run."""

    execution_id: uuid.UUID
    status: str


class WorkflowExecutionResponse(BaseModel):
    """
    Response schema for a single workflow execution record.

    logs contains structured step-level information.
    duration is in seconds (float), or null if not yet completed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    triggered_by: uuid.UUID | None = None
    status: str
    duration: float | None = None
    logs: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# Approval schema
# ===========================================================================


class ApprovalAction(BaseModel):
    """
    Request body for POST /api/v1/executions/{id}/approve.

    action must be 'approve' or 'reject'.
    comment is optional free-text reason.
    """

    action: Literal["approve", "reject"] = Field(
        ...,
        description="'approve' to resume the workflow; 'reject' to terminate it.",
    )
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional reason for the approval decision.",
    )
