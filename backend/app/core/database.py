"""
Database engine and session factory.

Provides the async SQLAlchemy engine and session factory used across the
application. All database access goes through the repository layer, not
directly from routes or services.

Design decisions:
- Uses SQLAlchemy 2.0 async API with asyncpg driver.
- `expire_on_commit=False` prevents lazy-load errors after commit since
  the session is closed before the response is serialised by FastAPI.
- Connection pooling is configured conservatively for a single-instance
  Docker deployment; adjust pool_size for horizontal scaling.

Usage:
    # In dependency injection (see dependencies/database.py)
    async with AsyncSessionLocal() as session:
        ...
"""

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.DATABASE_URL,
    # Echo SQL statements in development for debugging; disabled in production
    echo=settings.is_development,
    # Connection pool settings (tuned for a single backend instance)
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Detect stale connections before use
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative base — all SQLAlchemy models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """
    Shared declarative base for all ORM models.

    Future models (Milestone 3+) inherit from this class.
    Alembic's env.py imports Base.metadata to detect schema changes.
    """

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }
