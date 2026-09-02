# IntelliFlow AI — Phase 12 Operational Runbook & Incident Management

This runbook provides step-by-step procedures for diagnosing and mitigating infrastructure, security, and operational incidents in production environments.

---

## 1. Backend Service Incident

### Symptoms
- `GET /health` or `GET /api/v1/health/live` returns connection refused or HTTP 500.
- Frontend displays "Application Error" or "Service Unavailable".

### Diagnostic Steps
1. Check process and container status:
   ```bash
   docker compose ps backend
   docker compose logs backend --tail=100
   ```
2. Verify system resources (CPU, Memory, Disk):
   ```bash
   docker stats
   ```
3. Test liveness probe manually:
   ```bash
   curl -i http://localhost:8000/api/v1/health/live
   ```

### Resolution
- If container crashed with OOM (Out Of Memory), verify Docker memory limit and restart:
  ```bash
  docker compose restart backend
  ```
- If configuration failed startup validation, verify `.env` parameters against `Settings` in `app/core/config.py`.

---

## 2. Database (PostgreSQL) Incident

### Symptoms
- `GET /api/v1/health/ready` returns HTTP 503 with `"database": {"status": "unhealthy"}`.
- Backend logs show `asyncpg.exceptions.CannotConnectNowError` or `ConnectionRefusedError`.

### Diagnostic Steps
1. Verify PostgreSQL container status:
   ```bash
   docker compose ps postgres
   docker compose logs postgres --tail=50
   ```
2. Test database connection directly:
   ```bash
   docker compose exec postgres pg_isready -U intelliflow_user -d intelliflow
   ```
3. Check active connections and locks:
   ```bash
   docker compose exec postgres psql -U intelliflow_user -d intelliflow -c "SELECT count(*) FROM pg_stat_activity;"
   ```

### Resolution
- Restart PostgreSQL service if frozen:
  ```bash
  docker compose restart postgres
  ```
- If migrations are pending:
  ```bash
  docker compose exec backend alembic upgrade head
  ```

---

## 3. Redis / Rate Limiting Incident

### Symptoms
- `GET /api/v1/health/ready` reports `"redis": {"status": "unhealthy"}`.
- Legitimate users report persistent HTTP 429 Too Many Requests.

### Diagnostic Steps
1. Check Redis container and ping:
   ```bash
   docker compose exec redis redis-cli ping
   ```
2. Check Redis memory usage:
   ```bash
   docker compose exec redis redis-cli info memory
   ```
3. Inspect rate limit keys in Redis:
   ```bash
   docker compose exec redis redis-cli keys "ratelimit:*"
   ```

### Resolution
- In-memory rate limiter will automatically take over if Redis connection drops.
- To flush stale rate limit windows:
  ```bash
  docker compose exec redis redis-cli --scan --pattern "ratelimit:*" | xargs -r docker compose exec -T redis redis-cli del
  ```

---

## 4. Celery Worker Incident

### Symptoms
- Background OCR, AI document indexing, report generation, or workflow execution tasks remain in `pending` or `running` indefinitely.
- `GET /api/v1/health/details` reports 0 active workers registered.

### Diagnostic Steps
1. Check worker logs:
   ```bash
   docker compose logs worker --tail=100
   ```
2. Check Celery queue depth in Redis:
   ```bash
   docker compose exec redis redis-cli llen celery
   docker compose exec redis redis-cli llen reports
   docker compose exec redis redis-cli llen ocr
   ```
3. Inspect active tasks:
   ```bash
   docker compose exec backend celery -A app.workers.celery_app.celery_app inspect active
   ```

### Resolution
- Restart worker processes:
  ```bash
  docker compose restart worker
  ```
- Stale tasks will automatically timeout after `soft_time_limit=300s` and be retried up to `max_retries=3`.

---

## 5. AI / Ollama & FAISS Index Incident

### Symptoms
- Document Q&A, summaries, or semantic search queries fail or return fallback responses.
- `GET /api/v1/health/ready` reports `"ollama": {"status": "unhealthy"}`.

### Diagnostic Steps
1. Test Ollama API response:
   ```bash
   curl -i http://localhost:11434/api/tags
   ```
2. Verify required models are loaded:
   ```bash
   docker compose exec ollama ollama list
   ```
3. Verify FAISS index file integrity in backend storage:
   ```bash
   ls -la backend/data/vector_store/
   ```

### Resolution
- If Ollama is responsive but model is missing:
  ```bash
  docker compose exec ollama ollama pull llama3.2
  ```
- If vector store is out of sync, trigger an admin reindex:
  ```bash
  curl -X POST http://localhost:8000/api/v1/admin/ai/reindex -H "Authorization: Bearer <ADMIN_TOKEN>"
  ```

---

## 6. Security & Token Reuse Incident

### Symptoms
- Admin Security Dashboard (`/admin/security`) flags `auth.token_reuse_detected` events with `CRITICAL` severity.
- User accounts report unexpected session expirations across multiple devices.

### Diagnostic Steps
1. Query the security events log for the affected user:
   ```bash
   curl -G http://localhost:8000/api/v1/admin/security/events \
     -d "action=auth.token_reuse_detected" \
     -d "severity=critical" \
     -H "Authorization: Bearer <ADMIN_TOKEN>"
   ```
2. Identify the originating IP address and user agent in event details.

### Resolution
- Token reuse detection cascade automatically revokes all active refresh tokens for the affected user account upon detection.
- Force complete account password reset if credential compromise is suspected.
- Admin can trigger immediate global session revocation via `/api/v1/auth/revoke-all`.
