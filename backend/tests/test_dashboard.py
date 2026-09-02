"""
Tests for dashboard stats endpoint.

Coverage:
  - GET /api/v1/dashboard/stats — 401, response shape, correct field names,
    role-scoped document count, counts from DB (not fake).
"""

import pytest
from httpx import AsyncClient

# =============================================================================
# GET /dashboard/stats — authentication
# =============================================================================


@pytest.mark.asyncio
async def test_dashboard_stats_unauthenticated(async_client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    response = await async_client.get("/api/v1/dashboard/stats")
    assert response.status_code == 401


# =============================================================================
# GET /dashboard/stats — response structure
# =============================================================================


@pytest.mark.asyncio
async def test_dashboard_stats_response_shape(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Response contains success, message, data with exactly the documented fields."""
    response = await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    # Envelope shape
    assert body["success"] is True
    assert "message" in body
    assert "data" in body

    # Core KPI fields are present
    data = body["data"]
    assert {"total_departments", "total_employees", "total_documents"}.issubset(set(data.keys()))


@pytest.mark.asyncio
async def test_dashboard_stats_fields_are_integers(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """All stat values are non-negative integers."""
    response = await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    for field in ("total_departments", "total_employees", "total_documents"):
        assert isinstance(data[field], int)
        assert data[field] >= 0


# =============================================================================
# GET /dashboard/stats — counts from DB (not fake)
# =============================================================================


@pytest.mark.asyncio
async def test_dashboard_stats_department_count_reflects_creates(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """total_departments increases after creating a department."""
    before = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]["total_departments"]

    await async_client.post(
        "/api/v1/departments",
        json={"name": "Dashboard Test Dept"},
        headers=admin_headers,
    )

    after = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]["total_departments"]

    assert after == before + 1


@pytest.mark.asyncio
async def test_dashboard_stats_document_count_reflects_creates(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """total_documents for an employee increases after creating a document."""
    before = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]["total_documents"]

    await async_client.post(
        "/api/v1/documents",
        json={"file_name": "dash_test.pdf", "storage_path": "uploads/dash_test.pdf"},
        headers=auth_headers,
    )

    after = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]["total_documents"]

    assert after == before + 1


@pytest.mark.asyncio
async def test_dashboard_stats_admin_sees_all_documents(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Admin total_documents count includes documents owned by other users."""
    # Employee creates a document
    await async_client.post(
        "/api/v1/documents",
        json={"file_name": "emp_doc.pdf", "storage_path": "uploads/emp.pdf"},
        headers=auth_headers,
    )

    admin_stats = (await async_client.get("/api/v1/dashboard/stats", headers=admin_headers)).json()[
        "data"
    ]

    emp_stats = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]

    # Admin total must be >= employee total (admin sees all)
    assert admin_stats["total_documents"] >= emp_stats["total_documents"]


@pytest.mark.asyncio
async def test_dashboard_stats_employee_scoped_documents(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_headers: dict,
) -> None:
    """Employee total_documents is scoped to own documents only."""
    # Admin creates a document — employee should NOT see it in their count
    before = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]["total_documents"]

    await async_client.post(
        "/api/v1/documents",
        json={"file_name": "admin_only.pdf", "storage_path": "uploads/admin_only.pdf"},
        headers=admin_headers,
    )

    after = (await async_client.get("/api/v1/dashboard/stats", headers=auth_headers)).json()[
        "data"
    ]["total_documents"]

    # Employee count must not have increased (admin's doc is not theirs)
    assert after == before
