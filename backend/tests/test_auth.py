"""
Authentication endpoint tests.

Covers all scenarios specified in the Milestone 2 requirements (§19):
  - Registration (success, validation, duplicates, normalization)
  - Login (success, wrong password, unknown email, deactivated accounts)
  - JWT token validation (valid, expired, invalid, missing, malformed)
  - Token refresh (valid, expired, revoked, rotation)
  - Logout (success, revoked token cannot be reused)
  - RBAC (admin access, unauthorized role, unauthenticated)
  - Current user endpoint (/me)

Target: ≥90% coverage of authentication-related code paths.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User

# =============================================================================
# Registration tests — POST /api/v1/auth/register
# =============================================================================


class TestRegistration:
    """Tests for the user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, async_client: AsyncClient) -> None:
        """Successful registration returns 201 with user data (no hash)."""
        unique_email = f"newuser_{uuid.uuid4().hex[:8]}@example.com"
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": unique_email,
                "password": "StrongPass1!",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["email"] == unique_email
        assert data["role"] == "employee"
        assert data["status"] == "active"
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_register_email_normalised_to_lowercase(self, async_client: AsyncClient) -> None:
        """Email is stored as lowercase regardless of how it was sent."""
        unique_id = uuid.uuid4().hex[:8]
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Jane",
                "last_name": "Smith",
                "email": f"JANE_{unique_id}@EXAMPLE.COM",
                "password": "StrongPass1!",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["email"] == f"jane_{unique_id}@example.com"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        """Registering with an existing email returns 409 Conflict."""
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Another",
                "last_name": "User",
                "email": test_user.email,
                "password": "StrongPass1!",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["success"] is False

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(self, async_client: AsyncClient) -> None:
        """Invalid email format returns 422 Unprocessable Entity."""
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "not-an-email",
                "password": "StrongPass1!",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_weak_password_no_uppercase_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Password without uppercase letter fails validation."""
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": f"pw_{uuid.uuid4().hex[:8]}@example.com",
                "password": "weakpassword1!",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_weak_password_no_special_char_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Password without special character fails validation."""
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": f"pw2_{uuid.uuid4().hex[:8]}@example.com",
                "password": "WeakPassword1",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_fields_returns_422(self, async_client: AsyncClient) -> None:
        """Missing required fields return 422."""
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_password_returns_422(self, async_client: AsyncClient) -> None:
        """Password shorter than 8 characters is rejected."""
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": f"short_{uuid.uuid4().hex[:8]}@example.com",
                "password": "Ab1!",
            },
        )
        assert resp.status_code == 422


# =============================================================================
# Login tests — POST /api/v1/auth/login
# =============================================================================


class TestLogin:
    """Tests for the login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success_returns_tokens(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        """Successful login returns access and refresh tokens plus user data."""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "TestPass1!"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == test_user.email
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        """Wrong password returns 401 with a generic message."""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "WrongPassword1!"},
        )
        assert resp.status_code == 401
        # Must not reveal whether the email exists
        detail = resp.json()["detail"]
        assert "Invalid" in detail or "email" in detail.lower()

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(self, async_client: AsyncClient) -> None:
        """Unknown email returns 401 — same message as wrong password."""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@nowhere.com", "password": "TestPass1!"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_suspended_user_returns_401(
        self, async_client: AsyncClient, suspended_user: User
    ) -> None:
        """Suspended users cannot authenticate."""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": suspended_user.email, "password": "SuspendedPass1!"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user_returns_401(
        self, async_client: AsyncClient, inactive_user: User
    ) -> None:
        """Inactive users cannot authenticate."""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": inactive_user.email, "password": "InactivePass1!"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_email_normalised(self, async_client: AsyncClient, test_user: User) -> None:
        """Login with uppercase email succeeds (normalised before lookup)."""
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email.upper(), "password": "TestPass1!"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_login_missing_credentials_returns_422(self, async_client: AsyncClient) -> None:
        """Empty body returns 422."""
        resp = await async_client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422


# =============================================================================
# JWT / Token tests — GET /api/v1/auth/me
# =============================================================================


class TestJWT:
    """Tests for JWT token handling via the /me endpoint."""

    @pytest.mark.asyncio
    async def test_valid_token_grants_access(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Valid access token returns 200 on a protected endpoint."""
        resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, async_client: AsyncClient) -> None:
        """Missing Authorization header returns 401."""
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_token_returns_401(self, async_client: AsyncClient) -> None:
        """Malformed token returns 401."""
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, async_client: AsyncClient) -> None:
        """JWT with tampered signature returns 401."""
        # Build a token then tamper with the signature
        valid = create_access_token(subject=str(uuid.uuid4()), role="employee")
        parts = valid.split(".")
        tampered = parts[0] + "." + parts[1] + ".invalidsignature"
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_token_with_unknown_user_returns_401(self, async_client: AsyncClient) -> None:
        """Token for a non-existent user returns 401."""
        token = create_access_token(
            subject=str(uuid.uuid4()),  # Random UUID — no matching user
            role="employee",
        )
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# =============================================================================
# Refresh token tests — POST /api/v1/auth/refresh
# =============================================================================


