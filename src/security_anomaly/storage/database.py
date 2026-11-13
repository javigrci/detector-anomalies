"""Acceso a PostgreSQL: motor perezoso y comprobación de conectividad (research R4)."""

import logging

from sqlalchemy import Engine, create_engine, text

from security_anomaly.core.config import Settings

logger = logging.getLogger(__name__)


def create_db_engine(settings: Settings) -> Engine:
    """Crea el motor sin conectar: el servicio arranca aunque la base de datos esté caída."""
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_s},
    )


def check_database(engine: Engine) -> bool:
    """True si la base de datos responde; nunca propaga la excepción ni la registra con detalle."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("database_unavailable", extra={"fields": {"error_type": type(exc).__name__}})
        return False
    return True
