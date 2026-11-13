"""FR-000-08: /ready depende de la base de datos y el arranque tolera que esté caída."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings
from security_anomaly.storage import database

UNREACHABLE = {
    "DATABASE_URL": "postgresql+psycopg://leakuser:leakpass@127.0.0.1:1/leakdb",
    "DB_CONNECT_TIMEOUT_S": "3",
}


def test_app_starts_with_database_down() -> None:
    app = create_app(load_settings(UNREACHABLE))  # no debe lanzar
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_ready_returns_503_with_safe_envelope_when_database_is_down() -> None:
    with TestClient(create_app(load_settings(UNREACHABLE))) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "not_ready"
    assert body["details"] == {"checks": {"database": "unavailable"}}
    assert set(body) == {"code", "message", "request_id", "details"}
    for forbidden in ("leakuser", "leakpass", "leakdb", "127.0.0.1", "refused", "psycopg"):
        assert forbidden not in response.text


def test_engine_uses_configured_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_create_engine(url: str, **kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_engine", _fake_create_engine)
    database.create_db_engine(load_settings(UNREACHABLE))
    assert captured["connect_args"]["connect_timeout"] == 3
    assert captured["pool_pre_ping"] is True


def test_check_database_returns_false_instead_of_raising() -> None:
    engine = database.create_db_engine(load_settings(UNREACHABLE))
    assert database.check_database(engine) is False
