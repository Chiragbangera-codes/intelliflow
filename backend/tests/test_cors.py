"""
CORS middleware and origin authorization tests.

Covers:
  - Preflight OPTIONS requests for allowed origins (localhost:3000 and 127.0.0.1:3000)
  - Preflight rejection for unauthorized origins
  - Actual requests with Origin header returning Access-Control-Allow-Origin
  - Error responses (4xx, 5xx) retaining CORS headers for allowed origins
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cors_preflight_allowed_origin(async_client: AsyncClient) -> None:
    """Preflight OPTIONS request from http://localhost:3000 returns 200 with CORS headers."""
    response = await async_client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "POST" in response.headers.get("access-control-allow-methods", "")


@pytest.mark.asyncio
async def test_cors_preflight_127_origin(async_client: AsyncClient) -> None:
    """Preflight OPTIONS request from http://127.0.0.1:3000 returns 200 with CORS headers."""
    response = await async_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_preflight_unauthorized_origin(async_client: AsyncClient) -> None:
    """Preflight OPTIONS request from unauthorized origin does not return CORS headers."""
    response = await async_client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_cors_actual_request_includes_headers(async_client: AsyncClient) -> None:
    """Actual requests with allowed Origin header receive Access-Control-Allow-Origin."""
    response = await async_client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_error_response_includes_headers(async_client: AsyncClient) -> None:
    """Error responses (e.g. 422 or 404) still include CORS headers for allowed origins."""
    response = await async_client.get(
        "/api/v1/departments/00000000-0000-0000-0000-000000000099",
        headers={"Origin": "http://localhost:3000"},
    )
    # 401 unauthenticated
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
