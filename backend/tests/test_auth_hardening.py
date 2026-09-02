"""
Unit and integration tests for Authentication Hardening & Token Reuse Detection (Milestone 12).
"""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus
from app.schemas.auth import LoginRequest, RefreshRequest
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_refresh_token_reuse_detection(
    async_client: AsyncClient, db_session: AsyncSession, admin_user: User
):
    """
    Verify that presenting an already-revoked refresh token triggers REUSE DETECTION:
      - All active refresh tokens for that user are revoked.
      - A critical security audit event is logged.
      - The request is rejected with 401.
    """
    auth_svc = AuthService(db_session)

    # 1. Login to get initial token pair (Token A)
    login_res = await auth_svc.login(
        LoginRequest(email=admin_user.email, password="AdminPass1!"),
        ip_address="127.0.0.1",
    )
    token_a = login_res.refresh_token

    # 2. Refresh tokens legitimately (Token A is revoked, Token B is issued)
    refresh_res_1 = await auth_svc.refresh_tokens(
        RefreshRequest(refresh_token=token_a),
        ip_address="127.0.0.1",
    )
    token_b = refresh_res_1.refresh_token
    assert token_b != token_a

    # Verify Token B is active
    active_sessions_before = await auth_svc.get_user_sessions(admin_user.id)
    assert len(active_sessions_before) == 1

    # 3. ATTACK: Attacker presents already-revoked Token A again!
    with pytest.raises(Exception) as exc_info:
        await auth_svc.refresh_tokens(
            RefreshRequest(refresh_token=token_a),
            ip_address="198.51.100.2",
            user_agent="MaliciousActorBot/1.0",
        )
    assert "401" in str(exc_info.value) or "Invalid or expired" in str(exc_info.value)

    # 4. Invariant: Token B (and all sessions for this user) must now be revoked!
    active_sessions_after = await auth_svc.get_user_sessions(admin_user.id)
    assert len(active_sessions_after) == 0

    # 5. Subsequent attempts with Token B must now also fail
    with pytest.raises(HTTPException):
        await auth_svc.refresh_tokens(
            RefreshRequest(refresh_token=token_b),
            ip_address="127.0.0.1",
        )


@pytest.mark.asyncio
async def test_session_revocation_endpoints(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    admin_user: User,
    db_session: AsyncSession,
):
    """Test /api/v1/auth/sessions and /api/v1/auth/revoke-all endpoints."""
    auth_svc = AuthService(db_session)

    # Issue a few sessions
    await auth_svc.login(LoginRequest(email=admin_user.email, password="AdminPass1!"))
    await auth_svc.login(LoginRequest(email=admin_user.email, password="AdminPass1!"))

    # 1. List user sessions
    res = await async_client.get("/api/v1/auth/sessions", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert len(body["data"]) >= 2

    # 2. Revoke all sessions
    revoke_res = await async_client.post("/api/v1/auth/revoke-all", headers=admin_headers)
    assert revoke_res.status_code == 200
    revoke_body = revoke_res.json()
    assert revoke_body["success"] is True
    assert revoke_body["data"]["revoked_count"] >= 2

    # 3. List sessions now returns empty list
    res_after = await async_client.get("/api/v1/auth/sessions", headers=admin_headers)
    assert res_after.status_code == 200
    assert len(res_after.json()["data"]) == 0


@pytest.mark.asyncio
async def test_deactivated_user_cannot_refresh(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify that a deactivated user account is rejected upon token refresh."""
    auth_svc = AuthService(db_session)

    # 1. Login
    login_res = await auth_svc.login(LoginRequest(email=test_user.email, password="TestPass1!"))
    refresh_token = login_res.refresh_token

    # 2. Deactivate user account
    await db_session.execute(
        update(User).where(User.id == test_user.id).values(status=UserStatus.INACTIVE)
    )
    await db_session.commit()

    # 3. Attempt refresh
    with pytest.raises(HTTPException):
        await auth_svc.refresh_tokens(RefreshRequest(refresh_token=refresh_token))
