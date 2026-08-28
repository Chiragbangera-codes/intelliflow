"""
Authentication Pydantic schemas.

Defines request and response models for all authentication endpoints.

Security rules enforced here:
  - Email is always normalised (lowercase + stripped) on input.
  - Passwords are validated for complexity before reaching the service layer.
  - password_hash NEVER appears in any response schema.
  - Response models use model_config from_attributes=True so ORM objects
    can be passed directly without manual conversion.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# =============================================================================
# Request schemas
# =============================================================================


class RegisterRequest(BaseModel):
    """
    Payload for POST /api/v1/auth/register.

    Enforces complexity requirements before the hash is computed.
    """

    first_name: str = Field(..., min_length=1, max_length=100, examples=["John"])
    last_name: str = Field(..., min_length=1, max_length=100, examples=["Doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=8, max_length=128, examples=["StrongPass1!"])

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        """Lowercase and strip the email to ensure consistent storage."""
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Enforce minimum password complexity per security requirements.

        Requirements:
          - At least one uppercase letter
          - At least one lowercase letter
          - At least one digit
          - At least one special character
        """
        missing: list[str] = []
        if not any(c.isupper() for c in v):
            missing.append("an uppercase letter")
        if not any(c.islower() for c in v):
            missing.append("a lowercase letter")
        if not any(c.isdigit() for c in v):
            missing.append("a digit")
        special = set("!@#$%^&*()_+-=[]{}|;':\",./<>?`~\\")
        if not any(c in special for c in v):
            missing.append("a special character")
        if missing:
            raise ValueError(f"Password must contain: {', '.join(missing)}.")
        return v


class LoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/login."""

    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=1, examples=["StrongPass1!"])

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        """Normalise email to match stored form."""
        return v.lower().strip()


class RefreshRequest(BaseModel):
    """Payload for POST /api/v1/auth/refresh."""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """Payload for POST /api/v1/auth/logout."""

    refresh_token: str = Field(..., min_length=1)


# =============================================================================
# Response schemas
# =============================================================================


class UserInAuthResponse(BaseModel):
    """
    Safe user data included in authentication responses.

    Intentionally omits: password_hash, deleted_at, updated_at.
    """

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    role: str
    status: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """
    Full authentication response returned after login and token refresh.

    Contains:
      - access_token:  Short-lived JWT (15 min default)
      - refresh_token: Long-lived opaque token (7 days default)
      - token_type:    Always "bearer"
      - user:          Safe user profile
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInAuthResponse


class MeResponse(BaseModel):
    """
    Current user profile returned by GET /api/v1/auth/me.

    Includes last_login for security transparency.
    Never includes password_hash.
    """

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    role: str
    status: str
    last_login: datetime | None

    model_config = {"from_attributes": True}
