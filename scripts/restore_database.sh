#!/usr/bin/env bash
# =============================================================================
# IntelliFlow AI — PostgreSQL Database Restore Script
#
# Usage:
#   ./scripts/restore_database.sh <backup_file> [--confirm]
#
# Arguments:
#   backup_file   Path to the .sql.gz backup file to restore
#   --confirm     Skip the interactive confirmation prompt
#
# ⚠️  WARNING: This script DROPS and RECREATES the target database.
#             Always verify you have a valid backup before proceeding.
#             A safety backup is automatically created before restore.
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/.env"
    set +a
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-intelliflow_postgres}"
POSTGRES_USER="${POSTGRES_USER:-intelliflow_user}"
POSTGRES_DB="${POSTGRES_DB:-intelliflow}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"

# ── Parse arguments ───────────────────────────────────────────────────────────
BACKUP_FILE="${1:-}"
SKIP_CONFIRM="${2:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup_file.sql.gz> [--confirm]"
    echo ""
    echo "Available backups:"
    ls -lh "${BACKUP_DIR}/"intelliflow_*.sql.gz 2>/dev/null || echo "  (no backups found in $BACKUP_DIR)"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    err "Backup file not found: $BACKUP_FILE"
    exit 1
fi

if ! gzip --test "$BACKUP_FILE" 2>/dev/null; then
    err "Backup file failed integrity check: $BACKUP_FILE"
    exit 1
fi

if ! docker container inspect "$POSTGRES_CONTAINER" &>/dev/null; then
    err "PostgreSQL container '$POSTGRES_CONTAINER' is not running"
    exit 1
fi

# ── Confirmation ──────────────────────────────────────────────────────────────
log "====================================================================="
log "⚠️  DATABASE RESTORE — THIS WILL OVERWRITE EXISTING DATA ⚠️"
log "====================================================================="
log "Container : $POSTGRES_CONTAINER"
log "Database  : $POSTGRES_DB"
log "Restore   : $BACKUP_FILE"
log "Size      : $(du -h "$BACKUP_FILE" | cut -f1)"
log "====================================================================="

if [[ "$SKIP_CONFIRM" != "--confirm" ]]; then
    read -r -p "Type 'RESTORE' to confirm destructive restore: " response
    if [[ "$response" != "RESTORE" ]]; then
        log "Restore cancelled."
        exit 0
    fi
fi

# ── Safety backup ─────────────────────────────────────────────────────────────
SAFETY_TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
SAFETY_BACKUP="${BACKUP_DIR}/pre_restore_safety_${SAFETY_TIMESTAMP}.sql.gz"

log "Creating safety backup before restore..."
mkdir -p "$BACKUP_DIR"
if docker exec "$POSTGRES_CONTAINER" \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --no-password \
    --format=plain \
    --clean \
    --if-exists | gzip > "$SAFETY_BACKUP"; then
    log "Safety backup created: $SAFETY_BACKUP"
else
    err "Failed to create safety backup — aborting restore"
    exit 2
fi

# ── Restore ───────────────────────────────────────────────────────────────────
log "Restoring database from: $(basename "$BACKUP_FILE")"

if zcat "$BACKUP_FILE" | docker exec -i "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --no-password \
    -q; then
    log "Database restore: COMPLETE"
else
    err "Database restore FAILED"
    log "Safety backup is available at: $SAFETY_BACKUP"
    log "To restore the safety backup run:"
    log "  $0 $SAFETY_BACKUP --confirm"
    exit 3
fi

# ── Verify migration state ────────────────────────────────────────────────────
log "Verifying Alembic migration state..."
BACKEND_CONTAINER="${BACKEND_CONTAINER:-intelliflow_backend}"

if docker container inspect "$BACKEND_CONTAINER" &>/dev/null; then
    CURRENT=$(docker exec "$BACKEND_CONTAINER" alembic -c /app/alembic.ini current 2>/dev/null || echo "unknown")
    HEADS=$(docker exec "$BACKEND_CONTAINER" alembic -c /app/alembic.ini heads 2>/dev/null || echo "unknown")
    log "Migration current : $CURRENT"
    log "Migration heads   : $HEADS"
    if echo "$CURRENT" | grep -q "(head)"; then
        log "Migration state   : AT HEAD ✓"
    else
        log "WARNING: Migration may not be at head — run: docker exec $BACKEND_CONTAINER alembic upgrade head"
    fi
else
    log "WARNING: Backend container not found — skipping migration verification"
fi

log "====================================================================="
log "RESTORE COMPLETE"
log "  Restored from : $BACKUP_FILE"
log "  Safety backup : $SAFETY_BACKUP"
log "  Time          : $(date '+%Y-%m-%d %H:%M:%S')"
log "====================================================================="
