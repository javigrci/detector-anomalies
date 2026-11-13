"""Punto de entrada: ``python -m security_anomaly`` (FR-000-03)."""

import sys

import uvicorn

from security_anomaly.api.main import create_app
from security_anomaly.core.config import ConfigError, load_settings


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    app = create_app(settings)
    # 0.0.0.0 es necesario dentro del contenedor; Compose publica el puerto solo en 127.0.0.1.
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=settings.api_port,
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
