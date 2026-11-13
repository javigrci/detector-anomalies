"""Entorno de Alembic: la URL sale de la configuración, nunca de un archivo versionado."""

from alembic import context
from sqlalchemy import create_engine, pool

from security_anomaly.core.config import load_settings

config = context.config
target_metadata = None  # Los modelos de negocio llegan en el incremento 2.


def run_migrations_offline() -> None:
    url = load_settings().database_url.get_secret_value()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = load_settings()
    engine = create_engine(
        settings.database_url.get_secret_value(),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": settings.db_connect_timeout_s},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
