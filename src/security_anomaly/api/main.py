"""Fábrica de la aplicación FastAPI."""

from fastapi import FastAPI

from security_anomaly.api.errors import register_error_handlers
from security_anomaly.api.routes import health
from security_anomaly.core.config import Settings, load_settings
from security_anomaly.core.logging import configure_logging
from security_anomaly.core.request_id import RequestIdMiddleware
from security_anomaly.storage.database import create_db_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    """Crea la aplicación; sin ``settings`` los carga del entorno."""
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Security Log Anomaly Detector", version="0.1.0")
    app.state.settings = settings
    app.state.engine = create_db_engine(settings)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    return app
