"""
Role-Based Access Control (RBAC) permission dependencies.

Provides `require_role` — a factory that returns a FastAPI dependency
enforcing that the authenticated user has one of the specified roles.

Usage:
    from app.dependencies.permissions import require_role

    # Admin-only endpoint
    @router.delete("/users/{id}")
    async def delete_user(
        user_id: uuid.UUID,
        current_user: User = Depends(require_role("admin")),
    ) -> dict:
        ...

    # Multiple roles allowed
    @router.get("/reports")
    async def get_reports(
        current_user: User = Depends(require_role("admin", "manager", "finance")),
    ) -> dict:
        ...

Authentication (401) is checked first by the inner get_current_user call.
Authorization (403) is only checked after successful authentication.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.models.user import User


def require_role(*roles: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """
    RBAC dependency factory.

    Returns a FastAPI dependency that:
      1. Authenticates the request via get_current_user (401 if unauthenticated).
      2. Checks that the user's role is in the allowed set (403 if unauthorised).
      3. Returns the authenticated User if both checks pass.

    Args:
        *roles: One or more role names that are permitted to access the route.

    Returns:
        A FastAPI-compatible async dependency function.
    """
    allowed_roles = frozenset(r.lower() for r in roles)

    async def _check_role(
        current_user: User = Depends(get_current_user),
    ) -> User:
        """Inner dependency — checks role membership after authentication."""
        role_name = (
            current_user.role.name.lower()
            if (current_user.role and hasattr(current_user.role, "name") and current_user.role.name)
            else str(getattr(current_user, "role", "")).lower()
        )
        if role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
        return current_user

    return _check_role
