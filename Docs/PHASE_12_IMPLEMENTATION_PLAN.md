# Phase 12 Implementation Plan — Enterprise Security, Observability & Production Hardening

## 1. Executive Summary

Milestone 12 elevates **IntelliFlow AI** from a feature-complete application (Milestones 1–11) into a hardened, production-grade enterprise platform. It strengthens authentication and session governance, establishes centralized security auditing, enforces rate limiting and API security headers, builds multi-tier health and diagnostic observability, reinforces background worker reliability, provides global error handling envelopes without secret leakage, and introduces dedicated administrator security and system observability interfaces.

---

## 2. Current Architecture Assessment & Discovered Gaps

### A. Security Weaknesses Discovered
1. **Refresh Token Reuse Detection**: While refresh tokens are rotated, presentation of an already-revoked token does not invalidate the entire token family or session chain for the compromised user account.
2. **Missing Rate Limiting**: Sensitive endpoints (e.g. `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/ai/chat`, `/api/v1/documents/upload`, `/api/v1/reports`) have no rate limiting, leaving them susceptible to brute-force credential stuffing and resource exhaustion.
3. **Security Headers**: Standard defensive HTTP response headers (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, `Referrer-Policy`) are not systematically attached.
4. **Security Audit Events**: `AuditLog` captures general entity changes, but does not provide standardized severity grading (`info`, `warning`, `critical`), structured security event filtering, or automated alerts on failed authentication and access violations.
5. **Session Management**: Users lack the ability to view active sessions or invoke single-action global session revocation.

### B. Observability & Health Gaps
1. **Health Probes**: Only `/health` exists, returning a static `{"status": "ok"}` without checking downstream dependencies (PostgreSQL, Redis, Celery, FAISS, Ollama).
2. **Request Correlation**: No `X-Request-ID` tracking is generated or propagated across logs and response headers.
3. **Admin Telemetry**: There is no centralized administration screen for viewing real-time database connection metrics, Celery queue depth, Redis memory, or security audit logs.

### C. Reliability & Worker Gaps
1. **Worker Retries & Timeouts**: Celery tasks lack uniform retry policies with exponential backoff and jitter, leaving tasks vulnerable to transient network failures or indefinite hangs without timeouts.
2. **Error Envelope Consistency**: FastAPI `HTTPException` and unhandled exceptions do not return a unified enterprise error envelope containing `request_id`, error `code`, and safe sanitized descriptions.

---

## 3. Proposed Architecture & Core Components

```
                                      ┌────────────────────────────────────────────────────────┐
                                      │                Next.js 16 Client & UI                  │
                                      │   /admin/security  •  /admin/system  •  ErrorBoundaries │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │ HTTPS / X-Request-ID
                                                                  ▼
                                      ┌────────────────────────────────────────────────────────┐
                                      │             FastAPI Gateway & Middleware               │
                                      │ • CorrelationIdMiddleware (X-Request-ID propagation)   │
                                      │ • SecurityHeadersMiddleware (HSTS, CSP, X-Frame)       │
                                      │ • RateLimitMiddleware / Sliding Window (Redis-backed)  │
                                      │ • Global Exception Handlers (Standard Error Envelope)  │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────┴────────────────────────────┐
                                      │                                                        │
                                      ▼                                                        ▼
┌───────────────────────────────────────────────────────────┐ ┌──────────────────────────────────────────────────────────┐
│              Security & Audit Subsystem                   │ │               Observability & Health                   │
│ • SecurityAuditService (Severity, Events, Sanitization)   │ │ • HealthService (/health/live, /ready, /details)       │
│ • Hardened AuthService (Token Family Revocation on Reuse) │ │ • SystemMetricsService (Postgres, Redis, Worker, AI)   │
│ • Session Management (Revoke All Sessions)                │ │ • Structured Request Logging (Latency, Route, Status)  │
└─────────────────────────────┬─────────────────────────────┘ └────────────────────────────┬─────────────────────────┘
                              │                                                           │
                              └───────────────────────────┬───────────────────────────────┘
                                                          │
                                                          ▼
                              ┌────────────────────────────────────────────────────────┐
                              │            Database & Background Workers               │
                              │ • PostgreSQL: audit_logs (indexes), refresh_tokens     │
                              │ • Redis: Rate limiting sliding windows & cache         │
                              │ • Celery: Reliable base tasks (backoff, timeouts)      │
                              └────────────────────────────────────────────────────────┘
```

---

## 4. Detailed Component Design

### 1. Security Event & Audit System
- Standardized actions: `auth.login_success`, `auth.login_failed`, `auth.token_refreshed`, `auth.reuse_detected`, `auth.logout`, `auth.sessions_revoked`, `access.denied`, `access.forbidden`, `rate_limit.exceeded`, `admin.action`, `document.access_denied`.
- Severity classifications: `INFO`, `WARNING`, `CRITICAL`.
- Sanitization engine: Redacts any potential credentials, JWT strings, passwords, or document binary/raw content.
- Query API: `GET /api/v1/admin/security/events` with pagination and filters (`action`, `severity`, `user_id`, `success`, `start_date`, `end_date`), and `GET /api/v1/admin/security/summary`.

### 2. Authentication Hardening & Token Reuse Detection
- **Reuse Detection**: If a revoked refresh token is presented, immediately revoke all active refresh tokens for that user ID, record a `CRITICAL` `auth.reuse_detected` audit event, and return HTTP 401.
- **Global Session Revocation**: `POST /api/v1/auth/revoke-all` revokes all active refresh tokens for the authenticated user.
- **Active Sessions Query**: `GET /api/v1/auth/sessions` returns active session metadata (issued time, expiry, last IP).

