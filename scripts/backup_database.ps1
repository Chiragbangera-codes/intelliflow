# =============================================================================
# IntelliFlow AI — PostgreSQL Database Backup Script (PowerShell)
#
# Usage:
#   .\scripts\backup_database.ps1 [-BackupDir <path>] [-RetentionDays <days>]
#
# Requirements:
#   - Docker Desktop running
#   - intelliflow_postgres container running
#
# Output:
#   backups\intelliflow_YYYY-MM-DD_HHMMSS.sql.gz
# =============================================================================

[CmdletBinding()]
param(
    [string]$BackupDir = "",
    [int]$RetentionDays = 30,
    [string]$PostgresContainer = "intelliflow_postgres",
    [string]$PostgresUser = "intelliflow_user",
    [string]$PostgresDb = "intelliflow"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

# Load .env if present
$EnvFile = Join-Path $ProjectDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $key = $Matches[1]
            $val = $Matches[2] -replace '#.*$', '' -replace '"', '' -replace "'", ''
            [System.Environment]::SetEnvironmentVariable($key, $val.Trim())
        }
    }
    if ([System.Environment]::GetEnvironmentVariable("POSTGRES_USER")) {
        $PostgresUser = [System.Environment]::GetEnvironmentVariable("POSTGRES_USER")
    }
    if ([System.Environment]::GetEnvironmentVariable("POSTGRES_DB")) {
        $PostgresDb = [System.Environment]::GetEnvironmentVariable("POSTGRES_DB")
    }
}

if (-not $BackupDir) {
    $BackupDir = Join-Path $ProjectDir "backups"
}

function Write-Log {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}

function Write-Err {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $Message" -ForegroundColor Red
}

# ── Check Prerequisites ───────────────────────────────────────────────────────
Write-Log "Checking prerequisites..."

try {
    $null = docker container inspect $PostgresContainer 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Container not found" }
} catch {
    Write-Err "PostgreSQL container '$PostgresContainer' is not running"
    exit 1
}

# ── Create Backup Directory ───────────────────────────────────────────────────
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
    Write-Log "Created backup directory: $BackupDir"
}

# ── Perform Backup ────────────────────────────────────────────────────────────
$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$BackupFilename = "intelliflow_${Timestamp}.sql.gz"
$BackupPath = Join-Path $BackupDir $BackupFilename

Write-Log "Starting backup: $BackupFilename"
Write-Log "Database: $PostgresDb @ $PostgresContainer"

try {
    # pg_dump → gzip (requires gzip in PATH or use Docker to compress)
    $DumpCmd = "pg_dump -U $PostgresUser -d $PostgresDb --no-password --format=plain --clean --if-exists"
    docker exec $PostgresContainer sh -c $DumpCmd | & { 
        # Check if gzip is available
        if (Get-Command gzip -ErrorAction SilentlyContinue) {
            $input | gzip > $BackupPath
        } else {
            # Fallback: save uncompressed, rename
            $UncompressedPath = $BackupPath -replace "\.gz$", ""
            $input | Set-Content -Path $UncompressedPath -Encoding Byte
            $BackupPath = $UncompressedPath
            $BackupFilename = $BackupFilename -replace "\.gz$", ""
            Write-Log "WARNING: gzip not found — backup saved uncompressed as $BackupFilename"
        }
    }

    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
    Write-Log "Backup written: $BackupPath"
} catch {
    Write-Err "Backup failed: $_"
    if (Test-Path $BackupPath) { Remove-Item $BackupPath -Force }
    exit 2
}

# ── Verify Backup ─────────────────────────────────────────────────────────────
Write-Log "Verifying backup integrity..."

if (-not (Test-Path $BackupPath)) {
    Write-Err "Backup file not found: $BackupPath"
    exit 3
}

$FileSize = (Get-Item $BackupPath).Length
Write-Log "Backup size: $([math]::Round($FileSize / 1024, 1)) KB"

if ($FileSize -lt 100) {
    Write-Err "Backup file is suspiciously small ($FileSize bytes)"
    exit 4
}

Write-Log "Backup integrity: PASS"

# ── Cleanup Old Backups ───────────────────────────────────────────────────────
Write-Log "Cleaning up backups older than $RetentionDays days..."
$Cutoff = (Get-Date).AddDays(-$RetentionDays)
$OldBackups = Get-ChildItem -Path $BackupDir -Filter "intelliflow_*.sql*" |
    Where-Object { $_.LastWriteTime -lt $Cutoff }

foreach ($old in $OldBackups) {
    Remove-Item $old.FullName -Force
    Write-Log "  Removed: $($old.Name)"
}

if ($OldBackups.Count -eq 0) {
    Write-Log "No old backups to clean up"
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Log "===================================================================="
Write-Log "BACKUP COMPLETE"
Write-Log "  File    : $BackupPath"
Write-Log "  Database: $PostgresDb"
Write-Log "  Time    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Log "===================================================================="
