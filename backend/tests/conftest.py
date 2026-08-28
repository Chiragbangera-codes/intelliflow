"""
pytest fixtures shared across the test suite.

Milestone 2 provides:
  - `client`              — Sync FastAPI TestClient (preserved from Milestone 1)
  - `async_client`        — Async HTTPX client with DB override
  - `db_session`          — Isolated async database session per test function
  - `seed_roles`          — Seeds the 5 default roles
  - `test_user`           — Function-scoped: creates + cleans up a test user
  - `auth_headers`        — Authorization headers for an active test user
  - `admin_user`          — Function-scoped: test user with admin role
  - `suspended_user`      — Function-scoped: test user with suspended status
  - `inactive_user`       — Function-scoped: test user with inactive status
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.core.security import create_access_token, hash_password
from app.dependencies.database import get_db
from app.main import app
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.role import Role
from app.models.user import User, UserStatus

# ---------------------------------------------------------------------------
# Test engine — uses DATABASE_URL or SQLite in-memory fallback for unit tests
# ---------------------------------------------------------------------------
_db_url = os.getenv("TEST_DATABASE_URL", settings.DATABASE_URL)
# If default postgres:5432 is unreachable in local non-docker environment, fallback to sqlite
if "postgres:5432" in _db_url and not os.getenv("CI"):
    _db_url = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    _db_url,
    echo=False,
)

_TestSessionLocal = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Function-scoped database setup (on-demand when db_session is requested)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def setup_database() -> AsyncGenerator[None, None]:
    """
    Create all tables before each test function and drop them after.
    Guarantees clean database isolation between tests.
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def seed_roles(setup_database: None) -> None:
    """
    Seed the five default roles into the test database.
    """
    role_data = [
        {
            "id": uuid.UUID("00000000-0000-4000-8000-000000000001"),
            "name": "admin",
            "description": "System administrator",
        },
        {
            "id": uuid.UUID("00000000-0000-4000-8000-000000000002"),
            "name": "manager",
            "description": "Department manager",
        },
        {
            "id": uuid.UUID("00000000-0000-4000-8000-000000000003"),
            "name": "employee",
            "description": "Standard employee",
        },
        {
            "id": uuid.UUID("00000000-0000-4000-8000-000000000004"),
            "name": "hr",
            "description": "Human resources",
        },
        {
            "id": uuid.UUID("00000000-0000-4000-8000-000000000005"),
            "name": "finance",
            "description": "Finance department",
        },
    ]
    async with _TestSessionLocal() as session:
        for rd in role_data:
            existing = await session.get(Role, rd["id"])
            if existing is None:
                session.add(Role(**rd))
        await session.commit()


@pytest_asyncio.fixture(scope="function")
async def db_session(seed_roles: None) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a fresh async database session for each test function.
    """
    async with _TestSessionLocal() as session:
        yield session
        await session.close()


# ---------------------------------------------------------------------------
# FastAPI client fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Return a synchronous TestClient (preserved from Milestone 1).
    """
    return TestClient(app)


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Return an async HTTPX client with the database session overridden.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test user fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> AsyncGenerator[User, None]:
    """
    Create an active employee test user for each test function.
    """
    employee_role_id = uuid.UUID("00000000-0000-4000-8000-000000000003")
    unique_email = f"testuser_{uuid.uuid4().hex[:8]}@example.com"

    user = User(
        email=unique_email,
        password_hash=hash_password("TestPass1!"),
        first_name="Test",
        last_name="User",
        role_id=employee_role_id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    yield user


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> AsyncGenerator[User, None]:
    """Create an active admin test user."""
    admin_role_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
    unique_email = f"admin_{uuid.uuid4().hex[:8]}@example.com"

    user = User(
        email=unique_email,
        password_hash=hash_password("AdminPass1!"),
        first_name="Admin",
        last_name="User",
        role_id=admin_role_id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    yield user


@pytest_asyncio.fixture(scope="function")
async def suspended_user(db_session: AsyncSession) -> AsyncGenerator[User, None]:
    """Create a suspended test user."""
    employee_role_id = uuid.UUID("00000000-0000-4000-8000-000000000003")
    unique_email = f"suspended_{uuid.uuid4().hex[:8]}@example.com"

    user = User(
        email=unique_email,
        password_hash=hash_password("SuspendedPass1!"),
        first_name="Suspended",
        last_name="User",
        role_id=employee_role_id,
        status=UserStatus.SUSPENDED,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    yield user


@pytest_asyncio.fixture(scope="function")
async def inactive_user(db_session: AsyncSession) -> AsyncGenerator[User, None]:
    """Create an inactive test user."""
    employee_role_id = uuid.UUID("00000000-0000-4000-8000-000000000003")
    unique_email = f"inactive_{uuid.uuid4().hex[:8]}@example.com"

    user = User(
        email=unique_email,
        password_hash=hash_password("InactivePass1!"),
        first_name="Inactive",
        last_name="User",
        role_id=employee_role_id,
        status=UserStatus.INACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    yield user


# ---------------------------------------------------------------------------
# Auth header fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def auth_headers(test_user: User) -> dict[str, str]:
    """Return Authorization headers for the test user."""
    access_token = create_access_token(
        subject=str(test_user.id),
        role=test_user.role.name if test_user.role else "employee",
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture(scope="function")
def admin_headers(admin_user: User) -> dict[str, str]:
    """Return Authorization headers for the admin test user."""
    access_token = create_access_token(
        subject=str(admin_user.id),
        role=admin_user.role.name if admin_user.role else "admin",
    )
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# Milestone 4 fixtures — HR and Manager users
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def hr_user(db_session: AsyncSession) -> AsyncGenerator[User, None]:
    """Create an active HR test user."""
    hr_role_id = uuid.UUID("00000000-0000-4000-8000-000000000004")
    unique_email = f"hr_{uuid.uuid4().hex[:8]}@example.com"

    user = User(
        email=unique_email,
        password_hash=hash_password("HrPass1!"),
        first_name="HR",
        last_name="User",
        role_id=hr_role_id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    yield user


@pytest.fixture(scope="function")
def hr_headers(hr_user: User) -> dict[str, str]:
    """Return Authorization headers for the HR test user."""
    access_token = create_access_token(
        subject=str(hr_user.id),
        role=hr_user.role.name if hr_user.role else "hr",
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture(scope="function")
async def manager_user(db_session: AsyncSession) -> AsyncGenerator[User, None]:
    """Create an active manager test user."""
    manager_role_id = uuid.UUID("00000000-0000-4000-8000-000000000002")
    unique_email = f"manager_{uuid.uuid4().hex[:8]}@example.com"

    user = User(
        email=unique_email,
        password_hash=hash_password("ManagerPass1!"),
        first_name="Manager",
        last_name="User",
        role_id=manager_role_id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    yield user


@pytest.fixture(scope="function")
def manager_headers(manager_user: User) -> dict[str, str]:
    """Return Authorization headers for the manager test user."""
    access_token = create_access_token(
        subject=str(manager_user.id),
        role=manager_user.role.name if manager_user.role else "manager",
    )
    return {"Authorization": f"Bearer {access_token}"}
