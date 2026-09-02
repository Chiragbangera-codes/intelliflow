# IntelliFlow AI — Production Deployment Guide

**Target Environment:** Linux / Cloud VPS / Bare Metal / Container Cluster  
**Docker Runtime:** Docker Engine 24.0+ & Docker Compose V2  
**Architecture:** Next.js (Frontend) + FastAPI (Backend) + Celery (Workers) + PostgreSQL 16 + Redis 7 + Ollama (LLM)  

---

## 1. Architecture Overview

```text
                                INTERNET
                                   │
                                   ▼
                         HTTPS / TLS Reverse Proxy
                         (Nginx / Caddy / Traefik)
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
                     ▼ :80 / :3000               ▼ :8000 /api/v1
           ┌───────────────────┐       ┌───────────────────┐
           │ Next.js Frontend  │       │  FastAPI Backend  │
           │  (SSR Standalone) │       │   (4 Gunicorn/    │
           └───────────────────┘       │   Uvicorn Workers)│
                                       └─────────┬─────────┘
                                                 │
                     ┌───────────────────────────┼───────────────────────────┐
                     │                           │                           │
                     ▼                           ▼                           ▼
           ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
           │   PostgreSQL 16   │       │      Redis 7      │       │    Celery Worker  │
           │ (Internal Network)│       │ (Broker + Cache)  │       │(Background Tasks) │
           └───────────────────┘       └───────────────────┘       └───────────────────┘
                                                 │
                                                 ▼
                                       ┌───────────────────┐
                                       │   Ollama Local    │
                                       │  (LLM Inference)  │
                                       └───────────────────┘
```

---

## 2. Server Prerequisites

1. **Hardware Requirements:**
   - Minimum: 4 vCPU, 8 GB RAM, 50 GB SSD
   - Recommended: 8 vCPU, 16 GB RAM, 100 GB NVMe SSD (for Ollama model loading)
2. **Software Dependencies:**
   - Ubuntu 22.04 LTS / Debian 12 / RHEL 9
   - Docker Engine (`v24.0+`) & Docker Compose (`v2.20+`)
   - `git`, `curl`, `gzip`, `openssl`
3. **Firewall (UFW / iptables):**
   - Inbound `80/tcp` (HTTP -> Redirect to HTTPS)
   - Inbound `443/tcp` (HTTPS)
   - Inbound `22/tcp` (SSH)
   - **DO NOT** open ports 5432 (PostgreSQL) or 6379 (Redis) to the public internet.

---

## 3. Environment & Secret Provisioning

Clone the repository and prepare the production environment:

```bash
git clone https://github.com/your-org/intelliflow.git /opt/intelliflow
cd /opt/intelliflow
cp .env.example .env
```

Generate cryptographically secure values and populate `.env`:

```bash
# 1. JWT Secret Key (64-character hex)
JWT_SECRET=$(openssl rand -hex 32)

# 2. PostgreSQL Password
PG_PASS=$(openssl rand -base64 32)

# 3. Integration Encryption Key (Fernet 32-byte urlsafe base64)
INTEG_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# 4. Webhook Signing Secret (64-character hex)
WH_SECRET=$(openssl rand -hex 32)
```

Configure the following variables in `/opt/intelliflow/.env`:

```env
APP_ENV=production
APP_DEBUG=false

# Domain & CORS
CORS_ORIGINS=https://app.yourdomain.com,https://api.yourdomain.com
COOKIE_SECURE=true
COOKIE_SAMESITE=strict

# Database
POSTGRES_USER=intelliflow_user
POSTGRES_PASSWORD=<INSERT_GENERATED_PG_PASS>
POSTGRES_DB=intelliflow
DATABASE_URL=postgresql+asyncpg://intelliflow_user:<INSERT_GENERATED_PG_PASS>@postgres:5432/intelliflow
DATABASE_SYNC_URL=postgresql://intelliflow_user:<INSERT_GENERATED_PG_PASS>@postgres:5432/intelliflow

# Cryptographic Keys
JWT_SECRET_KEY=<INSERT_GENERATED_JWT_SECRET>
INTEGRATION_ENCRYPTION_KEY=<INSERT_GENERATED_INTEG_KEY>
WEBHOOK_SIGNING_SECRET=<INSERT_GENERATED_WH_SECRET>

# Frontend
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
```

---

## 4. Production Deployment Execution

Run the automated deployment script:

```bash
chmod +x scripts/deploy.sh scripts/backup_database.sh scripts/restore_database.sh
./scripts/deploy.sh
```

The script automatically:
1. Validates environment configurations and fails fast if insecure settings are found.
2. Creates a pre-deployment database backup.
3. Builds production Docker images (without development reload or host volume mounts).
4. Launches PostgreSQL and Redis, waiting for health checks.
5. Runs `alembic upgrade head` to apply database schema migrations.
6. Starts FastAPI backend (4 workers), Celery workers, Next.js frontend, and Ollama.
7. Executes health probes against `http://127.0.0.1:8000/health`.

---

## 5. Reverse Proxy & TLS Configuration

### Option A: Caddy (Recommended — Automatic TLS)

Create `/etc/caddy/Caddyfile`:

```caddyfile
app.yourdomain.com {
    reverse_proxy localhost:3000
    encode zstd gzip
}

api.yourdomain.com {
    reverse_proxy localhost:8000
    encode zstd gzip
}
```

Start Caddy:
```bash
sudo systemctl restart caddy
```

### Option B: Nginx + Certbot

```nginx
server {
    listen 80;
    server_name app.yourdomain.com api.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name app.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/app.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 6. Model Initialization (Ollama LLM)

If utilizing local LLM capabilities, pull the required model into the persistent Ollama volume:

```bash
docker exec intelliflow_ollama ollama pull llama3.2:1b
```

---

## 7. Production Operations & Monitoring

### Viewing Logs
```bash
# All services
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100

# Specific service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker
```

### Checking System Health
```bash
# Multi-tier readiness endpoint
curl -s http://127.0.0.1:8000/api/v1/health/ready | jq .

# Admin telemetry endpoint
curl -s -H "Authorization: Bearer <ADMIN_TOKEN>" http://127.0.0.1:8000/api/v1/admin/system/metrics | jq .
```

### Routine Upgrades
```bash
cd /opt/intelliflow
./scripts/deploy.sh
```
