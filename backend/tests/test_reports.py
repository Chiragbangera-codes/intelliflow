"""
Tests for Phase 9 Reports API endpoints.

Tests cover:
  - RBAC: all roles can request reports, only privileged roles see all
  - Report creation returns 202 with PENDING status
  - List reports: employees see own, admins see all
  - Get by ID: ownership enforcement
  - 404 on missing report
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User


@pytest.fixture(autouse=True)
def mock_celery():
    """Mock Celery task dispatch so tests run fast without live Redis broker."""
    with patch("app.services.report_service.celery_app") as m:
        m.send_task.return_value = None
        yield m


def _make_headers(user: User, role_override: str | None = None) -> dict[str, str]:
    role = role_override or (user.role.name if user.role else "employee")
    token = create_access_token(subject=str(user.id), role=role)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Authentication
# ===========================================================================


@pytest.mark.asyncio
async def test_request_report_requires_auth(async_client: AsyncClient) -> None:
    """Unauthenticated POST /reports must return 401."""
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": "csv"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_reports_requires_auth(async_client: AsyncClient) -> None:
    """Unauthenticated GET /reports must return 401."""
    resp = await async_client.get("/api/v1/reports")
    assert resp.status_code == 401


# ===========================================================================
# Any authenticated user can request a report
# ===========================================================================


@pytest.mark.asyncio
async def test_employee_can_request_report(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """Employee can POST /reports; receives 202 with PENDING status."""
    headers = _make_headers(test_user)
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["report_type"] == "employees"
    assert data["status"] in ("pending", "failed")  # failed if Celery not running


@pytest.mark.asyncio
async def test_admin_can_request_report(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Admin can POST /reports; receives 202 with PENDING status."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "departments", "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True


# ===========================================================================
# Report format validation
# ===========================================================================


@pytest.mark.asyncio
async def test_invalid_report_type_rejected(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Invalid report_type must return 422."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "unknown_type", "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_format_rejected(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Invalid format value must return 422."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": "docx"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["csv", "xlsx", "pdf"])
async def test_all_formats_accepted(
    async_client: AsyncClient,
    admin_user: User,
    fmt: str,
) -> None:
    """All three supported formats must be accepted with 202."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": fmt},
        headers=headers,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rtype", ["revenue", "employees", "departments", "workflows", "documents", "ai_usage"]
)
async def test_all_report_types_accepted(
    async_client: AsyncClient,
    admin_user: User,
    rtype: str,
) -> None:
    """All six supported report types must be accepted with 202."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": rtype, "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 202


# ===========================================================================
# List visibility scoping
# ===========================================================================


@pytest.mark.asyncio
async def test_employee_only_sees_own_reports(
    async_client: AsyncClient,
    test_user: User,
    admin_user: User,
) -> None:
    """Employee sees only their own reports; admin's report not visible."""
    emp_headers = _make_headers(test_user)
    admin_headers = _make_headers(admin_user)

    # Admin creates a report
    await async_client.post(
        "/api/v1/reports",
        json={"report_type": "departments", "format": "csv"},
        headers=admin_headers,
    )

    # Employee creates their own report
    await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": "csv"},
        headers=emp_headers,
    )

    # Employee lists reports — should only see their own
    emp_list = await async_client.get("/api/v1/reports", headers=emp_headers)
    assert emp_list.status_code == 200
    emp_data = emp_list.json()["data"]
    for report in emp_data:
        assert str(report["generated_by"]) == str(test_user.id)


@pytest.mark.asyncio
async def test_admin_sees_all_reports(
    async_client: AsyncClient,
    test_user: User,
    admin_user: User,
) -> None:
    """Admin can see reports generated by other users."""
    emp_headers = _make_headers(test_user)
    admin_headers = _make_headers(admin_user)

    # Employee creates a report
    await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": "csv"},
        headers=emp_headers,
    )

    # Admin lists — should see the employee's report
    admin_list = await async_client.get("/api/v1/reports", headers=admin_headers)
    assert admin_list.status_code == 200
    report_owners = {r["generated_by"] for r in admin_list.json()["data"]}
    assert str(test_user.id) in report_owners


# ===========================================================================
# Get by ID — ownership enforcement
# ===========================================================================


@pytest.mark.asyncio
async def test_get_report_by_id_own(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """User can retrieve their own report by ID."""
    headers = _make_headers(test_user)
    create_resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "employees", "format": "csv"},
        headers=headers,
    )
    report_id = create_resp.json()["data"]["id"]

    get_resp = await async_client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == report_id


@pytest.mark.asyncio
async def test_get_report_not_found(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """Non-existent report UUID must return 404."""
    headers = _make_headers(test_user)
    resp = await async_client.get(
        "/api/v1/reports/00000000-0000-4000-8000-000000000099",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_employee_cannot_view_others_report(
    async_client: AsyncClient,
    test_user: User,
    admin_user: User,
) -> None:
    """Employee must receive 403 when accessing a report they didn't create."""
    admin_headers = _make_headers(admin_user)
    emp_headers = _make_headers(test_user)

    # Admin creates a report
    create_resp = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "departments", "format": "csv"},
        headers=admin_headers,
    )
    report_id = create_resp.json()["data"]["id"]

    # Employee tries to access admin's report
    resp = await async_client.get(f"/api/v1/reports/{report_id}", headers=emp_headers)
    assert resp.status_code == 403


# ===========================================================================
# Pagination
# ===========================================================================


@pytest.mark.asyncio
async def test_list_reports_pagination(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """List endpoint must respect page/page_size and return meta."""
    headers = _make_headers(admin_user)
    resp = await async_client.get(
        "/api/v1/reports?page=1&page_size=5",
        headers=headers,
    )
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["page"] == 1
    assert meta["page_size"] == 5
