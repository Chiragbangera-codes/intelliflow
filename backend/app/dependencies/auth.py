"""
Authentication dependency for FastAPI route handlers.

Provides `get_current_user` — a reusable dependency.
"""

import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.dependencies.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# HTTPBearer extractor — auto_error=False so we can return a custom 401
_bearer_scheme = HTTPBearer(auto_error=False)

# Standard 401 response for all authentication failures
_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency: validate the JWT bearer token and return the active user.
    """
    if credentials is None:
        raise _UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as err:
        raise _UNAUTHORIZED from err

    sub: str | None = payload.get("sub")
    if not sub:
        raise _UNAUTHORIZED

    try:
        user_id = uuid.UUID(sub)
    except ValueError as err:
        raise _UNAUTHORIZED from err

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)

    if user is None or not user.is_active:
        raise _UNAUTHORIZED

    return user
