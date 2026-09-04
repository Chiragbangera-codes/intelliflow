#!/usr/bin/env bash
# =============================================================================
# IntelliFlow AI — Unified Production Container Entrypoint
#
# Runs both FastAPI (Uvicorn) and the Celery background worker within a single
# memory-constrained container (e.g. Render Free Web Service with 512 MB RAM).
#
# Process Management:
#   - Starts Celery worker in background with concurrency 1
#   - Starts Uvicorn on dynamic $PORT with 1 worker
#   - Traps SIGTERM and SIGINT to terminate both processes cleanly
#   - Monitors both processes; exits if either dies so the host can restart
# =============================================================================
set -e

PORT="${PORT:-8000}"
echo "==> [start.sh] Starting IntelliFlow AI in production on port ${PORT}..."

# 1. Start Celery worker in background (concurrency: 1 to fit in 512 MB)
echo "==> [start.sh] Launching Celery background worker (concurrency: 1)..."
celery -A app.workers.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --max-tasks-per-child=50 &
CELERY_PID=$!
echo "==> [start.sh] Celery worker started with PID ${CELERY_PID}"

# 2. Start Uvicorn in background
echo "==> [start.sh] Launching Uvicorn on 0.0.0.0:${PORT} (workers: 1)..."
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1 \
    --no-access-log &
UVICORN_PID=$!
echo "==> [start.sh] Uvicorn started with PID ${UVICORN_PID}"

# Graceful termination handler
cleanup() {
    echo "==> [start.sh] Signal received, stopping child processes..."
    kill -TERM "${UVICORN_PID}" 2>/dev/null || true
    kill -TERM "${CELERY_PID}" 2>/dev/null || true
    wait "${UVICORN_PID}" 2>/dev/null || true
    wait "${CELERY_PID}" 2>/dev/null || true
    echo "==> [start.sh] All processes terminated cleanly."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for any process to exit; if either fails, exit to trigger container restart
wait -n "${UVICORN_PID}" "${CELERY_PID}"
EXIT_STATUS=$?
echo "==> [start.sh] A child process exited with status ${EXIT_STATUS}. Initiating shutdown..."
cleanup
