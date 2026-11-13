"""FR-000-13 y FR-000-18: la CI ejecuta calidad, integración y la prueba de humo de Compose.

Comprobaciones de texto: no se añade una dependencia YAML.
"""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return WORKFLOW.read_text()


def test_defines_the_three_jobs() -> None:
    text = _text()
    for job in ("quality:", "integration:", "compose-smoke:"):
        assert re.search(rf"^  {re.escape(job)}", text, flags=re.MULTILINE), job


def test_triggers_on_push_to_main_and_pull_requests() -> None:
    text = _text()
    assert re.search(r"^on:", text, flags=re.MULTILINE)
    assert "pull_request" in text
    assert re.search(r"push:\s*\n\s*branches:\s*\[main\]", text)


def test_quality_job_runs_every_gate_with_a_frozen_lock() -> None:
    text = _text()
    for command in (
        "uv sync --frozen",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy",
        'uv run pytest -m "not integration"',
    ):
        assert command in text, command


def test_integration_job_uses_a_real_postgres_16_service() -> None:
    text = _text()
    assert "image: postgres:16" in text
    assert "uv run pytest -m integration" in text
    assert "uv run alembic upgrade head" in text


def test_compose_smoke_checks_both_probes_and_cleans_up() -> None:
    text = _text()
    assert "docker compose up --build" in text
    assert "/health" in text
    assert "/ready" in text
    assert "docker compose down -v" in text


def test_actions_are_pinned_to_exact_versions() -> None:
    uses = re.findall(r"uses:\s*(\S+)", _text())
    assert uses
    for reference in uses:
        assert re.fullmatch(r"[\w./-]+@v\d+\.\d+\.\d+", reference), reference


def test_workflow_requests_least_privilege_and_has_no_inline_secrets() -> None:
    text = _text()
    assert "permissions:" in text
    assert "contents: read" in text
    assert "secrets." not in text