### 3. API Protection & Rate Limiting
- **Redis Sliding-Window Rate Limiter**: High-performance, resource-conscious Lua script or sorted-set counter in Redis with an in-memory fallback for local testing and resilience.
- **Endpoint Limits**:
  - `/api/v1/auth/login`: 5 req / minute per IP.
  - `/api/v1/auth/refresh`: 30 req / minute per IP.
  - `/api/v1/ai/chat` & `/api/v1/documents/*/ai/*`: 20 req / minute per user.
  - `/api/v1/documents/upload` & `/versions`: 30 req / minute per user.
  - `/api/v1/reports/*` & `/workflows/*/execute`: 20 req / minute per user.
- **Security Headers**: HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, CSP.

### 4. Observability, Logging & Correlation IDs
- **Correlation ID**: Auto-generate UUIDv4 or accept valid incoming `X-Request-ID`. Attached to Python `logging` context, request state, and HTTP response headers.
- **Structured Request Logger**: Log method, path, status, latency in ms, client IP, user ID (when authenticated), and request ID.

### 5. Multi-Tier Health System
- `GET /health` & `GET /api/v1/health/live`: Fast liveness check (process responsive).
- `GET /api/v1/health/ready`: Readiness check testing PostgreSQL `SELECT 1`, Redis `ping`, Celery broker connectivity, and FAISS index state. Returns HTTP 200 (healthy/degraded) or HTTP 503 (unhealthy).
- `GET /api/v1/health/details`: Admin-only diagnostics reporting system uptime, DB connection pool status, Redis memory info, Celery task queue lengths, and AI vector counts.

### 6. Background Worker Reliability
- Base task options: `autoretry_for=(Exception,)`, `max_retries=3`, `retry_backoff=True`, `retry_backoff_max=300`, `retry_jitter=True`.
- Explicit timeouts: `soft_time_limit=300`, `time_limit=360`.
- Structured logging with task execution time and exception classification.

### 7. Global Error Handling
- Consistent response schema:
  ```json
  {
    "success": false,
    "error": {
      "code": "RATE_LIMIT_EXCEEDED",
      "message": "Too many requests. Please try again in 45 seconds.",
      "request_id": "6a7b...",
      "details": null
    }
  }
  ```
- No stack traces, SQL syntax, or internal file paths returned to clients.

### 8. System Settings Validation
- Startup validation in `app/core/config.py` verifying JWT secret strength in production, Redis connectivity configuration, CORS whitelist safety, and database URL validity.

### 9. Frontend Production Hardening & Admin Dashboards
- **Global & Route Error Boundaries**: React Error Boundary catching unexpected UI rendering errors with recovery actions.
- **Admin Security Dashboard** (`/admin/security`): Filterable timeline of security events, severity badges, failed login charts, and rate limit telemetry.
- **Admin System Health Dashboard** (`/admin/system`): Real-time dependency health cards (PostgreSQL, Redis, Celery, AI), latency meters, uptime, and database pool statistics.

---

## 5. Implementation Phases & Order

1. **Phase 12.1 — Configuration & Security Validation**: Startup validator and settings expansion.
2. **Phase 12.2 — Request Correlation & Security Headers Middleware**: `X-Request-ID` and defensive headers.
3. **Phase 12.3 — Resource-Conscious Rate Limiting Engine**: Redis sliding-window limiter with memory fallback.
4. **Phase 12.4 — Centralized Security Event System**: Repository, service, sanitization, and query endpoints.
5. **Phase 12.5 — Authentication Hardening & Token Reuse Detection**: Family revocation, session revocation, session listing.
6. **Phase 12.6 — Multi-Tier Health & Diagnostic System**: Live, Ready, and Details endpoints.
7. **Phase 12.7 — Celery Worker Reliability Hardening**: Retry policies, backoff, timeouts across all worker modules.
8. **Phase 12.8 — Standardized Global Error Envelopes**: Exception handlers and response schemas.
9. **Phase 12.9 — Admin Observability & Security API Endpoints**: Endpoints for metrics, queue status, security audit.
10. **Phase 12.10 — Frontend Production Hardening & Error Boundaries**: Interceptors, error boundaries, recovery UX.
11. **Phase 12.11 — Frontend Admin Security & System Dashboards**: Next.js pages for `/admin/security` and `/admin/system`.
12. **Phase 12.12 — Security & Reliability Test Suite**: Unit, integration, and security tests.
13. **Phase 12.13 — Full Regression Verification (603+ Tests)**: Guarantee 100% green suite across all milestones.
14. **Phase 12.14 — Live E2E Security Audit Script**: `backend/scripts/verify_phase12_e2e.py` executing 18+ live checks.
15. **Phase 12.15 — Comprehensive Runbooks & Documentation**: `PHASE_12_ENTERPRISE_SECURITY.md`, `PHASE_12_RUNBOOK.md`, roadmap and architecture updates.

---

## 6. Acceptance Criteria & Invariants
- 100% of all existing 603 backend tests pass without modification or weakening of RBAC.
- Zero secrets (JWTs, passwords, raw tokens, DB URLs) exposed in logs, error envelopes, or health responses.
- Presentation of a revoked refresh token triggers immediate token family revocation and critical security audit logging.
- Rate limiting enforces bounds on sensitive endpoints without degrading developer workflow.
- All live E2E security checks pass.
- Frontend builds and type-checks cleanly with zero errors.
