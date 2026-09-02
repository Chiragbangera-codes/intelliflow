"""
Automation repository.

Provides database operations for automation rules and execution audit logs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationExecution, AutomationRule, AutomationStatus


class AutomationRepository:
    """Repository for Automation Rules and Executions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        """Create and persist a new automation rule."""
        rule = AutomationRule(
            name=name,
            trigger_event=trigger_event,
            conditions=conditions,
            actions=actions,
            description=description,
            is_active=is_active,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> AutomationRule | None:
        """Get an automation rule by ID."""
        stmt = select(AutomationRule).where(AutomationRule.id == rule_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_rules(
        self,
        page: int = 1,
        page_size: int = 20,
        trigger_event: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[AutomationRule], int]:
        """List automation rules with filtering and pagination."""
        stmt = select(AutomationRule)
        count_stmt = select(func.count(AutomationRule.id))

        if trigger_event:
            stmt = stmt.where(AutomationRule.trigger_event == trigger_event)
            count_stmt = count_stmt.where(AutomationRule.trigger_event == trigger_event)
        if is_active is not None:
            stmt = stmt.where(AutomationRule.is_active == is_active)
            count_stmt = count_stmt.where(AutomationRule.is_active == is_active)

        total_res = await self.session.execute(count_stmt)
        total_items = total_res.scalar() or 0

        stmt = (
            stmt.order_by(AutomationRule.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items_res = await self.session.execute(stmt)
        rules = list(items_res.scalars().all())

        return rules, total_items

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
        """Update automation rule fields."""
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return None

        if name is not None:
            rule.name = name
        if description is not None:
            rule.description = description
        if trigger_event is not None:
            rule.trigger_event = trigger_event
        if conditions is not None:
            rule.conditions = conditions
        if actions is not None:
            rule.actions = actions
        if is_active is not None:
            rule.is_active = is_active

        rule.updated_at = datetime.now(UTC)
        await self.session.flush()
        return rule

    async def delete_rule(self, rule_id: uuid.UUID) -> bool:
        """Delete an automation rule."""
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return False
        await self.session.delete(rule)
        await self.session.flush()
        return True

    async def find_matching_rules(self, event_type: str) -> list[AutomationRule]:
        """Find active rules matching the event type or wildcard '*'."""
        stmt = select(AutomationRule).where(
            (AutomationRule.is_active.is_(True))
            & ((AutomationRule.trigger_event == event_type) | (AutomationRule.trigger_event == "*"))
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------------------
    # Executions
    # -------------------------------------------------------------------------
    async def create_execution(
        self,
        rule_id: uuid.UUID,
        event_type: str,
        status: AutomationStatus,
        action_results: list[dict[str, Any]],
        event_id: uuid.UUID | None = None,
        error_message: str | None = None,
        execution_time_ms: int | None = None,
    ) -> AutomationExecution:
        """Record an automation rule execution."""
        execution = AutomationExecution(
            rule_id=rule_id,
            event_id=event_id,
            event_type=event_type,
            status=status,
            action_results=action_results,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            created_at=datetime.now(UTC),
        )
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def list_executions(
        self,
        rule_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        status: AutomationStatus | None = None,
    ) -> tuple[list[AutomationExecution], int]:
        """List execution logs with optional filtering and pagination."""
        stmt = select(AutomationExecution)
        count_stmt = select(func.count(AutomationExecution.id))

        if rule_id is not None:
            stmt = stmt.where(AutomationExecution.rule_id == rule_id)
            count_stmt = count_stmt.where(AutomationExecution.rule_id == rule_id)
        if status is not None:
            stmt = stmt.where(AutomationExecution.status == status)
            count_stmt = count_stmt.where(AutomationExecution.status == status)

        total_res = await self.session.execute(count_stmt)
        total_items = total_res.scalar() or 0

        stmt = (
            stmt.order_by(AutomationExecution.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items_res = await self.session.execute(stmt)
        executions = list(items_res.scalars().all())

        return executions, total_items
