"""FR-002-22, 23: Compose aprovisiona los tres roles con perfiles explícitos y sin secretos.

Comprobaciones de texto: no se añade una dependencia YAML.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
FORBIDDEN_FOR_API = ("MAINTENANCE_DATABASE_URL", "ADMIN_DATABASE_URL", "MIGRATION_DATABASE_URL")


def _service(name: str) -> str:
    text = COMPOSE.read_text()
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|^\S|\Z)", text, re.M | re.S)
    assert match, f"falta el servicio {name}"
    return match.group(1)


def test_setup_and_maintenance_run_only_under_explicit_profiles() -> None:
    assert re.search(r"profiles:\s*\[\"?setup\"?\]", _service("db-setup"))
    assert re.search(r"profiles:\s*\[\"?maintenance\"?\]", _service("db-maintenance"))
    for name in ("db", "api"):
        assert "profiles:" not in _service(name)


def test_the_database_is_not_published_on_the_host() -> None:
    assert "ports:" not in _service("db")


def test_the_api_uses_the_application_role_and_has_no_other_credentials() -> None:
    api = _service("api")
    assert "anomaly_app" in api
    assert "APP_DB_PASSWORD" in api
    for variable in FORBIDDEN_FOR_API:
        assert variable not in api, variable
    for password in ("MAINT_DB_PASSWORD", "MIGRATOR_DB_PASSWORD"):
        assert password not in api, password


def test_setup_provisions_roles_then_migrates_with_the_migrator() -> None:
    setup = _service("db-setup")
    assert "provision-roles" in setup
    assert setup.index("provision-roles") < setup.index("alembic upgrade head")
    assert "MIGRATION_DATABASE_URL" in setup and "anomaly_migrator" in setup
    assert "ADMIN_DATABASE_URL" in setup
    assert "MAINTENANCE_DATABASE_URL" not in setup
    assert re.search(r"depends_on:\s*\n\s+db:\s*\n\s+condition:\s*service_healthy", setup)


def test_maintenance_defaults_to_a_dry_run_and_only_knows_its_own_role() -> None:
    maintenance = _service("db-maintenance")
    assert "MAINTENANCE_DATABASE_URL" in maintenance and "anomaly_maint" in maintenance
    assert "purge" in maintenance and "--dry-run" in maintenance
    assert "ADMIN_DATABASE_URL" not in maintenance
    assert "MIGRATION_DATABASE_URL" not in maintenance
    assert "APP_DB_PASSWORD" not in maintenance


def test_extra_cli_arguments_are_appended_to_the_entrypoint() -> None:
    # `run --rm db-maintenance purge` debe ejecutar `python -m security_anomaly.storage purge`.
    assert re.search(r"entrypoint:.*security_anomaly\.storage", _service("db-maintenance"))


def test_every_role_password_is_required_and_comes_from_the_environment() -> None:
    text = COMPOSE.read_text()
    for variable in ("MIGRATOR_DB_PASSWORD", "APP_DB_PASSWORD", "MAINT_DB_PASSWORD"):
        assert re.search(rf"\$\{{{variable}:\?", text), variable


def test_no_passwords_in_the_repository_files() -> None:
    assert "change-me" not in COMPOSE.read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "PASSWORD" not in dockerfile.upper().replace("POSTGRES", "")
    assert not re.search(r"postgresql\+psycopg://[^$\s]+:[^$@\s]+@", COMPOSE.read_text())
