# =============================================================================
# IntelliFlow AI — PostgreSQL Database Restore Script (PowerShell)
#
# Usage:
#   .\scripts\restore_database.ps1 -BackupFile <path> [-Confirm]
#
# ⚠️  WARNING: This script OVERWRITES existing data.
#             A safety backup is created automatically before restore.
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,
    [switch]$Confirm,
    [string]$PostgresContainer = "intelliflow_postgres",
    [string]$BackendContainer = "intelliflow_backend",
    [string]$PostgresUser = "intelliflow_user",
    [string]$PostgresDb = "intelliflow"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BackupDir = Join-Path $ProjectDir "backups"

function Write-Log {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}

function Write-Err {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $Message" -ForegroundColor Red
}

# ── Validate ──────────────────────────────────────────────────────────────────
if (-not (Test-Path $BackupFile)) {
    Write-Err "Backup file not found: $BackupFile"
    Write-Host ""
    Write-Host "Available backups:"
    Get-ChildItem -Path $BackupDir -Filter "intelliflow_*.sql*" -ErrorAction SilentlyContinue |
        Format-Table Name, LastWriteTime, Length
    exit 1
}

try {
    $null = docker container inspect $PostgresContainer 2>$null
    if ($LASTEXITCODE -ne 0) { throw "not running" }
} catch {
    Write-Err "PostgreSQL container '$PostgresContainer' is not running"
    exit 1
}

# ── Confirmation ──────────────────────────────────────────────────────────────
Write-Log "====================================================================="
Write-Log "⚠️  DATABASE RESTORE — THIS WILL OVERWRITE EXISTING DATA ⚠️"
Write-Log "====================================================================="
Write-Log "Container : $PostgresContainer"
Write-Log "Database  : $PostgresDb"
Write-Log "Restore   : $BackupFile"
Write-Log "====================================================================="

if (-not $Confirm) {
    $Response = Read-Host "Type 'RESTORE' to confirm destructive restore"
    if ($Response -ne "RESTORE") {
        Write-Log "Restore cancelled."
        exit 0
    }
}

# ── Safety Backup ─────────────────────────────────────────────────────────────
Write-Log "Creating safety backup before restore..."
$SafetyTimestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$SafetyBackup = Join-Path $BackupDir "pre_restore_safety_${SafetyTimestamp}.sql"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

docker exec $PostgresContainer pg_dump -U $PostgresUser -d $PostgresDb `
    --no-password --format=plain --clean --if-exists > $SafetyBackup

if ($LASTEXITCODE -ne 0) {
    Write-Err "Safety backup failed — aborting restore"
    exit 2
}
Write-Log "Safety backup created: $SafetyBackup"

# ── Restore ───────────────────────────────────────────────────────────────────
Write-Log "Restoring database from: $(Split-Path -Leaf $BackupFile)"

# Handle both .sql and .sql.gz
if ($BackupFile -match "\.gz$") {
    if (Get-Command gzip -ErrorAction SilentlyContinue) {
        & { gzip -d -c $BackupFile } |
            docker exec -i $PostgresContainer psql -U $PostgresUser -d $PostgresDb --no-password -q
    } else {
        Write-Err "gzip not found in PATH. Please decompress the backup manually first."
        exit 1
    }
} else {
    Get-Content $BackupFile | docker exec -i $PostgresContainer psql -U $PostgresUser -d $PostgresDb --no-password -q
}

if ($LASTEXITCODE -ne 0) {
    Write-Err "Restore failed. Safety backup available at: $SafetyBackup"
    exit 3
}

Write-Log "Database restore: COMPLETE"

# ── Verify Migration State ────────────────────────────────────────────────────
Write-Log "Verifying Alembic migration state..."

try {
    $Current = docker exec $BackendContainer alembic -c /app/alembic.ini current 2>$null
    Write-Log "Migration current: $Current"
    if ($Current -match "\(head\)") {
        Write-Log "Migration state: AT HEAD ✓"
    } else {
        Write-Log "WARNING: Run 'docker exec $BackendContainer alembic upgrade head' to apply pending migrations"
    }
} catch {
    Write-Log "WARNING: Could not verify migration state (backend container may not be running)"
}

Write-Log "====================================================================="
Write-Log "RESTORE COMPLETE"
Write-Log "  Restored from : $BackupFile"
Write-Log "  Safety backup : $SafetyBackup"
Write-Log "  Time          : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Log "====================================================================="
