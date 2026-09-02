# =============================================================================
# IntelliFlow AI — Production Deployment Script (PowerShell)
#
# Usage:
#   .\scripts\deploy.ps1 [-SkipPull] [-SkipBackup]
#
# Absolute Rule:
#   NEVER runs `docker compose down -v`. Database volumes are strictly preserved.
# =============================================================================

[CmdletBinding()]
param(
    [switch]$SkipPull,
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

function Write-Log {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [DEPLOY] $Message" -ForegroundColor Cyan
}

function Write-Err {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [DEPLOY-ERROR] $Message" -ForegroundColor Red
}

Write-Log "===================================================================="
Write-Log "Starting IntelliFlow AI Production Deployment (PowerShell)"
Write-Log "===================================================================="

# 1. Validate environment
Write-Log "Step 1: Validating environment and configuration..."
$EnvFile = Join-Path $ProjectDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Err ".env file missing in $ProjectDir. Create one from .env.example."
    exit 1
}

# 2. Validate Docker
Write-Log "Step 2: Validating Docker and Docker Compose..."
try {
    $null = docker compose version 2>$null
} catch {
    Write-Err "Docker Compose is not available or Docker Desktop is not running."
    exit 1
}

# 3. Pre-deployment backup
if (-not $SkipBackup) {
    Write-Log "Step 3: Creating pre-deployment database backup..."
    $BackupScript = Join-Path $ScriptDir "backup_database.ps1"
    if (Test-Path $BackupScript) {
        try {
            & $BackupScript -RetentionDays 30
        } catch {
            Write-Log "WARNING: Pre-deployment backup encountered an issue. Continuing..."
        }
    }
} else {
    Write-Log "Step 3: Skipping pre-deployment backup as requested."
}

# 4. Pull latest code
if (-not $SkipPull -and (Test-Path (Join-Path $ProjectDir ".git"))) {
    Write-Log "Step 4: Pulling latest changes from Git..."
    try {
        git pull --ff-only
    } catch {
        Write-Log "WARNING: Git pull failed or branch diverged. Continuing with local codebase."
    }
} else {
    Write-Log "Step 4: Skipping Git pull."
}

# 5. Build production Docker images
Write-Log "Step 5: Building production Docker images..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 6. Start infrastructure
Write-Log "Step 6: Starting core infrastructure (PostgreSQL & Redis)..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres redis

# 7. Wait for PostgreSQL
Write-Log "Step 7: Waiting for PostgreSQL readiness..."
$MaxTries = 30
$Count = 0
$Ready = $false
while (-not $Ready -and $Count -lt $MaxTries) {
    Start-Sleep -Seconds 2
    $Count++
    docker exec intelliflow_postgres pg_isready -U intelliflow_user -d intelliflow 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $Ready = $true
    }
}
if (-not $Ready) {
    Write-Err "PostgreSQL did not become healthy in time."
    exit 1
}
Write-Log "PostgreSQL is healthy and accepting connections."

# 8. Run Alembic database migrations
Write-Log "Step 8: Applying pending Alembic database migrations..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 9. Start application services
Write-Log "Step 9: Launching all application services..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 10. Wait for health verification
Write-Log "Step 10: Verifying backend health..."
Start-Sleep -Seconds 5
$HealthOk = $false
for ($i = 1; $i -le 20; $i++) {
    docker exec intelliflow_backend curl -sf http://127.0.0.1:8000/health 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $HealthOk = $true
        break
    }
    Write-Log "Waiting for backend health probe ($i/20)..."
    Start-Sleep -Seconds 3
}

if (-not $HealthOk) {
    Write-Err "Backend failed health check. Inspect 'docker compose logs backend'."
    exit 1
}

Write-Log "===================================================================="
Write-Log "🎉 DEPLOYMENT SUCCESSFUL"
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
Write-Log "===================================================================="
