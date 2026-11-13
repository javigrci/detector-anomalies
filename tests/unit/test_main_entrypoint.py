"""FR-000-03: el servicio falla al arrancar con configuración inválida, sin revelar valores."""

import os
import subprocess
import sys


def _run(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), **extra_env}
    return subprocess.run(
        [sys.executable, "-m", "security_anomaly"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_missing_database_url_fails_and_names_the_variable() -> None:
    result = _run({})
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_invalid_value_is_never_printed() -> None:
    result = _run(
        {
            "DATABASE_URL": "postgresql+psycopg://u:topsecretvalue@localhost/db",
            "API_PORT": "valor-secreto-invalido",
        }
    )
    assert result.returncode != 0
    assert "API_PORT" in result.stderr
    for text in (result.stdout, result.stderr):
        assert "valor-secreto-invalido" not in text
        assert "topsecretvalue" not in text
