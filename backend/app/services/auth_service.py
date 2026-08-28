"""
Authentication service — business logic for all auth operations.

This is the single source of truth for:
  - User registration flow
  - Login / credential verification
  - Token refresh with rotation
  - Logout / token revocation
  - Current-user profile retrieval

Architecture note:
  All database access goes through the repository layer.
  This service never executes SQL directly.
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserInAuthResponse,
)

logger = logging.getLogger(__name__)

# Generic message used for all authentication failures.
# A single message prevents user enumeration attacks.
_AUTH_FAILURE_MSG = "Invalid email or password."


class AuthService:
    """
    Encapsulates all authentication business logic.

    Instantiated per-request via FastAPI dependency injection.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Inject the database session and initialise repositories.

        Args:
            session: An active async SQLAlchemy session.
        """
        self._session = session
        self._users = UserRepository(session)
        self._roles = RoleRepository(session)
        self._tokens = RefreshTokenRepository(session)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    async def register(self, data: RegisterRequest) -> UserInAuthResponse:
        """
        Register a new user account.

        Flow:
          1. Validate duplicate email (409 if exists).
          2. Resolve default role.
          3. Hash password with Argon2id.
          4. Persist user.
          5. Return safe user data (no hash, no tokens).

        Args:
            data: Validated registration payload.

        Raises:
            HTTPException 409: If the email is already registered.

        Returns:
            Safe user profile (no password hash).
        """
        existing = await self._users.get_by_email(data.email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        default_role = await self._roles.get_default_role()
        password_hash = hash_password(data.password)

        user = await self._users.create(
            email=data.email,
            password_hash=password_hash,
            first_name=data.first_name,
            last_name=data.last_name,
            role_id=default_role.id,
        )
        await self._session.commit()
        await self._session.refresh(user)

        logger.info("User registered successfully: user_id=%s", user.id)

        return UserInAuthResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=default_role.name,
            status=user.status.value,
        )

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(self, data: LoginRequest) -> TokenResponse:
        """
        Authenticate a user and issue access + refresh tokens.

        Flow:
          1. Look up user by normalised email.
          2. Verify password using Argon2id — generic 401 on any failure
             (prevents user enumeration).
          3. Check account status — 401 for inactive/suspended.
          4. Stamp last_login.
          5. Issue JWT access token and opaque refresh token.
          6. Store refresh token hash.
          7. Return token pair + safe user profile.

        Args:
            data: Validated login payload.

        Raises:
            HTTPException 401: On any credential or status failure.

        Returns:
            Access token, refresh token, and safe user profile.
        """
        _invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_AUTH_FAILURE_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        )

        user = await self._users.get_by_email(data.email)
        if user is None:
            # Perform a dummy verify to prevent timing attacks
            verify_password("dummy", "$argon2id$v=19$m=65536,t=2,p=2$dummy")
            raise _invalid

        if not verify_password(data.password, user.password_hash):
            raise _invalid

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your account has been deactivated. Please contact support.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Stamp last login
        await self._users.update_last_login(user.id)

        # Issue tokens
        access_token = create_access_token(
            subject=str(user.id),
            role=user.role.name,
        )
        raw_refresh, refresh_hash = create_refresh_token()
        await self._tokens.create(user_id=user.id, token_hash=refresh_hash)

        await self._session.commit()

        logger.info("User authenticated: user_id=%s", user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            user=UserInAuthResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role.name,
                status=user.status.value,
            ),
        )

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------
    async def refresh_tokens(self, data: RefreshRequest) -> TokenResponse:
        """
        Validate a refresh token and issue a new token pair (rotation).

        Refresh token rotation:
          - The presented token is immediately revoked.
          - A new access token and refresh token are issued.
          - If the presented token was already revoked, reject the request.

        Args:
            data: Validated refresh payload containing the raw refresh token.

        Raises:
            HTTPException 401: On any token validation failure.

        Returns:
            New access token, new refresh token, and safe user profile.
        """
        _invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

        token_hash = hash_token(data.refresh_token)
        stored = await self._tokens.get_by_hash(token_hash)

        if stored is None or not stored.is_valid:
            raise _invalid

        user = await self._users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise _invalid

        # Rotate: revoke old, issue new
        await self._tokens.revoke(stored.id)

        access_token = create_access_token(
            subject=str(user.id),
            role=user.role.name,
        )
        raw_refresh, refresh_hash = create_refresh_token()
        await self._tokens.create(user_id=user.id, token_hash=refresh_hash)

        await self._session.commit()

        logger.info("Tokens rotated: user_id=%s", user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            user=UserInAuthResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role.name,
                status=user.status.value,
            ),
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    async def logout(self, data: LogoutRequest) -> None:
        """
        Revoke the provided refresh token server-side.

        Logout is only meaningful when the server-side token record is
        invalidated — not just when the client discards its copy.

        Args:
            data: Payload containing the raw refresh token to revoke.
        """
        token_hash = hash_token(data.refresh_token)
        stored = await self._tokens.get_by_hash(token_hash)
        if stored is not None and stored.revoked_at is None:
            await self._tokens.revoke(stored.id)
            await self._session.commit()
            logger.info("Refresh token revoked: user_id=%s", stored.user_id)

    # ------------------------------------------------------------------
    # Current user
    # ------------------------------------------------------------------
    async def get_current_user_profile(self, user: User) -> MeResponse:
        """
        Build a safe profile response for the currently authenticated user.

        The user object is already loaded by the get_current_user dependency.

        Args:
            user: The authenticated User ORM instance.

        Returns:
            Safe profile without password hash.
        """
        return MeResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role.name,
            status=user.status.value,
            last_login=user.last_login,
        )
