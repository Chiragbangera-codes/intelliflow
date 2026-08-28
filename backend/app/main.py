"""
IntelliFlow AI — FastAPI application factory.

This module creates and configures the FastAPI application instance.

Responsibilities:
  - Configure logging (must be first)
  - Register all API routers
  - Configure CORS middleware
  - Register global exception handlers
  - Manage application lifespan (startup / shutdown)

Architecture note:
  Routers are thin — they receive requests, delegate to services,
  and return responses. Business logic never lives here.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.admin import router as admin_router
from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.departments import router as departments_router
from app.api.v1.documents import router as documents_router
from app.api.v1.employees import router as employees_router
from app.api.v1.health import router as health_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.search import router as search_router
from app.core.config import settings
from app.core.logging import configure_logging

# Configure logging before anything else so all startup messages are captured
configure_logging()

logger = logging.getLogger(__name__)


# =============================================================================
# Lifespan — startup and shutdown events
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application lifecycle.

    Code before `yield` runs on startup.
    Code after `yield` runs on shutdown.

    Future milestones will add:
      - Database connection pool warm-up
      - Redis connection verification
      - FAISS index loading
    """
    logger.info(
        "Starting %s v%s [env: %s]",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
    )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


# =============================================================================
# Application factory
# =============================================================================
def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns a fully configured FastAPI instance ready to be served by Uvicorn.
    """
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "IntelliFlow AI — Enterprise SaaS platform combining AI, "
            "Workflow Automation, Document Intelligence, and Predictive Analytics."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        # Disable Swagger UI and ReDoc in production (access via internal network only)
        # Uncomment for production hardening:
        # docs_url=None if settings.is_production else "/docs",
        # redoc_url=None if settings.is_production else "/redoc",
        lifespan=lifespan,
    )

    _configure_cors(application)
    _register_routers(application)
    _register_exception_handlers(application)

    return application


def _configure_cors(application: FastAPI) -> None:
    """
    Configure Cross-Origin Resource Sharing (CORS).

    Origins are loaded from settings to avoid hardcoded values.
    All origins must be explicitly whitelisted per security guidelines.
    """
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


def _register_routers(application: FastAPI) -> None:
    """
    Register all API routers.

    Health is mounted at root (not /api/v1) so Docker health checks
    and load balancers can probe it without knowing the API prefix.

    Auth and future feature routers are mounted under /api/v1.
    """
    # Health check — no prefix, no auth required
    application.include_router(health_router)

    # API v1 routers
    _API_V1_PREFIX = "/api/v1"
    application.include_router(auth_router, prefix=_API_V1_PREFIX)

    # Milestone 4 — Core Application APIs
    application.include_router(dashboard_router, prefix=_API_V1_PREFIX)
    application.include_router(departments_router, prefix=_API_V1_PREFIX)
    application.include_router(employees_router, prefix=_API_V1_PREFIX)
    application.include_router(documents_router, prefix=_API_V1_PREFIX)
    application.include_router(ocr_router, prefix=_API_V1_PREFIX)

    # Milestone 7 Phase 2 — Semantic Search
    application.include_router(search_router, prefix=_API_V1_PREFIX)

    # Milestone 7 Phase 3 — AI Chat (RAG)
    application.include_router(ai_router, prefix=_API_V1_PREFIX)

    # Phase 3.1 — Admin AI index administration (reindex, status)
    application.include_router(admin_router, prefix=_API_V1_PREFIX)


def _register_exception_handlers(application: FastAPI) -> None:
    """
    Register global exception handlers.

    These handlers ensure errors are never exposed as raw stack traces.
    They return consistent JSON following the API specification envelope.
    """

    @application.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """
        Handle HTTP exceptions and format them according to the API specification.
        """
        headers = dict(exc.headers or {})
        origin = request.headers.get("origin")
        if origin and origin in settings.cors_origins_list:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"

        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={
                "success": False,
                "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
                "detail": exc.detail,
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """
        Catch-all handler for unexpected exceptions.

        Logs the full stack trace internally but returns a safe,
        user-friendly message to the client.
        """
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        headers: dict[str, str] = {}
        origin = request.headers.get("origin")
        if origin and origin in settings.cors_origins_list:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=headers,
            content={
                "success": False,
                "message": "An unexpected error occurred. Please try again later.",
            },
        )


# =============================================================================
# Module-level app instance consumed by Uvicorn
# =============================================================================
app: FastAPI = create_application()
