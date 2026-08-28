"""
Logging configuration for IntelliFlow AI.

Sets up structured, leveled logging for the entire application.

Design decisions:
- Uses Python's stdlib `logging` — no additional dependencies.
- Log format includes timestamp, level, and module name for traceability.
- Log level is driven by the Settings object, not hardcoded.
- Never logs passwords, secrets, or JWT tokens (see ENGINEERING_GUIDELINES §11).

Usage:
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Server started")
"""

import logging
import sys

from app.core.config import settings

# Log format follows the structure defined in SYSTEM_ARCHITECTURE §12:
# timestamp | level | module | message
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def configure_logging() -> None:
    """
    Configure the root logger for the application.

    Called once at application startup from main.py.
    Subsequent calls are idempotent — handlers are not duplicated.
    """
    root_logger = logging.getLogger()

    # Avoid adding duplicate handlers on hot-reload
    if root_logger.handlers:
        return

    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    root_logger.setLevel(log_level)

    # Stream handler — writes to stdout (captured by Docker and log aggregators)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root_logger.addHandler(handler)

    # Silence overly verbose third-party loggers in production
    if settings.is_production:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    Args:
        name: Typically __name__ from the calling module.

    Returns:
        A configured Logger instance.
    """
    return logging.getLogger(name)
