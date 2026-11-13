"""FR-000-10: formato de error único y sin detalles internos."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings

SETTINGS = load_settings({"DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/db"})
KEYS = {"code", "message", "request_id", "details"}


class _Body(BaseModel):
    number: int


def _app() -> FastAPI:
    app = create_app(SETTINGS)

    @app.post("/_test/validate")
    def validate(body: _Body) -> dict[str, int]:
        return {"number": body.number}

    @app.get("/_test/boom")
    def boom() -> None:
        raise RuntimeError("secreto-interno-no-visible")

    return app


def _assert_envelope(body: dict[str, object], code: str) -> None:
    assert set(body) == KEYS
    assert body["code"] == code
    assert isinstance(body["message"], str)
    assert isinstance(body["request_id"], str)
    assert isinstance(body["details"], dict)


def test_not_found_uses_envelope() -> None:
    response = TestClient(_app()).get("/no-existe")
    assert response.status_code == 404
    _assert_envelope(response.json(), "not_found")


def test_method_not_allowed_uses_envelope() -> None:
    response = TestClient(_app()).put("/_test/validate")
    assert response.status_code == 405
    _assert_envelope(response.json(), "method_not_allowed")


def test_validation_error_uses_envelope_without_input_echo() -> None:
    response = TestClient(_app()).post("/_test/validate", json={"number": "valor-secreto"})
    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, "validation_error")
    assert "valor-secreto" not in response.text


def test_unhandled_error_hides_internal_details() -> None:
    client = TestClient(_app(), raise_server_exceptions=False)
    response = client.get("/_test/boom")
    assert response.status_code == 500
    _assert_envelope(response.json(), "internal_error")
    assert "secreto-interno-no-visible" not in response.text
    assert "Traceback" not in response.text
