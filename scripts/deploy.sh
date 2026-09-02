#!/usr/bin/env bash
# =============================================================================
# IntelliFlow AI — Production Deployment Script
#
# Usage:
#   ./scripts/deploy.sh [--skip-pull] [--skip-backup]
#
# Flags:
#   --skip-pull    Skip git pull (e.g. for air-gapped or pre-pulled builds)
#   --skip-backup  Skip pre-deployment database backup (NOT recommended)
#
# Absolute Rule:
#   NEVER runs `docker compose down -v`. Database volumes are strictly preserved.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SKIP_PULL=false
SKIP_BACKUP=false

for arg in "$@"; do
    case "$arg" in
        --skip-pull)   SKIP_PULL=true ;;
        --skip-backup) SKIP_BACKUP=true ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEPLOY] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEPLOY-ERROR] $*" >&2; }

log "===================================================================="
log "Starting IntelliFlow AI Production Deployment"
log "===================================================================="

# 1. Validate environment & configuration
log "Step 1: Validating environment and configuration..."
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    err ".env file missing in $PROJECT_DIR. Create one from .env.example."
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$PROJECT_DIR/.env"
set +a

if [[ "${APP_ENV:-}" != "production" ]]; then
    log "WARNING: APP_ENV is set to '${APP_ENV:-development}' instead of 'production'."
fi

if [[ -z "${JWT_SECRET_KEY:-}" || "${JWT_SECRET_KEY:-}" == *"CHANGE_ME"* ]]; then
    err "JWT_SECRET_KEY is empty or using insecure default. Aborting."
    exit 1
fi

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    err "POSTGRES_PASSWORD must not be empty in production. Aborting."
    exit 1
fi

# 2. Validate Docker availability
log "Step 2: Validating Docker and Docker Compose..."
if ! command -v docker &>/dev/null; then
    err "Docker is not installed or not in PATH."
    exit 1
fi

if ! docker compose version &>/dev/null; then
    err "Docker Compose V2 is not available."
    exit 1
fi

# 3. Pre-deployment backup (safety)
if [[ "$SKIP_BACKUP" == false ]]; then
    log "Step 3: Creating pre-deployment database backup..."
    if [[ -f "$SCRIPT_DIR/backup_database.sh" ]]; then
        bash "$SCRIPT_DIR/backup_database.sh" "$PROJECT_DIR/backups" 30 || {
            log "WARNING: Pre-deployment backup encountered an issue. Proceeding with caution..."
        }
    fi
else
    log "Step 3: Skipping pre-deployment backup as requested."
fi

# 4. Pull latest code (if applicable)
if [[ "$SKIP_PULL" == false && -d "$PROJECT_DIR/.git" ]]; then
    log "Step 4: Pulling latest changes from Git..."
    git pull --ff-only || log "WARNING: Git pull failed or branch diverged. Continuing with local code."
else
    log "Step 4: Skipping Git pull."
fi

# 5. Build production Docker images
log "Step 5: Building production Docker images..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 6. Start infrastructure (PostgreSQL & Redis)
log "Step 6: Starting core infrastructure (PostgreSQL & Redis)..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis

# 7. Wait for Database readiness
log "Step 7: Waiting for PostgreSQL to become healthy..."
MAX_TRIES=30
COUNT=0
until docker exec intelliflow_postgres pg_isready -U "${POSTGRES_USER:-intelliflow_user}" -d "${POSTGRES_DB:-intelliflow}" &>/dev/null; do
    sleep 2
    COUNT=$((COUNT + 1))
    if [[ $COUNT -ge $MAX_TRIES ]]; then
        err "PostgreSQL did not become healthy within 60 seconds."
        exit 1
    fi
done
log "PostgreSQL is healthy and accepting connections."

# 8. Run Alembic database migrations
log "Step 8: Applying pending Alembic database migrations..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 9. Start application services
log "Step 9: Launching all application services (backend, worker, frontend, ollama)..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 10. Wait for health verification
log "Step 10: Waiting for system health checks..."
sleep 5
HEALTH_OK=false
for i in {1..20}; do
    if docker exec intelliflow_backend curl -sf http://127.0.0.1:8000/health &>/dev/null; then
        HEALTH_OK=true
        break
    fi
    log "Waiting for backend health probe ($i/20)..."
    sleep 3
done

if [[ "$HEALTH_OK" == false ]]; then
    err "Backend failed health check after startup. Check 'docker compose logs backend'."
    exit 1
fi

log "===================================================================="
log "🎉 DEPLOYMENT SUCCESSFUL"
log "All production containers are up and healthy."
log "Services:"
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
log "===================================================================="
