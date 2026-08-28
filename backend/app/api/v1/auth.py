"""
Authentication API routes.
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    """Provide an AuthService instance with the injected database session."""
    return AuthService(db)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Creates a new user with the default 'employee' role. "
        "Email is normalised to lowercase before storage. "
        "Returns the created user's safe profile (no password hash)."
    ),
    responses={
        201: {"description": "Account created successfully."},
        409: {"description": "Email address already registered."},
        422: {"description": "Validation error (weak password, invalid email, etc.)."},
    },
)
async def register(
    data: RegisterRequest,
    auth_svc: AuthService = Depends(_get_auth_service),
) -> dict[str, Any]:
    """Register a new user account."""
    user = await auth_svc.register(data)
    return {
        "success": True,
        "message": "Account created successfully.",
        "data": user.model_dump(mode="json"),
    }


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive JWT tokens",
    description=(
        "Validates credentials and returns a short-lived access token (15 min) "
        "and a long-lived refresh token (7 days). "
        "Uses generic error messages to prevent user enumeration."
    ),
    responses={
        200: {"description": "Login successful. Returns access + refresh tokens."},
        401: {"description": "Invalid credentials or deactivated account."},
    },
)
async def login(
    data: LoginRequest,
    auth_svc: AuthService = Depends(_get_auth_service),
) -> dict[str, Any]:
    """Authenticate a user and issue token pair."""
    result = await auth_svc.login(data)
    return {
        "success": True,
        "message": "Login successful.",
        "data": result.model_dump(mode="json"),
    }


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    summary="Refresh access token using a refresh token",
    description=(
        "Validates the provided refresh token, revokes it (rotation), "
        "and issues a new access token and refresh token pair. "
        "The old refresh token cannot be reused after this call."
    ),
    responses={
        200: {"description": "New token pair issued."},
        401: {"description": "Invalid, expired, or revoked refresh token."},
    },
)
async def refresh(
    data: RefreshRequest,
    auth_svc: AuthService = Depends(_get_auth_service),
) -> dict[str, Any]:
    """Refresh the access token using a valid refresh token."""
    result = await auth_svc.refresh_tokens(data)
    return {
        "success": True,
        "message": "Tokens refreshed successfully.",
        "data": result.model_dump(mode="json"),
    }


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout and revoke refresh token",
    description=(
        "Revokes the provided refresh token server-side. "
        "The access token remains valid until its natural expiry (15 min). "
        "Requires a valid access token in the Authorization header."
    ),
    responses={
        200: {"description": "Logout successful."},
        401: {"description": "Not authenticated (invalid/missing access token)."},
    },
)
async def logout(
    data: LogoutRequest,
    _current_user: User = Depends(get_current_user),
    auth_svc: AuthService = Depends(_get_auth_service),
) -> dict[str, Any]:
    """Logout the current user and revoke their refresh token."""
    await auth_svc.logout(data)
    return {
        "success": True,
        "message": "Logged out successfully.",
    }


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description=(
        "Returns the authenticated user's safe profile. "
        "Requires a valid access token in the Authorization header. "
        "Never returns password_hash."
    ),
    responses={
        200: {"description": "Current user profile."},
        401: {"description": "Not authenticated (invalid/missing access token)."},
    },
)
async def me(
    current_user: User = Depends(get_current_user),
    auth_svc: AuthService = Depends(_get_auth_service),
) -> dict[str, Any]:
    """Return the current authenticated user's profile."""
    profile = await auth_svc.get_current_user_profile(current_user)
    return {
        "success": True,
        "message": "User profile retrieved successfully.",
        "data": profile.model_dump(mode="json"),
    }
