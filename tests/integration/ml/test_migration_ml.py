"""FR-004-24: la migración 0002 crea las tablas del entrenamiento y es repetible."""

from collections.abc import Callable

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from security_anomaly.storage.roles import MIGRATOR_ROLE
from tests.integration.conftest import run_alembic

pytestmark = pytest.mark.integration

RoleUrl = Callable[[str, str], str]
SHA = "a" * 64
RUN = "11111111-1111-1111-1111-111111111111"
INSERT_RUN = (
    "INSERT INTO training_runs (id, status, params) VALUES (gen_random_uuid(), '{status}', '{{}}')"
)


def _migrated(fresh_database: Callable[[], str], role_url: RoleUrl) -> str:
    name = fresh_database()
    url = role_url(MIGRATOR_ROLE, name)
    assert run_alembic(url, "upgrade", "head").returncode == 0
    return url


def test_the_tables_columns_and_indexes_exist(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    url = _migrated(fresh_database, role_url)
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert {"training_runs", "model_versions"} <= set(inspector.get_table_names())
        runs = {c["name"] for c in inspector.get_columns("training_runs")}
        assert runs == {
            "id",
            "status",
            "started_at",
            "heartbeat_at",
            "finished_at",
            "params",
            "dataset_hash",
            "n_train",
            "n_calibration",
            "n_test",
            "version",
            "error_code",
        }
        versions = {c["name"] for c in inspector.get_columns("model_versions")}
        assert versions == {
            "version",
            "number",
            "run_id",
            "created_at",
            "schema_version",
            "schema_fingerprint",
            "params",
            "metrics",
            "dataset_hash",
            "artifact_file",
            "artifact_sha256",
            "library_versions",
            "active",
            "activated_at",
        }
        index_names = {
            i["name"] for t in ("training_runs", "model_versions") for i in inspector.get_indexes(t)
        }
        assert {"uq_training_runs_one_running", "uq_model_versions_one_active"} <= index_names
        fks = inspector.get_foreign_keys("model_versions")
        assert [fk["referred_table"] for fk in fks] == ["training_runs"]
    finally:
        engine.dispose()


def test_applying_twice_changes_nothing(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    url = _migrated(fresh_database, role_url)
    again = run_alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr


def _insert_run(connection, status: str = "running") -> None:  # type: ignore[no-untyped-def]
    connection.execute(
        text("INSERT INTO training_runs (id, status, params) VALUES (:id, :s, '{}')"),
        {"id": RUN, "s": status},
    )


def test_check_constraints_reject_bad_rows(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    url = _migrated(fresh_database, role_url)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            _insert_run(connection, "succeeded")
        good = {
            "v": "v0001",
            "n": 1,
            "r": RUN,
            "sha": SHA,
            "f": "model-v0001.joblib",
        }
        sql = (
            "INSERT INTO model_versions (version, number, run_id, schema_version, "
            "schema_fingerprint, params, metrics, dataset_hash, artifact_file, "
            "artifact_sha256, library_versions) "
            "VALUES (:v, :n, :r, 1, :sha, '{}', '{}', :sha, :f, :sha, '{}')"
        )
        for bad in (
            {**good, "v": "version-1"},
            {**good, "f": "../model-v0001.joblib"},
            {**good, "f": "sub/model-v0001.joblib"},
            {**good, "sha": "xyz"},
        ):
            with pytest.raises(DBAPIError) as caught, engine.begin() as connection:
                connection.execute(text(sql), bad)
            assert getattr(caught.value.orig, "sqlstate", None) == "23514"
        with engine.begin() as connection:
            connection.execute(text(sql), good)
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text("UPDATE training_runs SET status = 'paused'"))
    finally:
        engine.dispose()


def test_at_most_one_running_and_one_active(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    url = _migrated(fresh_database, role_url)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            _insert_run(connection)
        with pytest.raises(DBAPIError) as caught, engine.begin() as connection:
            connection.execute(text(INSERT_RUN.format(status="running")))
        assert getattr(caught.value.orig, "sqlstate", None) == "23505"
        with engine.begin() as connection:  # un `succeeded` y un `failed` no estorban
            connection.execute(text(INSERT_RUN.format(status="failed")))
    finally:
        engine.dispose()


def test_downgrade_is_guarded_when_there_are_rows(
    fresh_database: Callable[[], str], role_url: RoleUrl
) -> None:
    url = _migrated(fresh_database, role_url)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            _insert_run(connection, "failed")
    finally:
        engine.dispose()
    refused = run_alembic(url, "downgrade", "0001")
    assert refused.returncode != 0 and "destructive=yes" in refused.stderr
    allowed = run_alembic(url, "-x", "destructive=yes", "downgrade", "0001")
    assert allowed.returncode == 0, allowed.stderr
    engine = create_engine(url)
    try:
        assert "training_runs" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
