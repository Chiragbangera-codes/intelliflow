# IntelliFlow AI

**Enterprise SaaS Platform — AI · Workflow Automation · Document Intelligence · Analytics**

> This is Milestone 1 (Project Foundation). The platform is in active development.

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Getting Started](#getting-started)
5. [Running with Docker](#running-with-docker)
6. [Running Locally (without Docker)](#running-locally-without-docker)
7. [Environment Variables](#environment-variables)
8. [Available Make Commands](#available-make-commands)
9. [API Documentation](#api-documentation)
10. [Running Tests](#running-tests)
11. [CI/CD](#cicd)
12. [Architecture](#architecture)
13. [Development Roadmap](#development-roadmap)

---

## Overview

IntelliFlow AI is a production-grade enterprise SaaS platform that unifies:

- **AI Chat** — RAG-powered assistant over uploaded documents
- **Document Intelligence** — OCR, text extraction, and intelligent search
- **Workflow Automation** — configurable multi-step business workflows
- **Analytics & Predictions** — business dashboards and ML-based forecasting

---

## Tech Stack

| Layer      | Technology                                 |
|------------|--------------------------------------------|
| Frontend   | Next.js 15, React, TypeScript, Tailwind CSS, Shadcn UI |
| Backend    | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Database   | PostgreSQL 16                              |
| Cache      | Redis 7                                    |
| Workers    | Celery                                     |
| DevOps     | Docker, Docker Compose, GitHub Actions      |

---

## Project Structure

```
intelliflow/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI pipeline
├── backend/
│   ├── alembic/                # Database migration scripts
│   │   ├── versions/           # Generated migration files
│   │   └── env.py              # Alembic + SQLAlchemy wiring
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       └── health.py   # GET /health endpoint
│   │   ├── core/
│   │   │   ├── config.py       # Settings via pydantic-settings
│   │   │   ├── database.py     # SQLAlchemy engine & session
│   │   │   └── logging.py      # Structured logging setup
│   │   ├── dependencies/
│   │   │   └── database.py     # get_db() dependency injection
│   │   ├── middleware/         # Custom middleware (future)
│   │   ├── models/             # SQLAlchemy ORM models (Milestone 3+)
│   │   ├── repositories/       # Database access layer (Milestone 3+)
│   │   ├── schemas/
│   │   │   └── health.py       # Pydantic response schemas
│   │   ├── services/           # Business logic layer (Milestone 3+)
│   │   ├── utils/              # Shared utilities
│   │   ├── workers/
│   │   │   └── celery_app.py   # Celery app configuration
│   │   └── main.py             # FastAPI application factory
│   ├── tests/
│   │   ├── conftest.py         # Shared pytest fixtures
│   │   └── test_health.py      # Health endpoint tests
│   ├── alembic.ini             # Alembic configuration
│   ├── Dockerfile              # Multi-stage backend Dockerfile
│   ├── pyproject.toml          # Ruff, Black, mypy, pytest config
│   └── requirements.txt        # Pinned Python dependencies
├── frontend/
│   ├── app/                    # Next.js App Router
│   ├── components/             # Reusable UI components (Milestone 4+)
│   ├── features/               # Feature modules (Milestone 4+)
│   ├── hooks/                  # Custom React hooks
│   ├── services/               # API service layer
│   ├── store/                  # Zustand global state
│   ├── styles/                 # Global CSS
│   ├── types/                  # TypeScript type definitions
│   ├── utils/                  # Frontend utilities
│   ├── Dockerfile              # Multi-stage frontend Dockerfile
│   └── package.json
├── Docs/                       # Project documentation (source of truth)
├── .env.example                # Environment variable template
├── .gitignore
├── docker-compose.yml          # All services
└── Makefile                    # Development shortcuts
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 24+
- [Docker Compose](https://docs.docker.com/compose/) (included with Docker Desktop)
- [Git](https://git-scm.com/)

Optional (for local development without Docker):
- Python 3.12+
- Node.js 20+
- PostgreSQL 16
- Redis 7

---

## Running with Docker

This is the recommended way to run the project. Everything starts with one command.

**Step 1 — Clone the repository**

```bash
git clone https://github.com/your-org/intelliflow.git
cd intelliflow
```

**Step 2 — Create your environment file**

```bash
cp .env.example .env
# Edit .env and set strong passwords for POSTGRES_PASSWORD
```

**Step 3 — Start all services**

```bash
docker compose up --build
```

This starts:
| Service   | Port | Description                    |
|-----------|------|--------------------------------|
| frontend  | 3000 | Next.js application            |
| backend   | 8000 | FastAPI application            |
| postgres  | 5432 | PostgreSQL 16 database         |
| redis     | 6379 | Redis cache + Celery broker    |
| worker    | —    | Celery background worker       |

**Step 4 — Verify**

```bash
# Check all containers are healthy
docker compose ps

# Test the health endpoint
curl http://localhost:8000/health
# → {"status":"ok"}

# Open in browser
open http://localhost:3000        # Frontend
open http://localhost:8000/docs  # API documentation (Swagger)
```

---

## Running Locally (without Docker)

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate     # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp ../.env.example ../.env
# Edit .env — set DATABASE_URL and REDIS_URL to point to your local services

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable               | Description                              | Default               |
|------------------------|------------------------------------------|-----------------------|
| `APP_ENV`              | `development` / `staging` / `production` | `development`         |
| `POSTGRES_PASSWORD`    | PostgreSQL password (change this!)       | `change_this_strong_password` |
| `DATABASE_URL`         | Async SQLAlchemy connection string       | points to postgres service |
| `DATABASE_SYNC_URL`    | Sync URL for Alembic migrations          | points to postgres service |
| `REDIS_URL`            | Redis connection string                  | `redis://redis:6379/0` |
| `CELERY_BROKER_URL`    | Celery broker (Redis)                    | `redis://redis:6379/1` |
| `CORS_ORIGINS`         | Comma-separated allowed origins          | `http://localhost:3000` |
| `LOG_LEVEL`            | `DEBUG` / `INFO` / `WARNING` / `ERROR`   | `INFO`                |
| `NEXT_PUBLIC_API_URL`  | Backend API base URL (frontend)          | `http://localhost:8000/api/v1` |

> **Important:** Never commit your `.env` file. It is listed in `.gitignore`.

---

## Available Make Commands

```bash
make help              # Show all available commands

# Docker
make up                # Start all services (detached)
make down              # Stop all services
make build             # Rebuild Docker images
make logs              # Tail service logs
make ps                # Show container status

# Database
make migrate           # Apply pending migrations
make migrate-create MSG="add users table"  # Create a new migration
make migrate-history   # Show migration history

# Backend
make backend-lint      # Run Ruff + mypy
make backend-test      # Run pytest
make backend-shell     # Open backend container shell

# Frontend
make frontend-lint     # Run ESLint
make frontend-shell    # Open frontend container shell

# Utilities
make clean             # Remove containers and volumes
```

---

## API Documentation

When the backend is running, interactive API docs are available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Implemented Endpoints (Milestone 1)

| Method | Path      | Auth | Description       |
|--------|-----------|------|-------------------|
| GET    | `/health` | No   | API health check  |

---

## Running Tests

### Backend Tests

```bash
# Inside Docker
make backend-test

# Locally
cd backend
pytest tests/ -v
```

### Frontend Lint

```bash
# Inside Docker
make frontend-lint

# Locally
cd frontend
npm run lint
```

---

## CI/CD

GitHub Actions runs automatically on every push and pull request to `main` and `develop`:

1. **Frontend Lint** — ESLint + TypeScript type check
2. **Backend Lint** — Ruff + mypy (runs in parallel with frontend lint)
3. **Backend Tests** — pytest with real PostgreSQL and Redis service containers

Configuration: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

---

## Architecture

The system follows **Clean Architecture** with strict layer separation:

```
Browser / Client
      ↓
API Route (FastAPI)     ← Receives request, returns response. No business logic.
      ↓
Service Layer           ← All business logic lives here.
      ↓
Repository Layer        ← Only layer that touches the database.
      ↓
Database (PostgreSQL)
```

See [`Docs/SYSTEM_ARCHITECTURE.md`](Docs/SYSTEM_ARCHITECTURE.md) for the full architecture specification.

---

## Development Roadmap

| Milestone | Description          | Status      |
|-----------|----------------------|-------------|
| 1         | Project Foundation   | ✅ Complete |
| 2         | Authentication       | Planned     |
| 3         | Database Models      | Planned     |
| 4         | Dashboard            | Planned     |
| 5         | Document Management  | Planned     |
| 6         | OCR Engine           | Planned     |
| 7         | AI Assistant         | Planned     |
| 8         | Workflow Engine      | Planned     |
| 9         | Analytics            | Planned     |
| 10        | Notifications        | Planned     |
| 11        | Testing              | Planned     |
| 12        | Deployment           | Planned     |

---

## Contributing

1. Branch from `develop`: `git checkout -b feature/your-feature`
2. Follow the coding standards in [`Docs/CODING_STANDARDS.md`](Docs/CODING_STANDARDS.md)
3. Write tests alongside your feature
4. Open a pull request to `develop`

Commit format: `type(scope): description` (e.g., `feat(auth): implement JWT login`)
