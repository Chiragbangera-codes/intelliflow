"""
Automation Rule Engine Service.

Evaluates multi-condition business rules against published platform events
and executes configured automated actions without arbitrary code execution.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationExecution, AutomationRule, AutomationStatus
from app.repositories.automation_repository import AutomationRepository

logger = logging.getLogger(__name__)


def extract_field_value(data: dict[str, Any], field_path: str) -> Any:
    """
    Extract a nested value from a dictionary using dot-notation (e.g. 'payload.user.role').
    """
    parts = field_path.strip().split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def evaluate_condition(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    """
    Safely evaluate a single condition rule against event context data.

    Condition format:
      {"field": "payload.confidentiality", "operator": "equals", "value": "restricted"}
    """
    field = condition.get("field", "")
    operator = condition.get("operator", "equals").lower()
    expected = condition.get("value")

    actual = extract_field_value(context, field)

    try:
        if operator in ("equals", "==", "eq"):
            return actual == expected
        elif operator in ("not_equals", "!=", "neq"):
            return actual != expected
        elif operator in ("contains",):
            if actual is None:
                return False
            return str(expected) in str(actual) if isinstance(actual, str | list | dict) else False
        elif operator in ("not_contains",):
            if actual is None:
                return True
            return (
                str(expected) not in str(actual) if isinstance(actual, str | list | dict) else True
            )
        elif operator in ("in",):
            if not isinstance(expected, list | set | tuple):
                expected = [expected]
            return actual in expected
        elif operator in ("not_in",):
            if not isinstance(expected, list | set | tuple):
                expected = [expected]
            return actual not in expected
        elif operator in ("greater_than", ">", "gt"):
            return float(actual) > float(expected)
        elif operator in ("less_than", "<", "lt"):
            return float(actual) < float(expected)
        elif operator in ("greater_than_or_equal", ">=", "gte"):
            return float(actual) >= float(expected)
        elif operator in ("less_than_or_equal", "<=", "lte"):
            return float(actual) <= float(expected)
        elif operator in ("starts_with",):
            return str(actual).startswith(str(expected)) if actual is not None else False
        elif operator in ("ends_with",):
            return str(actual).endswith(str(expected)) if actual is not None else False
        elif operator in ("is_empty",):
            return not bool(actual)
        elif operator in ("is_not_empty",):
            return bool(actual)
        elif operator in ("is_null", "is_none"):
            return actual is None
        elif operator in ("is_not_null", "is_not_none"):
            return actual is not None
        else:
            logger.warning("Unknown condition operator '%s', evaluated to False", operator)
            return False
    except Exception as exc:
        logger.debug("Condition evaluation error for field '%s': %s", field, exc)
        return False


def evaluate_all_conditions(conditions: list[dict[str, Any]], context: dict[str, Any]) -> bool:
    """
    Evaluate a list of conditions (all must evaluate to True - logical AND).
    """
    if not conditions:
        return True  # Empty conditions mean unconditional trigger
    return all(evaluate_condition(cond, context) for cond in conditions)


class AutomationService:
    """Service for managing and executing automation rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AutomationRepository(session)

    async def create_rule(
        self,
        name: str,
        trigger_event: str,
        conditions: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        description: str | None = None,
        is_active: bool = True,
        created_by: uuid.UUID | None = None,
    ) -> AutomationRule:
        """Create a new automation rule."""
        rule = await self.repo.create_rule(
            name=name.strip(),
            trigger_event=trigger_event.strip(),
            conditions=conditions or [],
            actions=actions or [],
            description=description.strip() if description else None,
            is_active=is_active,
            created_by=created_by,
        )
        await self.session.commit()
        return rule

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> AutomationRule | None:
        """Fetch an automation rule by ID."""
        return await self.repo.get_rule_by_id(rule_id)

    async def list_rules(
        self,
        page: int = 1,
        page_size: int = 20,
        trigger_event: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[AutomationRule], int]:
        """List automation rules."""
        return await self.repo.list_rules(
            page=page, page_size=page_size, trigger_event=trigger_event, is_active=is_active
        )

    async def update_rule(
        self,
        rule_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        trigger_event: str | None = None,
        conditions: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        is_active: bool | None = None,
    ) -> AutomationRule | None:
        """Update an automation rule."""
        updated = await self.repo.update_rule(
            rule_id=rule_id,
            name=name.strip() if name is not None else None,
            description=description.strip() if description is not None else None,
            trigger_event=trigger_event.strip() if trigger_event is not None else None,
            conditions=conditions,
            actions=actions,
            is_active=is_active,
        )
        if updated:
            await self.session.commit()
        return updated

    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        """Delete an automation rule."""
        deleted = await self.repo.delete_rule(rule_id)
        if deleted:
            await self.session.commit()
        return deleted

    async def execute_action(
        self, action: dict[str, Any], event_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Execute a single automation action safely.

        Supported actions:
          - send_notification
          - send_webhook
          - send_integration
          - trigger_workflow
          - create_report
        """
        action_type = action.get("type", "")
        config = action.get("config", {})

        try:
            if action_type == "send_notification":
                from app.models.notification import NotificationChannel, NotificationPriority
                from app.repositories.notification_repository import NotificationRepository

                user_id_str = config.get("user_id") or event_context.get("actor_id")
                if not user_id_str:
                    return {"type": action_type, "success": False, "error": "Missing user_id"}

                notif_repo = NotificationRepository(self.session)
                await notif_repo.create(
                    user_id=uuid.UUID(str(user_id_str)),
                    title=config.get("title") or "Automated Notification",
                    message=config.get("message")
                    or f"Event {event_context.get('event_type')} triggered.",
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.MEDIUM,
                )
                return {"type": action_type, "success": True, "target_user": user_id_str}

            elif action_type == "send_webhook":
                from app.services.webhook_service import WebhookService

                webhook_id_str = config.get("webhook_id")
                if not webhook_id_str:
                    return {"type": action_type, "success": False, "error": "Missing webhook_id"}

                wh_service = WebhookService(self.session)
                webhook = await wh_service.get_by_id(uuid.UUID(str(webhook_id_str)))
                if not webhook:
                    return {"type": action_type, "success": False, "error": "Webhook not found"}

                delivery = await wh_service.execute_delivery(
                    webhook=webhook,
                    event_type=event_context.get("event_type", "automation.event"),
                    payload=event_context.get("payload", {}),
                    event_id=uuid.UUID(str(event_context["event_id"]))
                    if event_context.get("event_id")
                    else None,
                    correlation_id=event_context.get("correlation_id"),
                )
                return {
                    "type": action_type,
                    "success": delivery.status.value == "success",
                    "delivery_id": str(delivery.id),
                }

            elif action_type == "send_integration":
                from app.services.integration_service import IntegrationService

                integration_id_str = config.get("integration_id")
                if not integration_id_str:
                    return {
                        "type": action_type,
                        "success": False,
                        "error": "Missing integration_id",
                    }

                integ_service = IntegrationService(self.session)
                res = await integ_service.dispatch(
                    integration_id=uuid.UUID(str(integration_id_str)),
                    payload=event_context.get("payload", {}),
                )
                return {"type": action_type, "success": res.get("success", False), "result": res}

            elif action_type == "trigger_workflow":
                from app.repositories.workflow_repository import WorkflowRepository
                from app.services.workflow_service import WorkflowService

                workflow_id_str = config.get("workflow_id")
                if not workflow_id_str:
                    return {"type": action_type, "success": False, "error": "Missing workflow_id"}

                wf_repo = WorkflowRepository(self.session)
                wf_service = WorkflowService(self.session, wf_repo)
                exec_record = await wf_service.trigger_workflow(
                    workflow_id=uuid.UUID(str(workflow_id_str)),
                    user_id=uuid.UUID(str(event_context["actor_id"]))
                    if event_context.get("actor_id")
                    else uuid.UUID("00000000-0000-4000-8000-000000000001"),
                    context_data=event_context.get("payload", {}),
                )
                return {"type": action_type, "success": True, "execution_id": str(exec_record.id)}

            elif action_type == "create_report":
                from app.repositories.report_repository import ReportRepository
                from app.services.report_service import ReportService

                report_repo = ReportRepository(self.session)
                report_service = ReportService(self.session, report_repo)
                rep = await report_service.request_report(
                    user_id=uuid.UUID(str(event_context["actor_id"]))
                    if event_context.get("actor_id")
                    else uuid.UUID("00000000-0000-4000-8000-000000000001"),
                    title=config.get("title") or "Automated System Report",
                    report_type=config.get("report_type") or "analytics",
                    format=config.get("format") or "csv",
                    parameters=config.get("parameters") or {},
                )
                return {"type": action_type, "success": True, "report_id": str(rep.id)}

            else:
                return {
                    "type": action_type,
                    "success": False,
                    "error": f"Unsupported action type: {action_type}",
                }

        except Exception as exc:
            logger.warning("Action execution '%s' failed: %s", action_type, exc)
            return {"type": action_type, "success": False, "error": str(exc)}

    async def evaluate_and_run_rule(
        self,
        rule: AutomationRule,
        event_context: dict[str, Any],
        dry_run: bool = False,
    ) -> AutomationExecution | dict[str, Any]:
        """
        Evaluate rule conditions and execute actions if conditions pass.
        """
        start_time = time.monotonic()
        conditions_met = evaluate_all_conditions(rule.conditions or [], event_context)

        if not conditions_met:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            result = {
                "rule_id": str(rule.id),
                "matched": False,
                "conditions_met": False,
                "duration_ms": duration_ms,
            }
            return result

        action_results: list[dict[str, Any]] = []
        has_failure = False
        has_success = False

        if not dry_run:
            for action in rule.actions or []:
                res = await self.execute_action(action, event_context)
                action_results.append(res)
                if res.get("success"):
                    has_success = True
                else:
                    has_failure = True

        duration_ms = int((time.monotonic() - start_time) * 1000)
        status = (
            AutomationStatus.PARTIAL
            if (has_success and has_failure)
            else (AutomationStatus.FAILURE if has_failure else AutomationStatus.SUCCESS)
        )

        if dry_run:
            return {
                "rule_id": str(rule.id),
                "matched": True,
                "conditions_met": True,
                "dry_run": True,
                "actions_to_execute": len(rule.actions or []),
                "duration_ms": duration_ms,
            }

        execution = await self.repo.create_execution(
            rule_id=rule.id,
            event_type=event_context.get("event_type", rule.trigger_event),
            event_id=uuid.UUID(str(event_context["event_id"]))
            if event_context.get("event_id")
            else None,
            status=status,
            action_results=action_results,
            execution_time_ms=duration_ms,
        )
        await self.session.commit()
        return execution

    async def list_executions(
        self,
        rule_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        status: AutomationStatus | None = None,
    ) -> tuple[list[AutomationExecution], int]:
        """Query execution history."""
        return await self.repo.list_executions(
            rule_id=rule_id, page=page, page_size=page_size, status=status
        )
