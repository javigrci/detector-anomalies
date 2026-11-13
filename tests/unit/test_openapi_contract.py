"""Contrato de las sondas (contracts/openapi-probes.yaml, research R12)."""

from typing import Any

from fastapi.testclient import TestClient

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings


def _schema() -> dict[str, Any]:
    app = create_app(load_settings({"DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/db"}))
    schema: dict[str, Any] = TestClient(app).get("/openapi.json").json()
    return schema


def test_probes_are_documented() -> None:
    paths = _schema()["paths"]
    assert "/health" in paths
    assert "/ready" in paths
    assert not any(path.startswith("/api/v1") for path in paths)


def test_health_documents_200() -> None:
    assert "200" in _schema()["paths"]["/health"]["get"]["responses"]


def test_ready_documents_200_and_503_envelope() -> None:
    schema = _schema()
    responses = schema["paths"]["/ready"]["get"]["responses"]
    assert {"200", "503"} <= set(responses)
    ref = responses["503"]["content"]["application/json"]["schema"]["$ref"]
    envelope = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert set(envelope["required"]) == {"code", "message", "request_id", "details"}
