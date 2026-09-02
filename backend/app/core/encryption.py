"""
Symmetric encryption utilities for sensitive credentials.

Uses AES-128-CBC with HMAC-SHA256 authenticated encryption via cryptography.Fernet.
Derives a stable 32-byte key from settings.INTEGRATION_ENCRYPTION_KEY or
settings.JWT_SECRET_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Derive a URL-safe base64-encoded 32-byte key for Fernet."""
    secret = (
        settings.INTEGRATION_ENCRYPTION_KEY.strip()
        if settings.INTEGRATION_ENCRYPTION_KEY
        else settings.JWT_SECRET_KEY
    )
    # Generate 32 bytes via SHA-256 digest
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_data(data: dict[str, Any] | str | None) -> str | None:
    """
    Encrypt a string or JSON-serializable dictionary into a ciphertext string.

    Returns None if input is None.
    """
    if data is None:
        return None

    if isinstance(data, dict):
        raw_str = json.dumps(data)
    else:
        raw_str = str(data)

    f = _get_fernet()
    token = f.encrypt(raw_str.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_data(ciphertext: str | None) -> str | None:
    """
    Decrypt a Fernet ciphertext back to its plaintext string representation.

    Returns None if ciphertext is None or invalid.
    """
    if not ciphertext:
        return None

    f = _get_fernet()
    try:
        decrypted_bytes = f.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt ciphertext — invalid token or altered encryption key.")
        return None
    except Exception as exc:
        logger.error("Unexpected error during decryption: %s", exc)
        return None


def decrypt_json(ciphertext: str | None) -> dict[str, Any] | None:
    """
    Decrypt a ciphertext and parse as a JSON dictionary.

    Returns None if input is invalid or not valid JSON.
    """
    plain = decrypt_data(ciphertext)
    if not plain:
        return None
    try:
        parsed = json.loads(plain)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except Exception as exc:
        logger.warning("Decrypted plaintext is not valid JSON: %s", exc)
        return {"raw": plain}
