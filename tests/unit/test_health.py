"""FR-000-07 y FR-000-09: /health indica proceso vivo, sin base de datos y sin credenciales."""

import pytest
from fastapi.testclient import TestClient

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings

UNREACHABLE = {"DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/db"}


def test_health_is_ok_without_touching_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def _must_not_be_called(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("/health no debe consultar la base de datos")

    monkeypatch.setattr("security_anomaly.api.routes.health.check_database", _must_not_be_called)
    client = TestClient(create_app(load_settings(UNREACHABLE)))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_public_and_outside_api_prefix() -> None:
    client = TestClient(create_app(load_settings(UNREACHABLE)))
    assert client.get("/health").status_code == 200  # sin cabeceras de autenticación
    assert client.get("/api/v1/health").status_code == 404
