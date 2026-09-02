"""
Unit and integration tests for Security Event & Audit System (Milestone 12).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.security import SecuritySeverity
from app.services.security_audit_service import SecurityAuditService, sanitize_security_metadata


def test_sanitize_security_metadata():
    """Verify that credentials, tokens, JWTs, and passwords are comprehensively redacted."""
    raw = {
        "user_email": "admin@intelliflow.ai",
        "password": "SuperSecretPassword123!",
        "raw_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "access_jwt": "secret_jwt_string",
        "refresh_token": "opaque_refresh_token",
        "nested": {
            "smtp_password": "mail_password",
            "api_key": "sk-1234567890",
            "safe_field": "public_data",
        },
        "list_items": [
            {"token_hash": "abcde12345", "item_name": "report.pdf"},
            {"safe_value": 42},
        ],
    }

    sanitized = sanitize_security_metadata(raw)

    assert sanitized["user_email"] == "admin@intelliflow.ai"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["raw_token"] == "[REDACTED]"
    assert sanitized["access_jwt"] == "[REDACTED]"
    assert sanitized["refresh_token"] == "[REDACTED]"
    assert sanitized["nested"]["smtp_password"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == "public_data"
    assert sanitized["list_items"][0]["token_hash"] == "[REDACTED]"
    assert sanitized["list_items"][0]["item_name"] == "report.pdf"
    assert sanitized["list_items"][1]["safe_value"] == 42


@pytest.mark.asyncio
async def test_security_audit_service_logging_and_query(db_session: AsyncSession, admin_user: User):
    """Test creating and querying security events through SecurityAuditService."""
    sec_svc = SecurityAuditService(db_session)

    # 1. Log various events
    await sec_svc.log_security_event(
        action="auth.login_success",
        severity=SecuritySeverity.INFO,
        user_id=admin_user.id,
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0 TestAgent",
        status="success",
        details={"email": admin_user.email},
    )

    await sec_svc.log_security_event(
        action="auth.login_failed",
        severity=SecuritySeverity.WARNING,
        user_id=None,
        ip_address="192.168.1.200",
        user_agent="BadBot/1.0",
        status="failure",
        details={"password": "attempted_password", "reason": "invalid_credentials"},
    )

    await sec_svc.log_security_event(
        action="auth.token_reuse_detected",
        severity=SecuritySeverity.CRITICAL,
        user_id=admin_user.id,
        ip_address="192.168.1.200",
        status="failure",
        details={"token": "compromised_token", "reason": "revoked_token_presented"},
    )

    await db_session.commit()

    # 2. Query all events
    all_res = await sec_svc.get_security_events()
    assert all_res.success is True
    assert all_res.pagination.total_items >= 3
    assert len(all_res.data) >= 3

    # Check redaction in query results
    failed_event = next(e for e in all_res.data if e.action == "auth.login_failed")
    assert failed_event.severity == "warning"
    assert failed_event.details.get("password") == "[REDACTED]"

    # 3. Filter by severity
    critical_res = await sec_svc.get_security_events(severity="critical")
    assert critical_res.pagination.total_items >= 1
    assert all(e.severity == "critical" for e in critical_res.data)

    # 4. Summary metrics
    summary_res = await sec_svc.get_security_summary()
    assert summary_res.success is True
    assert summary_res.data.total_events >= 3
    assert summary_res.data.failed_logins_24h >= 1
    assert summary_res.data.critical_events_24h >= 1


@pytest.mark.asyncio
async def test_admin_security_api_endpoints(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
):
    """Test /api/v1/admin/security/events and /api/v1/admin/security/summary endpoints."""
    # 1. Admin access to security summary
    res = await async_client.get("/api/v1/admin/security/summary", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "failed_logins_24h" in body["data"]
    assert "critical_events_24h" in body["data"]

    # 2. Admin access to security events list
    res = await async_client.get(
        "/api/v1/admin/security/events?page=1&page_size=10", headers=admin_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "data" in body
    assert "pagination" in body

    # 3. RBAC: Employee is forbidden (403)
    res = await async_client.get("/api/v1/admin/security/events", headers=auth_headers)
    assert res.status_code == 403

    # 4. Unauthenticated is 401
    res = await async_client.get("/api/v1/admin/security/events")
    assert res.status_code == 401
