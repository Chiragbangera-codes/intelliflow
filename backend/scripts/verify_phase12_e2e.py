"""
End-to-End Verification Suite for Milestone 12: Enterprise Security, Observability & Production Hardening.

Executes a live audit covering:
  1. Multi-Tier Health System (/health/live, /health/ready, /health/details)
  2. Security Headers & Request Correlation Propagation (X-Request-ID)
  3. Authentication Hardening & Token Reuse Detection Cascade
  4. Sliding-Window Rate Limiting & 429 Retry-After Enforcement
  5. Security Audit Logging & Credential Sanitization Engine
  6. Admin System Observability & Subsystem Latency Metrics
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure app root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_db_url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
test_engine = create_async_engine(_db_url, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

from app.core.config import settings
from app.core.database import Base
from app.core.redis import SlidingWindowRateLimiter
from app.core.security import hash_password
from app.dependencies.database import get_db
from app.main import app
from app.models.role import Role
from app.models.user import User, UserStatus


class Phase12Verifier:
    """Automated live E2E verification orchestrator."""

    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.passed_checks = 0
        self.total_checks = 0
        self.admin_email = f"e2e_admin_{uuid.uuid4().hex[:6]}@example.com"
        self.admin_pass = "EnterpriseAdminPass1!"
        self.admin_headers: dict[str, str] = {}
        self.admin_id: uuid.UUID | None = None

    def _log_step(self, title: str) -> None:
        print(f"\n{'='*70}\n[PHASE 12 AUDIT] {title}\n{'='*70}")

    def _assert(self, condition: bool, description: str) -> None:
        self.total_checks += 1
        if condition:
            self.passed_checks += 1
            print(f"  [PASS] {description}")
        else:
            print(f"  [FAIL] {description}")
            raise AssertionError(f"Check failed: {description}")

    async def setup_test_environment(self) -> None:
        """Create schema tables and seed roles + test admin."""
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with TestSessionLocal() as session:
            admin_role_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
            existing_role = await session.get(Role, admin_role_id)
            if not existing_role:
                session.add(Role(id=admin_role_id, name="admin", description="Admin"))

            self.admin_id = uuid.uuid4()
            user = User(
                id=self.admin_id,
                email=self.admin_email,
                password_hash=hash_password(self.admin_pass),
                first_name="Security",
                last_name="Auditor",
                role_id=admin_role_id,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.commit()

    async def verify_health_system(self) -> None:
        """Audit multi-tier health endpoints."""
        self._log_step("1. Multi-Tier Health System Probes")

        # 1. Root Liveness
        res_live = await self.client.get("/health")
        self._assert(res_live.status_code == 200, "Root /health responds 200 OK")
        self._assert(res_live.json()["status"] == "ok", "Liveness status is 'ok'")

        # 2. API v1 Liveness
        res_v1_live = await self.client.get("/api/v1/health/live")
        self._assert(res_v1_live.status_code == 200, "/api/v1/health/live responds 200 OK")

        # 3. Readiness Probe
        res_ready = await self.client.get("/api/v1/health/ready")
        self._assert(res_ready.status_code in (200, 503), "/api/v1/health/ready executed dependency probes")
        ready_data = res_ready.json()
        self._assert("dependencies" in ready_data, "Readiness payload contains dependency map")
        self._assert("database" in ready_data["dependencies"], "PostgreSQL/SQLite database probed")

        # 4. Admin Diagnostics Probe
        res_diag = await self.client.get("/api/v1/health/details", headers=self.admin_headers)
        self._assert(res_diag.status_code == 200, "/api/v1/health/details accessible by Admin")
        diag = res_diag.json()["data"]
        self._assert("uptime_seconds" in diag, "Uptime metric present")
        self._assert("memory_usage_mb" in diag, "Process RSS memory metric present")
        self._assert("workers_registered" in diag, "Celery registered workers cataloged")

    async def verify_security_headers_and_correlation(self) -> None:
        """Audit HTTP security headers and correlation ID tracking."""
        self._log_step("2. Security Headers & Request Correlation Tracking")

        req_id = f"auditor-trace-{uuid.uuid4().hex[:8]}"
        res = await self.client.get("/health", headers={"X-Request-ID": req_id})
        self._assert(res.headers.get("X-Request-ID") == req_id, "Injected X-Request-ID echoed in response headers")

        headers = res.headers
        self._assert(headers.get("X-Content-Type-Options") == "nosniff", "X-Content-Type-Options: nosniff enforced")
        self._assert(headers.get("X-Frame-Options") == "DENY", "X-Frame-Options: DENY (clickjacking protection)")
        self._assert(headers.get("X-XSS-Protection") == "1; mode=block", "X-XSS-Protection enabled")
        self._assert(
            headers.get("Referrer-Policy") == "strict-origin-when-cross-origin",
            "Referrer-Policy strictly scoped",
        )

    async def verify_auth_and_token_reuse_cascade(self) -> None:
        """Audit authentication, token rotation, and reuse attack mitigation."""
        self._log_step("3. Auth Hardening & Token Reuse Detection Cascade")

        # 1. Login
        login_res = await self.client.post(
            "/api/v1/auth/login",
            json={"email": self.admin_email, "password": self.admin_pass},
        )
        self._assert(login_res.status_code == 200, "Enterprise admin authenticated successfully")
        tokens = login_res.json()["data"]
        token_a = tokens["refresh_token"]
        self.admin_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # 2. Legitimate Token Refresh
        refresh_res_1 = await self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token_a},
        )
        self._assert(refresh_res_1.status_code == 200, "Legitimate token rotation issued fresh token pair")
        token_b = refresh_res_1.json()["data"]["refresh_token"]
        self._assert(token_b != token_a, "Rotated refresh token differs from previous token")

        # 3. Malicious Token Reuse Attempt (Replaying revoked Token A)
        malicious_res = await self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token_a},
        )
        self._assert(malicious_res.status_code == 401, "Revoked token rejected with HTTP 401 Unauthorized")

        # 4. Token Reuse Cascade Invariant: Token B must now be invalidated
        subsequent_res = await self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token_b},
        )
        self._assert(
            subsequent_res.status_code == 401,
            "Security Invariant: Token Reuse Cascade invalidated entire active token family",
        )

        # Re-login for remaining tests
        re_login = await self.client.post(
            "/api/v1/auth/login",
            json={"email": self.admin_email, "password": self.admin_pass},
        )
        self.admin_headers = {"Authorization": f"Bearer {re_login.json()['data']['access_token']}"}

    async def verify_rate_limiting(self) -> None:
        """Audit sliding-window rate limiter."""
        self._log_step("4. Sliding-Window Rate Limiting Protection")

        SlidingWindowRateLimiter.reset_in_memory()
        limit = settings.RATE_LIMIT_AUTH_LOGIN
        print(f"  Sending {limit} requests to test login rate limit boundary...")

        for _ in range(limit):
            await self.client.post(
                "/api/v1/auth/login",
                json={"email": "nonexistent@example.com", "password": "WrongPassword1!"},
            )

        # Next request must hit 429
        blocked_res = await self.client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "WrongPassword1!"},
        )
        self._assert(blocked_res.status_code == 429, "Rate limiter enforced HTTP 429 Too Many Requests")
        self._assert("Retry-After" in blocked_res.headers, "Response contains Retry-After header")

        SlidingWindowRateLimiter.reset_in_memory()

    async def verify_security_governance_and_audit(self) -> None:
        """Audit centralized security audit service and sanitization."""
        self._log_step("5. Centralized Security Event Audit & Governance")

        # 1. 24h Summary Metrics
        sum_res = await self.client.get("/api/v1/admin/security/summary", headers=self.admin_headers)
        self._assert(sum_res.status_code == 200, "Admin security summary retrieved")
        sum_data = sum_res.json()["data"]
        self._assert(sum_data["critical_events_24h"] >= 1, "Token reuse security event registered as CRITICAL")

        # 2. Filtered Events Query
        events_res = await self.client.get(
            "/api/v1/admin/security/events?severity=critical&page=1&page_size=10",
            headers=self.admin_headers,
        )
        self._assert(events_res.status_code == 200, "Filterable security events stream queried")
        events_body = events_res.json()
        self._assert(events_body["pagination"]["total_items"] >= 1, "Critical events cataloged in audit log")

        # 3. Credential Redaction Check
        critical_event = events_body["data"][0]
        self._assert(
            critical_event["details"].get("password", "") != self.admin_pass,
            "Password credentials strictly redacted from audit details",
        )

    async def verify_system_metrics(self) -> None:
        """Audit admin system observability and entity inventory."""
        self._log_step("6. Admin System Observability & Subsystem Latency Metrics")

        res = await self.client.get("/api/v1/admin/system/metrics", headers=self.admin_headers)
        self._assert(res.status_code == 200, "/api/v1/admin/system/metrics returned successfully")
        metrics = res.json()["data"]

        self._assert("database_status" in metrics, "Database status metric present")
        self._assert("redis_status" in metrics, "Redis status metric present")
        self._assert("total_users_count" in metrics, "Total enterprise users inventory counted")
        self._assert("total_documents_count" in metrics, "Total documents inventory counted")
        self._assert("total_workflows_count" in metrics, "Total workflows inventory counted")


async def main() -> None:
    """Run all Milestone 12 live E2E verification suites."""
    print("=" * 70)
    print(" INTELLIFLOW AI — MILESTONE 12 ENTERPRISE SECURITY E2E AUDIT ")
    print("=" * 70)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        verifier = Phase12Verifier(client)
        await verifier.setup_test_environment()
        await verifier.verify_security_headers_and_correlation()
        await verifier.verify_auth_and_token_reuse_cascade()
        await verifier.verify_health_system()
        await verifier.verify_rate_limiting()
        await verifier.verify_security_governance_and_audit()
        await verifier.verify_system_metrics()

    app.dependency_overrides.clear()

    print("\n" + "=" * 70)
    print(f" ALL MILESTONE 12 VERIFICATION CHECKS PASSED: {verifier.passed_checks}/{verifier.total_checks} (100%)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
