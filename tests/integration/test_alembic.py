"""FR-002-05, FR-002-22: la migración 0001 crea `events`, es idempotente y retrocede con guardia."""

import importlib.util
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL

from security_anomaly.storage.roles import APP_ROLE, MAINT_ROLE, MIGRATOR_ROLE
from tests.integration.conftest import run_alembic

pytestmark = pytest.mark.integration

RoleUrl = Callable[[str, str], str]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "src/security_anomaly/storage/migrations/versions/0001_create_events.py"
)


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_events_with_indexes_and_checks(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    name = fresh_database()
    url = role_url(MIGRATOR_ROLE, name)
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert _tables(url) == {"events", "alembic_version", "training_runs", "model_versions"}
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        index_names = {i["name"] for i in inspector.get_indexes("events")}
        assert index_names == {
            "ix_events_timestamp",
            "ix_events_source_timestamp",
            "ix_events_ip_timestamp",
            "ix_events_user_timestamp",
            "ix_events_ingested_at",
        }
        assert inspector.get_pk_constraint("events")["constrained_columns"] == [
            "source",
            "event_id",
        ]
        assert len(inspector.get_check_constraints("events")) >= 6
    finally:
        engine.dispose()


def test_upgrade_twice_changes_nothing(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    name = fresh_database()
    url = role_url(MIGRATOR_ROLE, name)
    assert run_alembic(url, "upgrade", "head").returncode == 0
    again = run_alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
    assert _tables(url) == {"events", "alembic_version", "training_runs", "model_versions"}


def test_grants_follow_the_privilege_table(
    fresh_database: Callable[[], str], role_url: RoleUrl, admin_url: URL
) -> None:
    name = fresh_database()
    assert run_alembic(role_url(MIGRATOR_ROLE, name), "upgrade", "head").returncode == 0
    engine: Engine = create_engine(admin_url.set(database=name))
    try:
        with engine.connect() as connection:

            def privileges(role: str) -> set[str]:
                rows = connection.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name = 'events' AND grantee = :role"
                    ),
                    {"role": role},
                )
                return {row[0] for row in rows}

            assert privileges(APP_ROLE) == {"SELECT", "INSERT"}
            assert privileges(MAINT_ROLE) == {"SELECT", "DELETE"}
    finally:
        engine.dispose()


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_roles_are_reported_with_a_clear_message(
    admin_engine: Engine,
) -> None:
    module = _load_migration()
    with admin_engine.connect() as connection:
        missing = module.missing_roles(connection, [APP_ROLE, "anomaly_does_not_exist"])  # type: ignore[attr-defined]
    assert missing == ["anomaly_does_not_exist"]
    message = module.missing_roles_message(missing)  # type: ignore[attr-defined]
    assert "provision-roles" in message
    assert "anomaly_does_not_exist" in message


def test_downgrade_refuses_when_there_are_rows(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    name = fresh_database()
    url = role_url(MIGRATOR_ROLE, name)
    assert run_alembic(url, "upgrade", "head").returncode == 0
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO events (source, event_id, timestamp, event_type, action, "
                    "outcome, batch_id) VALUES ('linux-auth', 'e1', now(), 'other', 'other', "
                    "'unknown', gen_random_uuid())"
                )
            )
    finally:
        engine.dispose()
    refused = run_alembic(url, "downgrade", "base")
    assert refused.returncode != 0
    assert "destructive=yes" in refused.stderr
    assert "events" in _tables(url)
    allowed = run_alembic(url, "-x", "destructive=yes", "downgrade", "base")
    assert allowed.returncode == 0, allowed.stderr
    assert "events" not in _tables(url)


def test_downgrade_of_an_empty_table_needs_no_confirmation(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    name = fresh_database()
    url = role_url(MIGRATOR_ROLE, name)
    assert run_alembic(url, "upgrade", "head").returncode == 0
    result = run_alembic(url, "downgrade", "base")
    assert result.returncode == 0, result.stderr
    assert "events" not in _tables(url)


def test_migration_does_not_use_the_application_url(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    """Alembic lee solo MIGRATION_DATABASE_URL: sin ella falla nombrando la variable."""
    result = run_alembic("", "upgrade", "head")
    assert result.returncode != 0
    assert "MIGRATION_DATABASE_URL" in result.stderr
