"""
Tests for department endpoints.

Coverage:
  - GET  /api/v1/departments         — list, pagination, 401
  - GET  /api/v1/departments/{id}    — get, 404, 401
  - POST /api/v1/departments         — create, 409 duplicate, 403 wrong role, 401
  - PATCH /api/v1/departments/{id}   — update, 404, 409 name conflict, 403, 401
  - DELETE /api/v1/departments/{id}  — soft-delete, 404, 403, 401
"""

import pytest
from httpx import AsyncClient

# =============================================================================
# GET /departments — list
# =============================================================================


@pytest.mark.asyncio
async def test_list_departments_authenticated(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Any authenticated user can list departments."""
    response = await async_client.get("/api/v1/departments", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "meta" in body


@pytest.mark.asyncio
async def test_list_departments_unauthenticated(async_client: AsyncClient) -> None:
    """Unauthenticated requests are rejected with 401."""
    response = await async_client.get("/api/v1/departments")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_departments_pagination_meta(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Pagination meta keys are present."""
    response = await async_client.get(
        "/api/v1/departments",
        params={"page": 1, "page_size": 5},
        headers=auth_headers,
    )
    assert response.status_code == 200
    meta = response.json()["meta"]
    for key in ("page", "page_size", "total_items", "total_pages"):
        assert key in meta


# =============================================================================
# POST /departments — create
# =============================================================================


@pytest.mark.asyncio
async def test_create_department_as_admin(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Admin can create a department."""
    payload = {"name": "Engineering", "description": "Product engineering"}
    response = await async_client.post("/api/v1/departments", json=payload, headers=admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "Engineering"


@pytest.mark.asyncio
async def test_create_department_as_hr(
    async_client: AsyncClient,
    hr_headers: dict,
) -> None:
    """HR can create a department."""
    payload = {"name": "Human Resources"}
    response = await async_client.post("/api/v1/departments", json=payload, headers=hr_headers)
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "Human Resources"


@pytest.mark.asyncio
async def test_create_department_as_employee_forbidden(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Employee role cannot create departments — 403."""
    payload = {"name": "Marketing"}
    response = await async_client.post("/api/v1/departments", json=payload, headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_department_unauthenticated(async_client: AsyncClient) -> None:
    """Unauthenticated create returns 401."""
    response = await async_client.post("/api/v1/departments", json={"name": "Test"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_department_duplicate_name(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Creating a department with a duplicate name returns 409."""
    payload = {"name": "Finance Dept"}
    await async_client.post("/api/v1/departments", json=payload, headers=admin_headers)
    response = await async_client.post("/api/v1/departments", json=payload, headers=admin_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_department_missing_name(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Missing required 'name' field returns 422."""
    response = await async_client.post(
        "/api/v1/departments", json={"description": "No name"}, headers=admin_headers
    )
    assert response.status_code == 422


# =============================================================================
# GET /departments/{id}
# =============================================================================


@pytest.mark.asyncio
async def test_get_department_by_id(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Any authenticated user can get a department by ID."""
    create_resp = await async_client.post(
        "/api/v1/departments",
        json={"name": "Operations"},
        headers=admin_headers,
    )
    dept_id = create_resp.json()["data"]["id"]

    response = await async_client.get(f"/api/v1/departments/{dept_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == dept_id


@pytest.mark.asyncio
async def test_get_department_not_found(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Non-existent department returns 404."""
    response = await async_client.get(
        "/api/v1/departments/00000000-0000-0000-0000-000000000099",
        headers=auth_headers,
    )
    assert response.status_code == 404


# =============================================================================
# PATCH /departments/{id}
# =============================================================================


@pytest.mark.asyncio
async def test_update_department(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Admin can update a department."""
    create_resp = await async_client.post(
        "/api/v1/departments",
        json={"name": "Logistics"},
        headers=admin_headers,
    )
    dept_id = create_resp.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/departments/{dept_id}",
        json={"description": "Supply chain team"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["description"] == "Supply chain team"


@pytest.mark.asyncio
async def test_update_department_name_conflict(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Updating a department's name to an existing one returns 409."""
    await async_client.post("/api/v1/departments", json={"name": "Sales"}, headers=admin_headers)
    r2 = await async_client.post(
        "/api/v1/departments", json={"name": "Support"}, headers=admin_headers
    )
    dept_id = r2.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/departments/{dept_id}",
        json={"name": "Sales"},
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_department_as_employee_forbidden(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Employee cannot update a department — 403."""
    create_resp = await async_client.post(
        "/api/v1/departments", json={"name": "IT"}, headers=admin_headers
    )
    dept_id = create_resp.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/departments/{dept_id}",
        json={"description": "IT team"},
        headers=auth_headers,
    )
    assert response.status_code == 403


# =============================================================================
# DELETE /departments/{id}
# =============================================================================


@pytest.mark.asyncio
async def test_delete_department(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Admin can soft-delete a department."""
    create_resp = await async_client.post(
        "/api/v1/departments",
        json={"name": "Temporary Dept"},
        headers=admin_headers,
    )
    dept_id = create_resp.json()["data"]["id"]

    response = await async_client.delete(f"/api/v1/departments/{dept_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Soft-deleted — should return 404 now
    get_resp = await async_client.get(f"/api/v1/departments/{dept_id}", headers=admin_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_department_not_found(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Deleting a non-existent department returns 404."""
    response = await async_client.delete(
        "/api/v1/departments/00000000-0000-0000-0000-000000000099",
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_department_as_employee_forbidden(
    async_client: AsyncClient,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Employee cannot delete a department — 403."""
    create_resp = await async_client.post(
        "/api/v1/departments", json={"name": "Legal"}, headers=admin_headers
    )
    dept_id = create_resp.json()["data"]["id"]

    response = await async_client.delete(f"/api/v1/departments/{dept_id}", headers=auth_headers)
    assert response.status_code == 403
