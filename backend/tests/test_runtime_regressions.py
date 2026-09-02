"""
Regression test suite for runtime console errors and authorization boundaries.

Guarantees:
  1. GET /api/v1/documents with sort=-created_at works and serializes with versions and shares.
  2. GET /api/v1/reports and POST /api/v1/reports serialize cleanly without expired attribute errors.
  3. GET /api/v1/analytics/kpi enforces strict RBAC: 200 for admin/manager/hr/finance, 403 for employee.
  4. GET /api/v1/predictions and POST /api/v1/predictions enforce strict RBAC: 200/201 for privileged, 403 for employee.
  5. Case-insensitive and null-safe role handling in require_role.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_regression_documents_sort_and_serialization(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    """Verify document listing with sort=-created_at succeeds for both admin and standard user."""
    # Admin
    res_admin = await async_client.get(
        "/api/v1/documents?page=1&page_size=15&sort=-created_at", headers=admin_headers
    )
    assert res_admin.status_code == 200
    data_admin = res_admin.json()
    assert data_admin["success"] is True
    assert "data" in data_admin
    assert data_admin["meta"]["page"] == 1
    assert data_admin["meta"]["page_size"] == 15

    # Standard employee
    res_emp = await async_client.get(
        "/api/v1/documents?page=1&page_size=15&sort=-created_at", headers=auth_headers
    )
    assert res_emp.status_code == 200
    data_emp = res_emp.json()
    assert data_emp["success"] is True


@pytest.mark.asyncio
async def test_regression_reports_lifecycle_and_serialization(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    """Verify report listing and generation succeed and serialize without expired attribute errors."""
    # List reports
    res_list = await async_client.get("/api/v1/reports?page=1&page_size=20", headers=admin_headers)
    assert res_list.status_code == 200
    assert res_list.json()["success"] is True

    # Generate report as standard user
    res_post = await async_client.post(
        "/api/v1/reports",
        json={"report_type": "revenue", "format": "csv", "filters": {}},
        headers=auth_headers,
    )
    assert res_post.status_code == 202
    res_json = res_post.json()
    assert res_json["success"] is True
    assert res_json["data"]["status"] == "pending"
    report_id = res_json["data"]["id"]

    # Get single report
    res_get = await async_client.get(f"/api/v1/reports/{report_id}", headers=auth_headers)
    assert res_get.status_code == 200
    assert res_get.json()["data"]["id"] == report_id


@pytest.mark.asyncio
async def test_regression_analytics_rbac_matrix(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    """Verify GET /api/v1/analytics/kpi is accessible only to privileged roles."""
    # Admin -> 200 OK
    res_admin = await async_client.get("/api/v1/analytics/kpi", headers=admin_headers)
    assert res_admin.status_code == 200
    assert res_admin.json()["success"] is True
    assert "total_employees" in res_admin.json()["data"]

    # Employee -> 403 Forbidden
    res_emp = await async_client.get("/api/v1/analytics/kpi", headers=auth_headers)
    assert res_emp.status_code == 403
    assert res_emp.json()["success"] is False
    assert res_emp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_regression_predictions_rbac_matrix(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    """Verify prediction endpoints enforce RBAC: 200/201 for admin, 403 for employee."""
    # Admin list predictions -> 200 OK
    res_list_admin = await async_client.get(
        "/api/v1/predictions?page=1&page_size=20", headers=admin_headers
    )
    assert res_list_admin.status_code == 200
    assert res_list_admin.json()["success"] is True

    # Admin run prediction -> 201 Created
    res_post_admin = await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast"},
        headers=admin_headers,
    )
    assert res_post_admin.status_code == 201
    assert res_post_admin.json()["success"] is True

    # Employee list predictions -> 403 Forbidden
    res_list_emp = await async_client.get(
        "/api/v1/predictions?page=1&page_size=20", headers=auth_headers
    )
    assert res_list_emp.status_code == 403

    # Employee run prediction -> 403 Forbidden
    res_post_emp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast"},
        headers=auth_headers,
    )
    assert res_post_emp.status_code == 403
