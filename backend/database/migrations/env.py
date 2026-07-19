"""
env.py

Alembic Migration Environment — Lavender Trinetra Platform (PostgreSQL)
=====================================================================

Configures Alembic to run against the platform's PostgreSQL database,
reading the connection string exclusively from DATABASE_URL in .env
(never hard-coded here or in alembic.ini). Targets the SQLAlchemy
declarative metadata defined in database/models.py via database/database.py
so that `alembic revision --autogenerate` can detect schema changes.

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# =====================================================================
# PATH SETUP
# =====================================================================

# Ensure the backend package root is importable (this file lives at
# backend/database/migrations/env.py; backend/ must be on sys.path).
BACKEND_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# =====================================================================
# ENVIRONMENT / DATABASE_URL
# =====================================================================

# Load variables from .env at the backend root (does not override
# variables already present in the real environment, e.g. in CI/CD).
load_dotenv(os.path.join(BACKEND_ROOT, ".env"))

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Define it in backend/.env "
        "(e.g. postgresql+psycopg2://user:password@host:5432/lavender_trinetra) "
        "before running Alembic."
    )

if DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy 1.4+/2.x requires the postgresql:// scheme.
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# =====================================================================
# ALEMBIC CONFIG
# =====================================================================

config = context.config

# Inject the resolved DATABASE_URL into Alembic's config object so both
# offline and online migration modes use the same connection string.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# =====================================================================
# TARGET METADATA
# =====================================================================

try:
    from database.database import Base
    import database.models  # noqa: F401  (registers all models on Base.metadata)
except ImportError as exc:  # pragma: no cover - defensive
    raise RuntimeError(
        "Failed to import Base/models for Alembic autogenerate support. "
        "Ensure backend/ is on sys.path and database/models.py has no import errors."
    ) from exc

target_metadata = Base.metadata


# =====================================================================
# MIGRATION RUNNERS
# =====================================================================

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — emits SQL to stdout/a script
    rather than executing against a live connection. Useful for
    generating SQL for manual review or DBA execution.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        logger.info("Running migrations offline against target metadata.")
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects directly to the
    PostgreSQL database defined by DATABASE_URL and applies migrations.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            logger.info("Running migrations online against %s.", connectable.url.database)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()