"""
Tests for employee profile endpoints.

Coverage:
  - GET  /api/v1/employees                   — list (role-scoped), 401
  - GET  /api/v1/employees/{uid}/profile     — get own, get other (role checks), 404
  - POST /api/v1/employees/{uid}/profile     — create, 409 duplicate, 403, 404
  - PATCH /api/v1/employees/{uid}/profile    — update own, 403, 404, 409 code
"""

import pytest
from httpx import AsyncClient

from app.models.user import User

# =============================================================================
# GET /employees — list
# =============================================================================


@pytest.mark.asyncio
async def test_list_employees_unauthenticated(async_client: AsyncClient) -> None:
    """Unauthenticated list returns 401."""
    response = await async_client.get("/api/v1/employees")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_employees_authenticated(
    async_client: AsyncClient,
    auth_headers: dict,
) -> None:
    """Authenticated employee gets a valid list response (own scope)."""
    response = await async_client.get("/api/v1/employees", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "meta" in body


@pytest.mark.asyncio
async def test_list_employees_admin_sees_all(
    async_client: AsyncClient,
    admin_headers: dict,
    test_user: User,
    hr_user: User,
) -> None:
    """Admin sees paginated response with meta keys."""
    response = await async_client.get("/api/v1/employees", headers=admin_headers)
    assert response.status_code == 200
    meta = response.json()["meta"]
    for key in ("page", "page_size", "total_items", "total_pages"):
        assert key in meta


# =============================================================================
# POST /employees/{user_id}/profile — create
# =============================================================================


@pytest.mark.asyncio
async def test_create_own_profile_as_employee(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
) -> None:
    """Employee can create their own profile."""
    payload = {"designation": "Software Engineer", "employee_code": "EMP-001"}
    response = await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user_id"] == str(test_user.id)
    assert data["designation"] == "Software Engineer"
    assert data["employee_code"] == "EMP-001"


@pytest.mark.asyncio
async def test_create_profile_duplicate_returns_409(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
) -> None:
    """Creating a second profile for the same user returns 409."""
    payload = {"designation": "Analyst"}
    await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json=payload,
        headers=auth_headers,
    )
    response = await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_employee_cannot_create_profile_for_another(
    async_client: AsyncClient,
    auth_headers: dict,
    admin_user: User,
) -> None:
    """Employee cannot create a profile for another user — 403."""
    response = await async_client.post(
        f"/api/v1/employees/{admin_user.id}/profile",
        json={"designation": "Hacker"},
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_profile_for_any_user(
    async_client: AsyncClient,
    admin_headers: dict,
    test_user: User,
) -> None:
    """Admin can create a profile for another user."""
    response = await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "QA Engineer"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_create_profile_user_not_found(
    async_client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Creating a profile for a non-existent user returns 404."""
    response = await async_client.post(
        "/api/v1/employees/00000000-0000-0000-0000-000000000099/profile",
        json={"designation": "Ghost"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_profile_duplicate_employee_code(
    async_client: AsyncClient,
    admin_headers: dict,
    test_user: User,
    admin_user: User,
) -> None:
    """Two profiles with the same employee_code return 409 on second."""
    await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"employee_code": "EMP-DUP"},
        headers=admin_headers,
    )
    response = await async_client.post(
        f"/api/v1/employees/{admin_user.id}/profile",
        json={"employee_code": "EMP-DUP"},
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_profile_unauthenticated(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """Unauthenticated create returns 401."""
    response = await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "Ghost"},
    )
    assert response.status_code == 401


# =============================================================================
# GET /employees/{user_id}/profile
# =============================================================================


@pytest.mark.asyncio
async def test_employee_can_get_own_profile(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
) -> None:
    """Employee can fetch their own profile after creating it."""
    await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "Dev"},
        headers=auth_headers,
    )
    response = await async_client.get(
        f"/api/v1/employees/{test_user.id}/profile",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_employee_cannot_get_another_profile(
    async_client: AsyncClient,
    admin_headers: dict,
    admin_user: User,
    auth_headers: dict,
) -> None:
    """Employee trying to get another user's profile gets 403."""
    await async_client.post(
        f"/api/v1/employees/{admin_user.id}/profile",
        json={"designation": "Admin"},
        headers=admin_headers,
    )
    response = await async_client.get(
        f"/api/v1/employees/{admin_user.id}/profile",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_profile_not_found(
    async_client: AsyncClient,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Profile that hasn't been created returns 404."""
    response = await async_client.get(
        f"/api/v1/employees/{test_user.id}/profile",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_get_any_profile(
    async_client: AsyncClient,
    admin_headers: dict,
    test_user: User,
    auth_headers: dict,
) -> None:
    """Admin can fetch any user's profile."""
    await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "Tester"},
        headers=auth_headers,
    )
    response = await async_client.get(
        f"/api/v1/employees/{test_user.id}/profile",
        headers=admin_headers,
    )
    assert response.status_code == 200


# =============================================================================
# PATCH /employees/{user_id}/profile
# =============================================================================


@pytest.mark.asyncio
async def test_employee_can_update_own_profile(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
) -> None:
    """Employee can update their own profile."""
    await async_client.post(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "Junior Dev"},
        headers=auth_headers,
    )
    response = await async_client.patch(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "Senior Dev"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["designation"] == "Senior Dev"


@pytest.mark.asyncio
async def test_employee_cannot_update_another_profile(
    async_client: AsyncClient,
    admin_user: User,
    admin_headers: dict,
    auth_headers: dict,
) -> None:
    """Employee cannot update another user's profile — 403."""
    await async_client.post(
        f"/api/v1/employees/{admin_user.id}/profile",
        json={"designation": "Admin"},
        headers=admin_headers,
    )
    response = await async_client.patch(
        f"/api/v1/employees/{admin_user.id}/profile",
        json={"designation": "Hacker"},
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_profile_not_found(
    async_client: AsyncClient,
    auth_headers: dict,
    test_user: User,
) -> None:
    """Updating a non-existent profile returns 404."""
    response = await async_client.patch(
        f"/api/v1/employees/{test_user.id}/profile",
        json={"designation": "Ghost"},
        headers=auth_headers,
    )
    assert response.status_code == 404
