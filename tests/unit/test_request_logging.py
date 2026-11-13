"""FR-000-05 y FR-000-06: un registro JSON por petición, con el mismo request_id y sin secretos."""

import json

import pytest
from fastapi.testclient import TestClient

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings

SETTINGS = load_settings(
    {"DATABASE_URL": "postgresql+psycopg://leakuser:leakpass@127.0.0.1:1/leakdb"}
)


def _records(out: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def test_one_json_record_per_request_with_matching_id(capsys: pytest.CaptureFixture[str]) -> None:
    client = TestClient(create_app(SETTINGS))
    response = client.get("/no-existe", headers={"X-Request-ID": "trace-1"})
    requests = [r for r in _records(capsys.readouterr().out) if r["message"] == "request"]
    assert len(requests) == 1
    record = requests[0]
    assert record["request_id"] == "trace-1"
    assert record["method"] == "GET"
    assert record["path"] == "/no-existe"
    assert record["status"] == 404
    assert response.headers["X-Request-ID"] == "trace-1"
    assert response.json()["request_id"] == "trace-1"


def test_sensitive_data_is_never_logged(capsys: pytest.CaptureFixture[str]) -> None:
    client = TestClient(create_app(SETTINGS))
    client.get(
        "/ready?token=SECRETQUERY",
        headers={
            "Authorization": "Bearer SECRETBEARER",
            "Cookie": "session=SECRETCOOKIE",
            "X-Request-ID": "trace-2",
        },
    )
    # El cliente de pruebas (httpx) registra la URL de su propia petición; solo importa lo que
    # emite la aplicación.
    app_lines = [
        json.dumps(record)
        for record in _records(capsys.readouterr().out)
        if str(record["logger"]).startswith("security_anomaly")
    ]
    out = "\n".join(app_lines)
    assert "trace-2" in out
    for secret in (
        "SECRETQUERY",
        "SECRETBEARER",
        "SECRETCOOKIE",
        "leakpass",
        "leakuser",
        "leakdb",
    ):
        assert secret not in out


def test_unhandled_error_is_logged_with_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(SETTINGS)

    @app.get("/_test/boom")
    def boom() -> None:
        raise RuntimeError("fallo")

    TestClient(app, raise_server_exceptions=False).get(
        "/_test/boom", headers={"X-Request-ID": "trace-3"}
    )
    records = _records(capsys.readouterr().out)
    errors = [r for r in records if r["message"] == "unhandled_exception"]
    assert errors
    assert errors[0]["request_id"] == "trace-3"