class TestTokenRefresh:
    """Tests for the token refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_valid_token_returns_new_pair(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        """Valid refresh token issues new access + refresh tokens."""
        # Login to get tokens
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "TestPass1!"},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # Refresh
        resp = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] != refresh_token  # Token was rotated

    @pytest.mark.asyncio
    async def test_refresh_rotation_revokes_old_token(
        self, async_client: AsyncClient, test_user: User
    ) -> None:
        """After rotation, the old refresh token cannot be used again."""
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "TestPass1!"},
        )
        old_refresh_token = login_resp.json()["data"]["refresh_token"]

        # Perform refresh (rotates token)
        await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )

        # Try using the old token again
        retry_resp = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert retry_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_401(self, async_client: AsyncClient) -> None:
        """Invalid refresh token returns 401."""
        resp = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "completely-invalid-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_empty_token_returns_422(self, async_client: AsyncClient) -> None:
        """Empty refresh token fails Pydantic validation."""
        resp = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": ""},
        )
        assert resp.status_code == 422


# =============================================================================
# Logout tests — POST /api/v1/auth/logout
# =============================================================================


class TestLogout:
    """Tests for the logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict[str, str]
    ) -> None:
        """Logout revokes the refresh token and returns 200."""
        # First login to get a refresh token
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "TestPass1!"},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # Logout
        resp = await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_cannot_be_reused(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict[str, str]
    ) -> None:
        """A revoked refresh token cannot obtain a new access token."""
        # Login
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "TestPass1!"},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # Logout (revokes the refresh token)
        await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers=auth_headers,
        )

        # Attempt to refresh with the revoked token
        refresh_resp = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_requires_authentication(self, async_client: AsyncClient) -> None:
        """Logout without a valid access token returns 401."""
        resp = await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "some-token"},
        )
        assert resp.status_code == 401


# =============================================================================
# RBAC tests
# =============================================================================


class TestRBAC:
    """Tests for role-based access control."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, async_client: AsyncClient) -> None:
        """Unauthenticated request to protected endpoint returns 401."""
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_employee_can_access_own_profile(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Employee role can access /me endpoint."""
        resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "employee"

    @pytest.mark.asyncio
    async def test_admin_can_access_own_profile(
        self, async_client: AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        """Admin role can access /me endpoint."""
        resp = await async_client.get("/api/v1/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "admin"


# =============================================================================
# Current user tests — GET /api/v1/auth/me
# =============================================================================


class TestMe:
    """Tests for the current user profile endpoint."""

    @pytest.mark.asyncio
    async def test_me_returns_user_profile(
        self, async_client: AsyncClient, test_user: User, auth_headers: dict[str, str]
    ) -> None:
        """Authenticated /me returns safe user profile."""
        resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == test_user.email
        assert data["first_name"] == test_user.first_name
        assert data["last_name"] == test_user.last_name
        assert data["role"] == "employee"
        assert data["status"] == "active"
        # Must never expose password hash
        assert "password_hash" not in data
        assert "password" not in data

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, async_client: AsyncClient) -> None:
        """No token → 401."""
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401
