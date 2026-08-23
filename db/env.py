"""Alembic environment.

The DSN comes from OFFICE_ADMIN_DSN, never from alembic.ini, so a credential is
never committed. Migrations run as the owner; office_app is created by 0002 and
is not used here.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _dsn() -> str:
    dsn = os.environ.get("OFFICE_ADMIN_DSN")
    if not dsn:
        raise RuntimeError(
            "OFFICE_ADMIN_DSN is not set. Copy .env.example to .env and fill it in, "
            "or export it in the environment."
        )
    # One DSN serves psql, psycopg and SQLAlchemy. Only SQLAlchemy needs the
    # driver named, and it defaults to psycopg2 - which this project does not use.
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+psycopg://", 1)
    return dsn


def run_migrations_offline() -> None:
    context.configure(
        url=_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _dsn()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
