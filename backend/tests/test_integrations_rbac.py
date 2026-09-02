"""
RBAC permission tests for Milestone 13 endpoints (Integrations, Webhooks, Automations, Events).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestIntegrationsRBAC:
    """Verify role-based access control across all Milestone 13 endpoints."""

    async def test_employee_forbidden_from_integrations(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Verify employee role receives 403 on all Milestone 13 routers."""
        # Integrations
        res = await async_client.get("/api/v1/integrations", headers=auth_headers)
        assert res.status_code == 403

        # Webhooks
        res = await async_client.get("/api/v1/webhooks", headers=auth_headers)
        assert res.status_code == 403

        # Automations
        res = await async_client.get("/api/v1/automations", headers=auth_headers)
        assert res.status_code == 403

        # Events
        res = await async_client.get("/api/v1/events", headers=auth_headers)
        assert res.status_code == 403

    async def test_unauthenticated_rejected(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Verify unauthenticated requests receive 401."""
        res = await async_client.get("/api/v1/integrations")
        assert res.status_code == 401

        res = await async_client.get("/api/v1/webhooks")
        assert res.status_code == 401

        res = await async_client.get("/api/v1/automations")
        assert res.status_code == 401

        res = await async_client.get("/api/v1/events")
        assert res.status_code == 401

    async def test_admin_allowed_on_all_milestone13_endpoints(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """Verify admin role has full access."""
        res = await async_client.get("/api/v1/integrations", headers=admin_headers)
        assert res.status_code == 200

        res = await async_client.get("/api/v1/webhooks", headers=admin_headers)
        assert res.status_code == 200

        res = await async_client.get("/api/v1/automations", headers=admin_headers)
        assert res.status_code == 200

        res = await async_client.get("/api/v1/events", headers=admin_headers)
        assert res.status_code == 200

        res = await async_client.get("/api/v1/events/outbox/stats", headers=admin_headers)
        assert res.status_code == 200
