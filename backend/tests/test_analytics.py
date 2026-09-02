"""
Tests for Phase 9 Analytics API endpoints.

Tests cover:
  - RBAC enforcement (401 unauthenticated, 403 wrong role)
  - Successful responses for all 6 analytics endpoints
  - Empty-database behaviour (responses always return valid schema)

All tests use the in-memory SQLite test database defined in conftest.py.
The analytics queries that use PostgreSQL-specific functions (date_trunc,
extract) fall back gracefully to empty results under SQLite — the response
schema is always valid regardless.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_headers(user: User, role_override: str | None = None) -> dict[str, str]:
    role = role_override or (user.role.name if user.role else "employee")
    token = create_access_token(subject=str(user.id), role=role)
    return {"Authorization": f"Bearer {token}"}


ANALYTICS_ENDPOINTS = [
    "/api/v1/analytics/kpi",
    "/api/v1/analytics/revenue",
    "/api/v1/analytics/departments",
    "/api/v1/analytics/employees",
    "/api/v1/analytics/documents",
    "/api/v1/analytics/workflows",
    "/api/v1/analytics/ai",
]


# ===========================================================================
# Authentication tests
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ANALYTICS_ENDPOINTS)
async def test_analytics_requires_auth(
    async_client: AsyncClient,
    endpoint: str,
) -> None:
    """Unauthenticated requests must be rejected with 401."""
    resp = await async_client.get(endpoint)
    assert resp.status_code == 401, f"{endpoint} should require auth"


# ===========================================================================
# RBAC tests — employee role must be rejected
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ANALYTICS_ENDPOINTS)
async def test_analytics_forbidden_for_employee(
    async_client: AsyncClient,
    test_user: User,
    endpoint: str,
) -> None:
    """Employee role must receive 403 on all analytics endpoints."""
    headers = _make_headers(test_user, role_override="employee")
    resp = await async_client.get(endpoint, headers=headers)
    assert resp.status_code == 403, f"{endpoint} should be forbidden for employee"


# ===========================================================================
# Success tests — admin role can access all endpoints
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ANALYTICS_ENDPOINTS)
async def test_analytics_accessible_by_admin(
    async_client: AsyncClient,
    admin_user: User,
    endpoint: str,
) -> None:
    """Admin role must receive 200 on all analytics endpoints."""
    headers = _make_headers(admin_user)
    resp = await async_client.get(endpoint, headers=headers)
    assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["success"] is True
    assert "data" in body


# ===========================================================================
# Content structure tests
# ===========================================================================


@pytest.mark.asyncio
async def test_kpi_summary_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """KPI summary response must contain required numeric fields."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/kpi", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    required_fields = [
        "total_employees",
        "total_documents",
        "active_workflows",
        "total_ai_conversations",
        "completed_workflow_executions",
        "total_predictions_run",
        "total_reports_generated",
    ]
    for field in required_fields:
        assert field in data, f"KPI response missing '{field}'"
        assert isinstance(data[field], int), f"'{field}' must be int"


@pytest.mark.asyncio
async def test_revenue_analytics_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Revenue analytics must include 12 monthly data points."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/revenue", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "year" in data
    assert "data" in data
    assert isinstance(data["data"], list)
    # 12 months always returned (zeroed for empty months)
    assert len(data["data"]) == 12


@pytest.mark.asyncio
async def test_department_analytics_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Department analytics must include data list and total_departments count."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/departments", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "data" in data
    assert "total_departments" in data
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_employee_analytics_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Employee analytics must include total, role_distribution, monthly_headcount."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/employees", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total" in data
    assert "role_distribution" in data
    assert "monthly_headcount" in data


@pytest.mark.asyncio
async def test_document_analytics_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Document analytics must include upload totals and status breakdowns."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/documents", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_uploads" in data
    assert "by_status" in data
    assert "monthly_uploads" in data


@pytest.mark.asyncio
async def test_workflow_analytics_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Workflow analytics must include execution counts and status breakdown."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/workflows", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_executions" in data
    assert "by_status" in data
    assert "avg_duration_seconds" in data


@pytest.mark.asyncio
async def test_ai_usage_analytics_structure(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """AI usage analytics must include conversation counts and token stats."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/ai", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_conversations" in data
    assert "avg_response_time_seconds" in data
    assert "monthly_conversations" in data


@pytest.mark.asyncio
async def test_revenue_analytics_year_param(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Revenue analytics should accept explicit year query parameter."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/revenue?year=2025", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["year"] == 2025


@pytest.mark.asyncio
async def test_revenue_analytics_invalid_year(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Invalid year values must be rejected with 422."""
    headers = _make_headers(admin_user)
    resp = await async_client.get("/api/v1/analytics/revenue?year=1800", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_hr_can_access_analytics(
    async_client: AsyncClient,
    hr_user: User,
) -> None:
    """HR role must be able to access analytics endpoints."""
    headers = _make_headers(hr_user)
    resp = await async_client.get("/api/v1/analytics/kpi", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_manager_can_access_analytics(
    async_client: AsyncClient,
    manager_user: User,
) -> None:
    """Manager role must be able to access analytics endpoints."""
    headers = _make_headers(manager_user)
    resp = await async_client.get("/api/v1/analytics/kpi", headers=headers)
    assert resp.status_code == 200
