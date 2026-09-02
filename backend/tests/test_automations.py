"""
Tests for Automation Rule Engine: condition parser, action executor, dry-run testing, and execution tracking.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.automation_service import (
    evaluate_all_conditions,
    evaluate_condition,
)


class TestAutomations:
    """Test Automation rule condition evaluation and execution."""

    @pytest.mark.parametrize(
        ("condition", "context", "expected"),
        [
            # equals
            (
                {"field": "payload.status", "operator": "equals", "value": "approved"},
                {"payload": {"status": "approved"}},
                True,
            ),
            (
                {"field": "payload.status", "operator": "equals", "value": "rejected"},
                {"payload": {"status": "approved"}},
                False,
            ),
            # contains
            (
                {"field": "payload.title", "operator": "contains", "value": "Confidential"},
                {"payload": {"title": "2026 Confidential Strategy"}},
                True,
            ),
            (
                {"field": "payload.title", "operator": "contains", "value": "Secret"},
                {"payload": {"title": "2026 Public Report"}},
                False,
            ),
            # in
            (
                {"field": "payload.priority", "operator": "in", "value": ["high", "critical"]},
                {"payload": {"priority": "critical"}},
                True,
            ),
            (
                {"field": "payload.priority", "operator": "in", "value": ["high", "critical"]},
                {"payload": {"priority": "low"}},
                False,
            ),
            # numeric comparisons
            (
                {"field": "payload.amount", "operator": "greater_than", "value": 1000},
                {"payload": {"amount": 5000}},
                True,
            ),
            (
                {"field": "payload.amount", "operator": "greater_than", "value": 10000},
                {"payload": {"amount": 5000}},
                False,
            ),
            (
                {"field": "payload.amount", "operator": "less_than", "value": 500},
                {"payload": {"amount": 100}},
                True,
            ),
            # null checks
            (
                {"field": "payload.error", "operator": "is_null", "value": None},
                {"payload": {}},
                True,
            ),
            (
                {"field": "payload.error", "operator": "is_not_null", "value": None},
                {"payload": {"error": "Failed"}},
                True,
            ),
        ],
    )
    def test_evaluate_condition_operators(
        self,
        condition: dict,
        context: dict,
        expected: bool,
    ) -> None:
        """Verify AST condition evaluator without unsafe eval()."""
        assert evaluate_condition(condition, context) == expected

    def test_evaluate_all_conditions(self) -> None:
        """Verify multiple conditions AND conjunction."""
        conditions = [
            {"field": "payload.department", "operator": "equals", "value": "Finance"},
            {"field": "payload.amount", "operator": ">=", "value": 5000},
        ]
        assert (
            evaluate_all_conditions(
                conditions, {"payload": {"department": "Finance", "amount": 10000}}
            )
            is True
        )
        assert (
            evaluate_all_conditions(conditions, {"payload": {"department": "HR", "amount": 10000}})
            is False
        )

    @pytest.mark.asyncio
    async def test_automation_rule_crud_and_dry_run(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify POST /api/v1/automations and POST /api/v1/automations/{id}/test."""
        create_payload = {
            "name": "Notify On Large Expense",
            "trigger_event": "expense.submitted",
            "conditions": [
                {"field": "payload.amount", "operator": ">=", "value": 10000},
            ],
            "actions": [
                {
                    "type": "send_notification",
                    "config": {
                        "title": "High Value Expense Submitted",
                        "message": "An expense exceeding $10k was submitted.",
                    },
                },
            ],
        }

        res = await async_client.post(
            "/api/v1/automations",
            json=create_payload,
            headers=admin_headers,
        )
        assert res.status_code == 201
        rule = res.json()
        rule_id = rule["id"]

        # Dry run matching
        match_test_res = await async_client.post(
            f"/api/v1/automations/{rule_id}/test",
            json={"event_context": {"payload": {"amount": 25000}}},
            headers=admin_headers,
        )
        assert match_test_res.status_code == 200
        match_data = match_test_res.json()
        assert match_data["matched"] is True
        assert match_data["conditions_met"] is True
        assert match_data["actions_to_execute"] == 1

        # Dry run non-matching
        no_match_test_res = await async_client.post(
            f"/api/v1/automations/{rule_id}/test",
            json={"event_context": {"payload": {"amount": 500}}},
            headers=admin_headers,
        )
        assert no_match_test_res.status_code == 200
        no_match_data = no_match_test_res.json()
        assert no_match_data["matched"] is False
        assert no_match_data["conditions_met"] is False
        assert no_match_data["actions_to_execute"] == 0
