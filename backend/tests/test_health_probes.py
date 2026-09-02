"""
Unit and integration tests for Multi-Tier Health System (Milestone 12).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoints(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    """Test /health, /health/live, /health/ready, and /health/details."""
    # 1. Root liveness probe
    res = await async_client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 2. API v1 liveness probe
    res_live = await async_client.get("/api/v1/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "ok"

    # 3. Readiness probe
    res_ready = await async_client.get("/api/v1/health/ready")
    assert res_ready.status_code in (200, 503)
    data = res_ready.json()
    assert "status" in data
    assert "dependencies" in data
    assert "database" in data["dependencies"]

    # 4. Deep diagnostics probe (Admin only)
    res_diag = await async_client.get("/api/v1/health/details", headers=admin_headers)
    assert res_diag.status_code == 200
    diag_data = res_diag.json()
    assert diag_data["success"] is True
    assert "uptime_seconds" in diag_data["data"]
    assert "memory_usage_mb" in diag_data["data"]

    # 5. Non-admin is rejected from diagnostics
    res_diag_emp = await async_client.get("/api/v1/health/details", headers=auth_headers)
    assert res_diag_emp.status_code == 403


@pytest.mark.asyncio
async def test_admin_system_metrics_endpoint(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    """Test /api/v1/admin/system/metrics endpoint."""
    res = await async_client.get("/api/v1/admin/system/metrics", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "data" in body
    d = body["data"]
    assert "database_status" in d
    assert "redis_status" in d
    assert "total_users_count" in d
    assert "total_documents_count" in d
    assert "total_workflows_count" in d

    # Non-admin rejected
    res_emp = await async_client.get("/api/v1/admin/system/metrics", headers=auth_headers)
    assert res_emp.status_code == 403
