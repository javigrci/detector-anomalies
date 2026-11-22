"""Entorno de Alembic: usa el rol migrador (`MIGRATION_DATABASE_URL`), nunca `DATABASE_URL`.

La URL sale de la configuración, no de un archivo versionado, y la API no recibe esa variable
(FR-002-22). El servicio nunca migra al arrancar.
"""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from security_anomaly.storage.config import load_migration_settings
from security_anomaly.storage.schema import metadata

config = context.config
target_metadata = metadata


def _connect_timeout() -> int:
    raw = os.environ.get("DB_CONNECT_TIMEOUT_S", "").strip()
    return int(raw) if raw.isdigit() and 1 <= int(raw) <= 30 else 2


def _url() -> str:
    return load_migration_settings().migration_database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        _url(),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": _connect_timeout()},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
