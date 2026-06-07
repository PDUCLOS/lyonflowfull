"""Alembic env — LyonFlowFull.

Configure Alembic pour utiliser notre config + DB.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool


# Ajouter le workspace au path
WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))

# Import des settings + Base
from src.config import get_settings  # noqa: E402


# Config Alembic
config = context.config

# Override URL avec env var
settings = get_settings()
config.set_main_option(
    "sqlalchemy.url",
    f"postgresql://{settings.db.user}:{settings.db.password}"
    f"@{settings.db.host}:{settings.db.port}/{settings.db.db}",
)

# Config logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata pour autogenerate (optionnel — on peut juste gérer le init-db.sql à la main)
target_metadata = None  # Si on utilise raw SQL : target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations en mode offline (génère SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations en mode online (connecte à la DB)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
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
