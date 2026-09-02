# Milestone 12 — Enterprise Security, Observability & Production Hardening

## 1. Overview & Architecture

Milestone 12 transforms **IntelliFlow AI** from a feature-complete application (Milestones 1–11) into a hardened, production-grade enterprise platform. It establishes enterprise-grade security governance, token rotation and reuse detection, sliding-window rate limiting, defense-in-depth security headers, multi-tier health monitoring, Celery worker reliability policies, structured request correlation tracking, and dedicated administrator dashboards.

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

## 2. Authentication & Session Hardening

### Refresh Token Rotation & Reuse Detection
- Refresh tokens are single-use cryptographically random tokens hashed and stored in PostgreSQL (`refresh_tokens`).
- Upon presentation of a valid refresh token, the server rotates it:
  1. Revokes the old refresh token (`is_revoked = True`).
  2. Issues a new access token and a fresh refresh token.
- **Token Reuse Detection Cascade**:
  - If an already-revoked refresh token is presented (indicating a potential token theft / replay attack):
    1. Immediately revokes **all** active refresh tokens for the compromised user account.
    2. Logs a `CRITICAL` security audit event (`auth.token_reuse_detected`) with client IP and metadata.
    3. Rejects the request with HTTP 401 Unauthorized without leaking internal state.

### Active Session Governance
- `GET /api/v1/auth/sessions`: Lists active sessions (creation date, expiration, client metadata).
- `POST /api/v1/auth/revoke-all`: Single-action revocation of all active sessions across all devices for the current user.

---

## 3. Centralized Security Event System & Credential Sanitization

### Security Event Schema
All security-sensitive operations are recorded via `SecurityAuditService` to the `audit_logs` table with indexed fields:
- `action`: Standardized event actions (`auth.login_success`, `auth.login_failed`, `auth.token_refreshed`, `auth.token_reuse_detected`, `auth.sessions_revoked`, `access.denied`, `access.forbidden`, `rate_limit.exceeded`, `admin.action`).
- `severity`: `INFO`, `WARNING`, `CRITICAL`.
- `user_id`, `ip_address`, `user_agent`, `status` (`success`/`failure`).
- `details`: JSON payload sanitized through recursive redaction.

### Credential Redaction Engine
`sanitize_security_metadata()` automatically redacts:
- Passwords, password hashes, secrets, JWT tokens, refresh tokens, auth headers, API keys, database credentials, and raw document contents (`[REDACTED]`).

---

## 4. API Security & Sliding-Window Rate Limiting

### Defensive HTTP Headers (`SecurityHeadersMiddleware`)
- `X-Content-Type-Options: nosniff` (MIME-sniffing prevention)
- `X-Frame-Options: DENY` (Clickjacking prevention)
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (when HTTPS)
- `Content-Security-Policy: default-src 'self'; ...`

### Sliding-Window Rate Limiter
- Implemented with Redis sliding-window counters with an in-memory fallback for local testing and fail-open resilience.
- Endpoint limits:
  - `/api/v1/auth/login`: 5 requests / min per IP.
  - `/api/v1/auth/refresh`: 30 requests / min per IP.
  - `/api/v1/ai/chat` & `/api/v1/documents/*/ai/*`: 20 requests / min per user.
  - `/api/v1/documents/upload` & `/versions`: 30 requests / min per user.
  - `/api/v1/reports/*` & `/workflows/*/execute`: 20 requests / min per user.
- Emits HTTP 429 with standard headers: `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

---

## 5. Request Correlation & Observability

### Correlation Tracking (`CorrelationIdMiddleware`)
- Accepts incoming `X-Request-ID` or generates a UUIDv4.
- Injects correlation ID into:
  1. `request.state.request_id`
  2. Python `logging` context
  3. Response header `X-Request-ID`
  4. Standard error envelopes

### Structured Access Logging
- Formatted structured log entry per request:
  `[<request_id>] <METHOD> <PATH> -> <STATUS> (<LATENCY_MS>ms) [client: <IP>]`

---

## 6. Multi-Tier Health System

| Endpoint | Probe Type | Description | Auth Required | Status Code |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health` | Liveness | Root liveness probe (`{"status": "ok"}`) | None | 200 |
| `GET /api/v1/health/live` | Liveness | Structured process liveness probe | None | 200 |
| `GET /api/v1/health/ready` | Readiness | Downstream probe (Postgres, Redis, Celery, FAISS, Ollama) | None | 200 / 503 |
| `GET /api/v1/health/details` | Diagnostics | Telemetry (uptime, memory RSS, pool, worker catalogs) | Admin | 200 |

---

## 7. Celery Worker Reliability

All asynchronous Celery workers (`document_tasks`, `workflow_tasks`, `report_tasks`, `ocr_tasks`) implement enterprise resilience:
- `autoretry_for=(Exception,)` with exponential backoff and jitter (`retry_backoff=True`, `retry_backoff_max=300`).
- `max_retries=3` on transient failures.
- Explicit execution timeouts (`time_limit=360s`, `soft_time_limit=300s`).
- Structured logging with execution timings and error classifications.

---

## 8. Standardized Global Error Envelope

All HTTP exceptions and validation errors return a consistent envelope without secret or stack trace leakage:

```json
{
  "success": false,
  "message": "Too many requests. Please slow down and try again in 45 seconds.",
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please slow down and try again in 45 seconds.",
    "request_id": "8f3b2c91-...",
    "details": null
  }
}
```

---

## 9. Frontend Production Hardening & Admin Portals

- **Global & Route Error Boundaries**: Catch rendering exceptions gracefully with recovery and reload actions.
- **Admin Security Dashboard** (`/admin/security`): 24h security telemetry, filterable audit event logs, severity badges, and global session revocation.
- **Admin System Health Dashboard** (`/admin/system`): Real-time dependency health cards (Postgres, Redis, Celery, AI), latency gauges, uptime, and database connection statistics.
