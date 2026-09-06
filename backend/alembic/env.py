"""
Alembic environment configuration.

Connects Alembic's migration runner to the application's Settings and
ORM models so that:
  - Credentials come from environment variables (not alembic.ini)
  - Autogenerate detects schema changes by inspecting Base.metadata
  - All models are visible to migrations by importing them here

To create a new migration:
    alembic revision --autogenerate -m "description"

To apply pending migrations:
    alembic upgrade head

Migration naming convention (per DATABASE_SCHEMA.md §11):
    001_auth
    002_database_schema
    003_*  (future milestones)
"""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# ---------------------------------------------------------------------------
# Import all models so Alembic can detect them in autogenerate mode.
# Import order follows FK dependencies (parents before children).
# ---------------------------------------------------------------------------

# Milestone 2 — auth models
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.user import User  # noqa: F401

# Milestone 3 — database schema models
from app.models.ai_conversation import AIConversation  # noqa: F401
from app.models.ai_embedding import AIEmbedding  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.department import Department  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.models.employee_profile import EmployeeProfile  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.prediction import Prediction  # noqa: F401
from app.models.report import Report  # noqa: F401
from app.models.setting import Setting  # noqa: F401
from app.models.workflow import Workflow  # noqa: F401
from app.models.workflow_execution import WorkflowExecution  # noqa: F401
from app.models.workflow_step import WorkflowStep  # noqa: F401

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Override the database URL from Settings so credentials are never in alembic.ini
config.set_main_option("sqlalchemy.url", settings.DATABASE_SYNC_URL.replace("%", "%%"))

# Setup loggers defined in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Metadata used for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This generates SQL scripts without a live database connection.
    Useful for producing migration scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode with a live database connection.

    This is the standard mode used during `alembic upgrade head`.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling for migration runs
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
