"""FR-000-08 con PostgreSQL real (marcador integration)."""

import os

import pytest
from fastapi.testclient import TestClient

from security_anomaly.api.main import create_app
from security_anomaly.core.config import load_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            "Los tests de integración requieren DATABASE_URL (ver tasks.md, notas)", pytrace=False
        )
    return url


def test_ready_is_ok_with_real_database(database_url: str) -> None:
    with TestClient(create_app(load_settings({"DATABASE_URL": database_url}))) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}
