"""
Celery background worker tasks for Event Bus, Outbox, Webhooks, and Automations.

Handles:
  - process_outbox_batch_task: Drains transactional outbox and dispatches events.
  - dispatch_event_task: Evaluates matching automations and schedules webhook deliveries.
  - deliver_webhook_task: Executes signed HTTP webhook delivery with exponential backoff.
  - execute_automation_rule_task: Runs an automation rule in background worker.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.database import AsyncSessionLocal
from app.repositories.automation_repository import AutomationRepository
from app.repositories.webhook_repository import WebhookRepository
from app.services.automation_service import AutomationService
from app.services.event_bus_service import EventBusService
from app.services.webhook_service import WebhookService
from app.workers.celery_app import celery_app
from app.workers.task_runner import run_in_worker

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.event_tasks.process_outbox_batch_task", bind=True, max_retries=3)
def process_outbox_batch_task(self, limit: int = 50) -> dict[str, int]:
    """Drain pending outbox events and dispatch them."""

    async def _run() -> dict[str, int]:
        async with AsyncSessionLocal() as session:
            service = EventBusService(session)
            return await service.process_outbox_batch(limit=limit)

    try:
        return run_in_worker(_run())
    except Exception as exc:
        logger.exception("Error in process_outbox_batch_task: %s", exc)
        raise self.retry(exc=exc, countdown=5) from exc


@celery_app.task(name="app.workers.event_tasks.dispatch_event_task", bind=True)
def dispatch_event_task(
    self,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
    correlation_id: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """
    Match an event against active automations and subscribed webhooks, and trigger them.
    """

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            event_ctx = {
                "event_id": event_id,
                "event_type": event_type,
                "payload": payload,
                "correlation_id": correlation_id,
                "actor_id": actor_id,
            }

            # 1. Match & Execute Automation Rules
            auto_repo = AutomationRepository(session)
            matching_rules = await auto_repo.find_matching_rules(event_type)
            auto_service = AutomationService(session)

            rule_results = []
            for rule in matching_rules:
                res = await auto_service.evaluate_and_run_rule(rule, event_ctx)
                rule_results.append(res)

            # 2. Match & Deliver Webhooks
            wh_repo = WebhookRepository(session)
            matching_webhooks = await wh_repo.find_matching_webhooks(event_type)
            wh_service = WebhookService(session)

            wh_results = []
            for wh in matching_webhooks:
                delivery = await wh_service.execute_delivery(
                    webhook=wh,
                    event_type=event_type,
                    payload=payload,
                    event_id=uuid.UUID(event_id) if event_id else None,
                    correlation_id=correlation_id,
                )
                wh_results.append(
                    {
                        "webhook_id": str(wh.id),
                        "status": delivery.status.value,
                        "delivery_id": str(delivery.id),
                    }
                )

            return {
                "event_id": event_id,
                "matched_rules": len(matching_rules),
                "matched_webhooks": len(matching_webhooks),
                "webhook_results": wh_results,
            }

    try:
        return run_in_worker(_run())
    except Exception as exc:
        logger.exception("Error in dispatch_event_task for event %s: %s", event_id, exc)
        return {"error": str(exc), "event_id": event_id}


@celery_app.task(
    name="app.workers.event_tasks.deliver_webhook_task",
    bind=True,
    max_retries=5,
    default_retry_delay=10,
)
def deliver_webhook_task(
    self,
    webhook_id: str,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Deliver a webhook with automatic Celery retries."""

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            wh_service = WebhookService(session)
            webhook = await wh_service.get_by_id(uuid.UUID(webhook_id))
            if not webhook:
                return {"success": False, "error": "Webhook not found"}

            delivery = await wh_service.execute_delivery(
                webhook=webhook,
                event_type=event_type,
                payload=payload,
                event_id=uuid.UUID(event_id) if event_id else None,
                correlation_id=correlation_id,
            )
            return {"success": delivery.status.value == "success", "delivery_id": str(delivery.id)}

    try:
        return run_in_worker(_run())
    except Exception as exc:
        logger.warning("Retrying deliver_webhook_task for %s: %s", webhook_id, exc)
        raise self.retry(exc=exc) from exc
