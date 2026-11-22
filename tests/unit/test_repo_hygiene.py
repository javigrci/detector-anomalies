"""FR-000-04 y FR-000-12: sin secretos versionados y contenedor sin privilegios."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VARS = {
    "APP_ENV",
    "LOG_LEVEL",
    "DATABASE_URL",
    "DB_CONNECT_TIMEOUT_S",
    "API_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "PSEUDONYM_KEY",
    "INGEST_MAX_FILE_BYTES",
    "INGEST_MAX_EVENTS_PER_BATCH",
    "INGEST_MAX_EVENTS_PER_DATASET",
    "INGEST_MAX_FIELD_LENGTH",
    "INGEST_TIMESTAMP_MIN",
    "INGEST_TIMESTAMP_MAX",
    "MIGRATION_DATABASE_URL",
    "MAINTENANCE_DATABASE_URL",
    "ADMIN_DATABASE_URL",
    "MIGRATOR_DB_PASSWORD",
    "APP_DB_PASSWORD",
    "MAINT_DB_PASSWORD",
    "RETENTION_DAYS",
    "QUERY_DEFAULT_LIMIT",
    "QUERY_MAX_LIMIT",
}


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def test_env_example_lists_every_documented_variable() -> None:
    assert set(_env_example()) >= EXPECTED_VARS


def test_env_example_contains_only_placeholder_secrets() -> None:
    values = _env_example()
    assert "change-me" in values["POSTGRES_PASSWORD"]
    assert "change-me" in values["DATABASE_URL"]
    assert "change-me" in values["PSEUDONYM_KEY"]
    for name in (
        "MIGRATION_DATABASE_URL",
        "MAINTENANCE_DATABASE_URL",
        "ADMIN_DATABASE_URL",
        "MIGRATOR_DB_PASSWORD",
        "APP_DB_PASSWORD",
        "MAINT_DB_PASSWORD",
    ):
        assert "change-me" in values[name], name


def test_dotenv_is_gitignored() -> None:
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    assert ".env" in lines


def test_dockerfile_runs_unprivileged_and_declares_no_secrets() -> None:
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    users = [line.split(None, 1)[1].strip() for line in lines if line.startswith("USER ")]
    assert users
    assert users[-1] not in {"root", "0"}
    for line in lines:
        if line.startswith(("ENV ", "ARG ")):
            for word in ("PASSWORD", "SECRET", "TOKEN", "DATABASE_URL"):
                assert word not in line.upper()


def test_dockerignore_excludes_secrets_and_vcs() -> None:
    entries = {line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()}
    assert {".git", ".env", ".venv"} <= entries
