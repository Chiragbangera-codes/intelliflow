"""
IntelliFlow AI — FastAPI application factory.

This module creates and configures the FastAPI application instance.

Responsibilities:
  - Configure logging (must be first)
  - Register all API routers
  - Configure CORS, Request Correlation, and Security Headers middleware
  - Register global standardized exception handlers (Error Envelope)
  - Manage application lifespan (startup settings validation / shutdown cleanups)
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.admin import router as admin_router
from app.api.v1.ai import router as ai_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.automations import router as automations_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.departments import router as departments_router
from app.api.v1.documents import router as documents_router
from app.api.v1.employees import router as employees_router
from app.api.v1.events import router as events_router
from app.api.v1.health import router as health_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.reports import router as reports_router
from app.api.v1.search import router as search_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.workflows import router as workflows_router
from app.core.config import settings, validate_runtime_configuration
from app.core.logging import configure_logging
from app.core.redis import close_redis
from app.middleware import (
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
    get_current_request_id,
)

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
    """
    logger.info(
        "Starting %s v%s [env: %s]",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
    )

    # 1. Validate runtime settings
    try:
        warnings = validate_runtime_configuration(settings)
        for w in warnings:
            logger.warning("CONFIG WARNING: %s", w)
    except Exception as exc:
        logger.error("FATAL CONFIGURATION ERROR: %s", exc)
        raise

    # 2. Warm up FAISS vector store (self-healing for cloud ephemeral environments)
    try:
        from app.services.vector_store_service import warm_up_vector_store

        await warm_up_vector_store()
    except Exception as exc:
        logger.warning("FAISS vector store startup warm-up warning (non-fatal): %s", exc)

    yield

    # 2. Cleanup resources on shutdown
    logger.info("Shutting down %s", settings.APP_NAME)
    await close_redis()


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
        lifespan=lifespan,
    )

    _configure_middleware(application)
    _configure_cors(application)
    _register_routers(application)
    _register_exception_handlers(application)

    return application


def _configure_middleware(application: FastAPI) -> None:
    """Register custom correlation and security headers middleware."""
    application.add_middleware(CorrelationIdMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)


def _configure_cors(application: FastAPI) -> None:
    """
    Configure Cross-Origin Resource Sharing (CORS).
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
    """
    # Health check — mounted at root and /api/v1 for probe flexibility
    application.include_router(health_router)

    # API v1 routers
    _API_V1_PREFIX = "/api/v1"
    application.include_router(health_router, prefix=_API_V1_PREFIX)
    application.include_router(auth_router, prefix=_API_V1_PREFIX)

    # Core Application APIs
    application.include_router(dashboard_router, prefix=_API_V1_PREFIX)
    application.include_router(departments_router, prefix=_API_V1_PREFIX)
    application.include_router(employees_router, prefix=_API_V1_PREFIX)
    application.include_router(documents_router, prefix=_API_V1_PREFIX)
    application.include_router(ocr_router, prefix=_API_V1_PREFIX)

    # Semantic Search & AI Chat
    application.include_router(search_router, prefix=_API_V1_PREFIX)
    application.include_router(ai_router, prefix=_API_V1_PREFIX)

    # Admin Management & Observability
    application.include_router(admin_router, prefix=_API_V1_PREFIX)

    # Workflow Engine
    application.include_router(workflows_router, prefix=_API_V1_PREFIX)

    # Analytics, Predictions, Reports
    application.include_router(analytics_router, prefix=_API_V1_PREFIX)
    application.include_router(predictions_router, prefix=_API_V1_PREFIX)
    application.include_router(reports_router, prefix=_API_V1_PREFIX)

    # Notifications
    application.include_router(notifications_router, prefix=_API_V1_PREFIX)

    # Enterprise Integrations, Webhooks, Automations & Events (Milestone 13)
    application.include_router(integrations_router, prefix=_API_V1_PREFIX)
    application.include_router(webhooks_router, prefix=_API_V1_PREFIX)
    application.include_router(automations_router, prefix=_API_V1_PREFIX)
    application.include_router(events_router, prefix=_API_V1_PREFIX)


_STATUS_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "AUTHENTICATION_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "RESOURCE_NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def _register_exception_handlers(application: FastAPI) -> None:
    """
    Register global exception handlers returning consistent JSON error envelopes.
    """

    @application.exception_handler(StarletteHTTPException)
    @application.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException | StarletteHTTPException,
    ) -> JSONResponse:
        """
        Handle HTTP exceptions with standard error envelope.
        """
        request_id = getattr(request.state, "request_id", get_current_request_id())
        headers = dict(exc.headers or {})
        if request_id:
            headers["X-Request-ID"] = request_id

        origin = request.headers.get("origin")
        if origin and origin in settings.cors_origins_list:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"

        msg = exc.detail if isinstance(exc.detail, str) else "Request failed"
        err_code = _STATUS_CODE_MAP.get(exc.status_code, "ERROR")

        content = {
            "success": False,
            "message": msg,
            "detail": exc.detail,
            "error": {
                "code": err_code,
                "message": msg,
                "request_id": request_id,
                "details": exc.detail if not isinstance(exc.detail, str) else None,
            },
        }

        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content=content,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """
        Handle validation errors (422) with standard error envelope.
        """
        request_id = getattr(request.state, "request_id", get_current_request_id())
        headers: dict[str, str] = {}
        if request_id:
            headers["X-Request-ID"] = request_id

        origin = request.headers.get("origin")
        if origin and origin in settings.cors_origins_list:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"

        errors = jsonable_encoder(exc.errors())
        msg = "Request validation failed."
        if errors and len(errors) > 0:
            first_err = errors[0]
            loc = " -> ".join(str(elem) for elem in first_err.get("loc", []))
            msg = f"Validation error at {loc}: {first_err.get('msg')}"

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers=headers,
            content={
                "success": False,
                "message": msg,
                "detail": errors,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": msg,
                    "request_id": request_id,
                    "details": errors,
                },
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """
        Catch-all handler for unexpected exceptions.
        """
        request_id = getattr(request.state, "request_id", get_current_request_id())
        logger.exception(
            "[%s] Unhandled exception on %s %s: %s",
            request_id,
            request.method,
            request.url.path,
            exc,
        )
        headers: dict[str, str] = {}
        if request_id:
            headers["X-Request-ID"] = request_id

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
                "detail": "Internal server error",
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                    "request_id": request_id,
                    "details": None,
                },
            },
        )


# =============================================================================
# Module-level app instance consumed by Uvicorn
# =============================================================================
app: FastAPI = create_application()
