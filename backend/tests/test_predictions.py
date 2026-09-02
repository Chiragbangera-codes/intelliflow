"""
Tests for Phase 9 Predictions API endpoints.

Tests cover:
  - RBAC enforcement (401/403)
  - Running all 3 supported prediction models
  - List and get single prediction
  - Unsupported model name returns 400
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User


def _make_headers(user: User, role_override: str | None = None) -> dict[str, str]:
    role = role_override or (user.role.name if user.role else "employee")
    token = create_access_token(subject=str(user.id), role=role)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Authentication / RBAC
# ===========================================================================


@pytest.mark.asyncio
async def test_run_prediction_requires_auth(async_client: AsyncClient) -> None:
    """Unauthenticated POST /predictions must return 401."""
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_run_prediction_forbidden_for_employee(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """Employee role must be rejected with 403."""
    headers = _make_headers(test_user, role_override="employee")
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_predictions_requires_auth(async_client: AsyncClient) -> None:
    """Unauthenticated GET /predictions must return 401."""
    resp = await async_client.get("/api/v1/predictions")
    assert resp.status_code == 401


# ===========================================================================
# Revenue forecast model
# ===========================================================================


@pytest.mark.asyncio
async def test_run_revenue_forecast(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Admin can run revenue_forecast; result contains expected fields."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast", "input": {"year": 2026}},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["model"] == "revenue_forecast"
    assert "prediction" in data
    assert "confidence" in data
    assert data["prediction"]["year"] == 2026
    assert len(data["prediction"]["monthly_forecast"]) == 12


# ===========================================================================
# Employee attrition model
# ===========================================================================


@pytest.mark.asyncio
async def test_run_employee_attrition(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Admin can run employee_attrition; result contains risk fields."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "employee_attrition"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["model"] == "employee_attrition"
    prediction = data["prediction"]
    assert "overall_attrition_risk" in prediction
    assert "overall_risk_label" in prediction
    assert prediction["overall_risk_label"] in ("Low", "Medium", "High")


# ===========================================================================
# Customer churn model
# ===========================================================================


@pytest.mark.asyncio
async def test_run_customer_churn(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Admin can run customer_churn; result contains churn_probability."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "customer_churn"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["model"] == "customer_churn"
    prediction = data["prediction"]
    assert "churn_probability" in prediction
    assert 0.0 <= prediction["churn_probability"] <= 1.0


# ===========================================================================
# Unsupported model
# ===========================================================================


@pytest.mark.asyncio
async def test_run_unsupported_model(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Unsupported model name must return 422 (Pydantic literal validation)."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "magic_unicorn_model"},
        headers=headers,
    )
    assert resp.status_code == 422


# ===========================================================================
# List and retrieve
# ===========================================================================


@pytest.mark.asyncio
async def test_list_predictions_after_run(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """After running a prediction, it must appear in the list."""
    headers = _make_headers(admin_user)

    # Run one prediction
    await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast"},
        headers=headers,
    )

    resp = await async_client.get("/api/v1/predictions", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]) >= 1
    assert "meta" in body


@pytest.mark.asyncio
async def test_get_prediction_by_id(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """A prediction created by POST must be retrievable by its ID."""
    headers = _make_headers(admin_user)

    # Run one prediction
    create_resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "customer_churn"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    prediction_id = create_resp.json()["data"]["id"]

    # Retrieve by ID
    get_resp = await async_client.get(
        f"/api/v1/predictions/{prediction_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["id"] == prediction_id


@pytest.mark.asyncio
async def test_get_prediction_not_found(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Non-existent prediction UUID must return 404."""
    headers = _make_headers(admin_user)
    resp = await async_client.get(
        "/api/v1/predictions/00000000-0000-4000-8000-000000000099",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_predictions_pagination(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """List endpoint should respect page and page_size query params."""
    headers = _make_headers(admin_user)
    resp = await async_client.get(
        "/api/v1/predictions?page=1&page_size=5",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 5


@pytest.mark.asyncio
async def test_prediction_confidence_is_bounded(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """Confidence score must be in [0, 1]."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "employee_attrition"},
        headers=headers,
    )
    assert resp.status_code == 201
    confidence = resp.json()["data"]["confidence"]
    assert confidence is not None
    assert 0.0 <= confidence <= 1.0


@pytest.mark.asyncio
async def test_finance_role_can_run_prediction(
    async_client: AsyncClient,
    finance_user: User,
) -> None:
    """Finance role must be able to run predictions."""
    headers = _make_headers(finance_user)
    resp = await async_client.post(
        "/api/v1/predictions",
        json={"model": "revenue_forecast"},
        headers=headers,
    )
    assert resp.status_code == 201
