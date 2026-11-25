"""FR-004-23, 24: permisos por columna sobre las tablas del entrenamiento."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

SHA = "b" * 64
RUN = str(uuid.uuid4())
INSERT_VERSION = (
    "INSERT INTO model_versions (version, number, run_id, schema_version, schema_fingerprint, "
    "params, metrics, dataset_hash, artifact_file, artifact_sha256, library_versions) "
    "VALUES ('v0001', 1, :r, 1, :sha, '{}', '{}', :sha, 'model-v0001.joblib', :sha, '{}')"
)


def _denied(engine: Engine, statement: str, **params: object) -> bool:
    try:
        with engine.begin() as connection:
            connection.execute(text(statement), params)
    except DBAPIError as exc:
        return getattr(exc.orig, "sqlstate", None) == "42501"
    return False


def _allowed(engine: Engine, statement: str, **params: object) -> bool:
    with engine.begin() as connection:
        connection.execute(text(statement), params)
    return True


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        query = text(f"SELECT count(*) FROM {table}")  # noqa: S608
        return int(connection.execute(query).scalar_one())


@pytest.fixture
def seeded(app_engine: Engine) -> Engine:
    assert _allowed(
        app_engine,
        "INSERT INTO training_runs (id, status, params) VALUES (:r, 'running', '{}')",
        r=RUN,
    )
    assert _allowed(app_engine, INSERT_VERSION, r=RUN, sha=SHA)
    return app_engine


def test_the_application_role_can_read_and_insert_both_tables(seeded: Engine) -> None:
    assert _count(seeded, "training_runs") == 1 and _count(seeded, "model_versions") == 1


def test_the_application_role_updates_only_the_allowed_run_columns(seeded: Engine) -> None:
    for column, value in (
        ("status", "'failed'"),
        ("heartbeat_at", "now()"),
        ("finished_at", "now()"),
        ("dataset_hash", f"'{SHA}'"),
        ("n_train", "10"),
        ("n_calibration", "5"),
        ("n_test", "5"),
        ("version", "'v0001'"),
        ("error_code", "'stale'"),
    ):
        assert _allowed(seeded, f"UPDATE training_runs SET {column} = {value}"), column  # noqa: S608
    for column, value in (("params", "'{}'"), ("started_at", "now()"), ("id", "gen_random_uuid()")):
        assert _denied(seeded, f"UPDATE training_runs SET {column} = {value}"), column  # noqa: S608


def test_a_registered_version_is_immutable_except_for_activation(seeded: Engine) -> None:
    assert _allowed(seeded, "UPDATE model_versions SET active = true, activated_at = now()")
    assert _allowed(seeded, "UPDATE model_versions SET active = false")
    for column, value in (
        ("metrics", "'{\"x\": 1}'"),
        ("params", "'{\"x\": 1}'"),
        ("artifact_sha256", f"'{'c' * 64}'"),
        ("dataset_hash", f"'{'c' * 64}'"),
        ("schema_fingerprint", f"'{'c' * 64}'"),
        ("schema_version", "2"),
        ("artifact_file", "'model-v0002.joblib'"),
        ("library_versions", "'{}'"),
        ("version", "'v0009'"),
        ("number", "9"),
        ("created_at", "now()"),
    ):
        assert _denied(seeded, f"UPDATE model_versions SET {column} = {value}"), column  # noqa: S608
    with seeded.connect() as connection:
        row = connection.execute(
            text("SELECT metrics::text, artifact_sha256 FROM model_versions")
        ).one()
    assert tuple(row) == ("{}", SHA)


def test_the_application_role_can_never_delete_truncate_or_alter(seeded: Engine) -> None:
    for statement in (
        "DELETE FROM training_runs",
        "DELETE FROM model_versions",
        "TRUNCATE TABLE model_versions",
        "TRUNCATE TABLE training_runs CASCADE",
        "ALTER TABLE model_versions ADD COLUMN intruder text",
        "DROP TABLE model_versions",
        "CREATE INDEX intruder_ix ON model_versions (dataset_hash)",
    ):
        assert _denied(seeded, statement), statement
    assert _count(seeded, "training_runs") == 1 and _count(seeded, "model_versions") == 1


def test_the_maintenance_role_has_no_access_and_the_migrator_has_it_all(
    seeded: Engine, maint_engine: Engine, migrator_engine: Engine
) -> None:
    for statement in (
        "SELECT * FROM training_runs",
        "SELECT * FROM model_versions",
        "INSERT INTO training_runs (id, status, params) VALUES (gen_random_uuid(), 'failed', '{}')",
        "DELETE FROM model_versions",
    ):
        assert _denied(maint_engine, statement), statement
    assert _allowed(migrator_engine, "UPDATE model_versions SET metrics = '{\"x\": 1}'")
    assert _allowed(migrator_engine, "UPDATE training_runs SET params = '{\"x\": 1}'")


def test_the_events_privileges_of_the_application_role_do_not_change(seeded: Engine) -> None:
    for statement in (
        "DELETE FROM events",
        "UPDATE events SET host = 'x'",
        "TRUNCATE TABLE events",
    ):
        assert _denied(seeded, statement), statement
