"""FR-000-16: el README documenta instalar, configurar, arrancar, verificar y detener."""

from pathlib import Path

README = (Path(__file__).resolve().parents[2] / "README.md").read_text()


def test_readme_documents_the_documented_commands() -> None:
    for fragment in (
        "uv sync --frozen",
        "docker compose up --build",
        "docker compose down",
        "alembic upgrade head",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy",
        "uv run pytest",
        "cp .env.example .env",
    ):
        assert fragment in README, fragment


def test_readme_explains_the_probes_and_the_required_password() -> None:
    for fragment in ("/health", "/ready", "POSTGRES_PASSWORD", "X-Request-ID"):
        assert fragment in README, fragment


def test_readme_states_the_known_limits() -> None:
    lowered = README.lower()
    assert "anomalía no implica" in lowered or "no es una probabilidad" in lowered
    assert "protección de rama" in lowered
