"""
Security utilities for IntelliFlow AI.

Provides:
  - Password hashing and verification using Argon2id
  - JWT access token creation and decoding
  - Refresh token generation and hashing
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jose import jwt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Argon2id password hasher
# ---------------------------------------------------------------------------
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65_536,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using Argon2id.
    """
    return _ph.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored Argon2id hash.
    """
    try:
        return cast(bool, _ph.verify(hashed_password, plain_password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------------------
# JWT access token
# ---------------------------------------------------------------------------
def create_access_token(
    subject: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a signed JWT access token.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = secrets.token_hex(16)  # Unique token identifier

    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expire,
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)

    token_str = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return cast(str, token_str)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.
    """
    decoded = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return cast(dict[str, Any], decoded)


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------
def create_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically secure refresh token pair.
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """
    Compute the SHA-256 hex digest of a token string.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()
