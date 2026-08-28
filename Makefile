# =============================================================================
# IntelliFlow AI — Makefile
#
# Provides convenient shortcuts for common development tasks.
# Usage: make <target>
# =============================================================================

.PHONY: help up down restart logs ps build \
        migrate migrate-create migrate-history \
        backend-shell backend-lint backend-test \
        frontend-shell frontend-lint \
        clean

# Default target — show help
help:
	@echo ""
	@echo "IntelliFlow AI — Available Commands"
	@echo "======================================"
	@echo ""
	@echo "  Docker:"
	@echo "    make up              Start all services (detached)"
	@echo "    make down            Stop all services"
	@echo "    make restart         Restart all services"
	@echo "    make build           Rebuild all Docker images"
	@echo "    make logs            Tail logs for all services"
	@echo "    make ps              Show running containers"
	@echo ""
	@echo "  Database:"
	@echo "    make migrate         Run pending Alembic migrations"
	@echo "    make migrate-create  Create a new migration (MSG=<description>)"
	@echo "    make migrate-history Show migration history"
	@echo ""
	@echo "  Backend:"
	@echo "    make backend-lint    Run Ruff + mypy linters"
	@echo "    make backend-test    Run pytest test suite"
	@echo "    make backend-shell   Open shell in backend container"
	@echo ""
	@echo "  Frontend:"
	@echo "    make frontend-lint   Run ESLint"
	@echo "    make frontend-shell  Open shell in frontend container"
	@echo ""
	@echo "  Utilities:"
	@echo "    make clean           Remove stopped containers and volumes"
	@echo ""

# -----------------------------------------------------------------------------
# Docker
# -----------------------------------------------------------------------------
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

ps:
	docker compose ps

# -----------------------------------------------------------------------------
# Database Migrations (Alembic)
# -----------------------------------------------------------------------------
migrate:
	docker compose exec backend alembic upgrade head

migrate-create:
	@if [ -z "$(MSG)" ]; then echo "Usage: make migrate-create MSG='description'"; exit 1; fi
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

migrate-history:
	docker compose exec backend alembic history --verbose

# -----------------------------------------------------------------------------
# Backend
# -----------------------------------------------------------------------------
backend-lint:
	docker compose exec backend ruff check app tests
	docker compose exec backend mypy app

backend-test:
	docker compose exec backend pytest tests/ -v --tb=short

backend-shell:
	docker compose exec backend /bin/bash

# -----------------------------------------------------------------------------
# Frontend
# -----------------------------------------------------------------------------
frontend-lint:
	docker compose exec frontend npm run lint

frontend-shell:
	docker compose exec frontend /bin/sh

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
clean:
	docker compose down -v --remove-orphans
	docker system prune -f
