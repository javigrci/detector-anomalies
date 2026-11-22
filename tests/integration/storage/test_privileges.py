"""FR-002-22, SC-007: privilegios de los tres roles contra PostgreSQL real."""

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError

from security_anomaly.storage import save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration

INSERT = (
    "INSERT INTO events (source, event_id, timestamp, event_type, action, outcome, batch_id) "
    "VALUES ('linux-auth', 'priv-' || gen_random_uuid()::text, now(), 'other', 'other', "
    "'unknown', gen_random_uuid())"
)


def _denied(engine: Engine, statement: str) -> bool:
    """True si la base de datos deniega la sentencia por falta de privilegios (SQLSTATE 42501)."""
    try:
        with engine.begin() as connection:
            connection.execute(text(statement))
    except DBAPIError as exc:
        return getattr(exc.orig, "sqlstate", None) == "42501"
    return False


def _allowed(engine: Engine, statement: str) -> bool:
    with engine.begin() as connection:
        connection.execute(text(statement))
    return True


def _snapshot(engine: Engine) -> tuple[int, set[str], set[str]]:
    with engine.connect() as connection:
        count = int(connection.execute(text("SELECT count(*) FROM events")).scalar_one())
    inspector = inspect(engine)
    return (
        count,
        {c["name"] for c in inspector.get_columns("events")},
        set(inspector.get_table_names()),
    )


@pytest.fixture
def seeded(app_engine: Engine, migrator_engine: Engine) -> Engine:
    save_events(app_engine, make_events(5))
    return migrator_engine


def test_application_role_can_insert_and_select_only(app_engine: Engine, seeded: Engine) -> None:
    before = _snapshot(seeded)
    assert _allowed(app_engine, INSERT)
    assert _allowed(app_engine, "SELECT count(*) FROM events")
    after_insert = _snapshot(seeded)
    assert after_insert[0] == before[0] + 1

    for statement in (
        "DELETE FROM events",
        "DELETE FROM events WHERE event_id = 'evt-000000'",
        "TRUNCATE TABLE events",
        "UPDATE events SET host = 'x'",
        "CREATE TABLE intruder (x int)",
        "ALTER TABLE events ADD COLUMN intruder text",
        "ALTER TABLE events DROP COLUMN host",
        "DROP TABLE events",
        "CREATE INDEX intruder_ix ON events (host)",
    ):
        assert _denied(app_engine, statement), statement
    assert _snapshot(seeded) == after_insert


def test_maintenance_role_can_select_and_delete_only(maint_engine: Engine, seeded: Engine) -> None:
    assert _allowed(maint_engine, "SELECT count(*) FROM events")
    before = _snapshot(seeded)
    for statement in (
        INSERT,
        "UPDATE events SET host = 'x'",
        "TRUNCATE TABLE events",
        "CREATE TABLE intruder (x int)",
        "ALTER TABLE events ADD COLUMN intruder text",
        "DROP TABLE events",
    ):
        assert _denied(maint_engine, statement), statement
    assert _snapshot(seeded) == before

    assert _allowed(maint_engine, "DELETE FROM events WHERE event_id = 'evt-000000'")
    assert _snapshot(seeded)[0] == before[0] - 1


def test_migrator_owns_the_schema(migrator_engine: Engine) -> None:
    assert _allowed(migrator_engine, INSERT)
    assert _allowed(migrator_engine, "UPDATE events SET host = 'x'")
    assert _allowed(migrator_engine, "DELETE FROM events")
    assert _allowed(migrator_engine, "CREATE TABLE scratch (x int)")
    assert _allowed(migrator_engine, "ALTER TABLE scratch ADD COLUMN y int")
    assert _allowed(migrator_engine, "DROP TABLE scratch")
    assert _allowed(migrator_engine, "TRUNCATE TABLE events")


def test_neither_runtime_role_can_create_in_the_schema(
    app_engine: Engine, maint_engine: Engine, admin_engine: Engine
) -> None:
    with admin_engine.connect() as connection:
        for role in ("anomaly_app", "anomaly_maint"):
            assert not connection.execute(
                text("SELECT has_schema_privilege(:r, 'public', 'CREATE')"), {"r": role}
            ).scalar_one()
    for engine in (app_engine, maint_engine):
        assert _denied(engine, "CREATE TABLE intruder (x int)")
        assert _denied(engine, "CREATE SCHEMA intruder")


def test_the_application_role_cannot_use_the_roles_of_others(
    app_engine: Engine, maint_engine: Engine
) -> None:
    for engine in (app_engine, maint_engine):
        assert _denied(engine, "SET ROLE anomaly_migrator")
        assert _denied(engine, "CREATE ROLE intruder")
        assert _denied(engine, "ALTER ROLE anomaly_app SUPERUSER")


def test_the_alembic_table_is_not_readable_by_runtime_roles(
    app_engine: Engine, maint_engine: Engine
) -> None:
    for engine in (app_engine, maint_engine):
        assert _denied(engine, "SELECT * FROM alembic_version")
