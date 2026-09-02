#!/usr/bin/env bash
# =============================================================================
# IntelliFlow AI — PostgreSQL Database Backup Script
#
# Usage:
#   ./scripts/backup_database.sh [backup_dir] [retention_days]
#
# Arguments:
#   backup_dir       Directory to store backups (default: ./backups)
#   retention_days   Days to retain backups (default: 30)
#
# Requirements:
#   - Docker with intelliflow_postgres container running
#   - POSTGRES_USER and POSTGRES_DB set in environment or .env
#
# Output:
#   backups/intelliflow_YYYY-MM-DD_HHMMSS.sql.gz
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/.env"
    set +a
fi

BACKUP_DIR="${1:-${BACKUP_DIR:-$PROJECT_DIR/backups}}"
RETENTION_DAYS="${2:-${BACKUP_RETENTION_DAYS:-30}}"

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-intelliflow_postgres}"
POSTGRES_USER="${POSTGRES_USER:-intelliflow_user}"
POSTGRES_DB="${POSTGRES_DB:-intelliflow}"

TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILENAME="intelliflow_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

# ── Functions ─────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

check_prerequisites() {
    log "Checking prerequisites..."

    if ! command -v docker &>/dev/null; then
        err "Docker is not installed or not in PATH"
        exit 1
    fi

    if ! docker container inspect "$POSTGRES_CONTAINER" &>/dev/null; then
        err "PostgreSQL container '$POSTGRES_CONTAINER' is not running"
        exit 1
    fi

    # Verify container is healthy
    local health
    health=$(docker inspect "$POSTGRES_CONTAINER" --format '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
    if [[ "$health" != "healthy" ]]; then
        log "WARNING: Container health is '$health' (expected 'healthy')"
    fi

    log "Prerequisites OK"
}

create_backup_dir() {
    if [[ ! -d "$BACKUP_DIR" ]]; then
        mkdir -p "$BACKUP_DIR"
        log "Created backup directory: $BACKUP_DIR"
    fi
}

perform_backup() {
    log "Starting backup: $BACKUP_FILENAME"
    log "Database: $POSTGRES_DB @ $POSTGRES_CONTAINER"

    # Run pg_dump inside the container, pipe through gzip
    if docker exec "$POSTGRES_CONTAINER" \
        pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --no-password \
        --format=plain \
        --clean \
        --if-exists | gzip > "$BACKUP_PATH"; then
        log "Backup written: $BACKUP_PATH"
    else
        err "pg_dump failed"
        rm -f "$BACKUP_PATH"
        exit 2
    fi
}

verify_backup() {
    log "Verifying backup integrity..."

    if [[ ! -f "$BACKUP_PATH" ]]; then
        err "Backup file not found: $BACKUP_PATH"
        exit 3
    fi

    local size_bytes
    size_bytes=$(stat -c%s "$BACKUP_PATH" 2>/dev/null || stat -f%z "$BACKUP_PATH")
    log "Backup size: $(numfmt --to=iec "$size_bytes" 2>/dev/null || echo "${size_bytes} bytes")"

    if [[ "$size_bytes" -lt 100 ]]; then
        err "Backup file is suspiciously small (${size_bytes} bytes) — possible empty dump"
        exit 4
    fi

    # Verify gzip integrity
    if ! gzip --test "$BACKUP_PATH" 2>/dev/null; then
        err "Backup gzip integrity check FAILED"
        exit 5
    fi

    # Verify SQL content
    local line_count
    line_count=$(zcat "$BACKUP_PATH" | wc -l)
    log "SQL statements: $line_count lines"

    if [[ "$line_count" -lt 10 ]]; then
        err "Backup appears to contain no SQL data ($line_count lines)"
        exit 6
    fi

    log "Backup integrity: PASS"
}

cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."
    local removed=0
    while IFS= read -r old_backup; do
        rm -f "$old_backup"
        log "  Removed: $(basename "$old_backup")"
        ((removed++))
    done < <(find "$BACKUP_DIR" -name "intelliflow_*.sql.gz" -mtime "+$RETENTION_DAYS" 2>/dev/null)

    if [[ "$removed" -gt 0 ]]; then
        log "Removed $removed old backup(s)"
    else
        log "No old backups to clean up"
    fi
}

print_summary() {
    log "===================================================================="
    log "BACKUP COMPLETE"
    log "  File    : $BACKUP_PATH"
    log "  Database: $POSTGRES_DB"
    log "  Time    : $(date '+%Y-%m-%d %H:%M:%S')"
    log "===================================================================="
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    log "IntelliFlow AI — Database Backup"
    check_prerequisites
    create_backup_dir
    perform_backup
    verify_backup
    cleanup_old_backups
    print_summary
    exit 0
}

main "$@"
