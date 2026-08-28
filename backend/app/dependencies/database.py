"""
Database dependency injection.

Provides an async database session to FastAPI route handlers via Depends().
The session is properly closed after each request, even on exceptions.

Usage in a route:
    from app.dependencies.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        result = await db.execute(...)
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session for the duration of a request.

    The `async with` block guarantees the session is closed and returned
    to the connection pool regardless of whether the request succeeds or fails.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
