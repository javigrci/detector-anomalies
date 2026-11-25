"""FR-004-21…23, 25, 26: un entrenamiento registra su ejecución y su versión sin activarla."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from security_anomaly.ml import registry
from security_anomaly.ml.artifacts import sha256_file
from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.service import run_training
from security_anomaly.schemas.ml import MlPolicy
from tests.integration.ml.conftest import LoadedData

pytestmark = pytest.mark.integration


def _train(engine: Engine, settings: MlSettings, data: LoadedData, **kwargs):  # type: ignore[no-untyped-def]
    return run_training(
        engine, settings, data.start, data.end, history_start=data.history_start, **kwargs
    )


def test_a_training_registers_the_run_the_version_and_the_artifact(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData, tmp_path: Path
) -> None:
    result = _train(app_engine, settings, loaded, labels=loaded.labels)
    run = registry.get_training_run(app_engine, result.run_id)
    assert (run.status, run.version, run.error_code) == ("succeeded", "v0001", None)
    assert run.finished_at is not None and run.dataset_hash is not None
    assert (run.n_train or 0) > 0 and (run.n_calibration or 0) > 0 and (run.n_test or 0) > 0

    version = result.version
    assert (version.version, version.number, version.run_id) == ("v0001", 1, result.run_id)
    assert (version.schema_version, len(version.schema_fingerprint)) == (1, 64)
    assert version.params == MlPolicy().model_dump()
    assert version.metrics["labelled"] is True
    assert version.dataset_hash == run.dataset_hash and len(version.dataset_hash) == 64
    assert set(version.library_versions) == {"scikit-learn", "numpy", "scipy"}
    assert version.active is False and version.activated_at is None
    artifact = tmp_path / version.artifact_file
    assert artifact.is_file() and sha256_file(artifact) == version.artifact_sha256
    assert registry.get_version(app_engine, "v0001") == version


def test_a_second_training_gets_a_new_version_and_leaves_the_first_untouched(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData
) -> None:
    first = _train(app_engine, settings, loaded)
    second = _train(app_engine, settings, loaded)
    assert second.version.version == "v0002"
    assert second.version.dataset_hash == first.version.dataset_hash  # mismo dataset, misma huella
    assert registry.get_version(app_engine, "v0001") == first.version
    assert [v.version for v in registry.list_versions(app_engine)] == ["v0001", "v0002"]


def test_no_training_activates_its_result(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData
) -> None:
    _train(app_engine, settings, loaded)
    assert registry.get_active_version(app_engine) is None


def test_a_failure_while_registering_leaves_a_failed_run_and_no_orphan(
    app_engine: Engine,
    settings: MlSettings,
    loaded: LoadedData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("SENTINEL-FAILURE")

    monkeypatch.setattr(registry, "register_model_version", boom)
    with pytest.raises(MlError) as caught:
        _train(app_engine, settings, loaded)
    assert caught.value.code == "training_failed"
    assert "SENTINEL" not in f"{caught.value!s} {caught.value!r}"
    (run,) = registry.list_training_runs(app_engine)
    assert (run.status, run.error_code, run.version) == ("failed", "training_failed", None)
    assert registry.list_versions(app_engine) == []
    assert list(tmp_path.iterdir()) == []


def test_insufficient_data_fails_the_run_with_its_code_and_writes_nothing(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData, tmp_path: Path
) -> None:
    with pytest.raises(MlError) as caught:
        run_training(
            app_engine,
            settings,
            loaded.start,
            loaded.start.replace(microsecond=0) + (loaded.end - loaded.start) / 50,
            history_start=loaded.history_start,
        )
    assert caught.value.code == "insufficient_data"
    (run,) = registry.list_training_runs(app_engine)
    assert (run.status, run.error_code) == ("failed", "insufficient_data")
    assert registry.list_versions(app_engine) == [] and list(tmp_path.iterdir()) == []


def test_the_log_only_has_counts_durations_versions_and_codes(
    app_engine: Engine,
    settings: MlSettings,
    loaded: LoadedData,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    with caplog.at_level(logging.INFO):
        _train(app_engine, settings, loaded)
    started = [r for r in caplog.records if r.getMessage() == "training_started"]
    finished = [r for r in caplog.records if r.getMessage() == "training_finished"]
    assert len(started) == 1 and len(finished) == 1
    fields = finished[0].fields  # type: ignore[attr-defined]
    assert {"run_id", "version", "n_train", "n_calibration", "n_test", "duration_ms"} <= set(fields)
    assert "SENTINEL" not in caplog.text and "usr_" not in caplog.text


def test_the_versions_table_only_has_what_the_service_wrote(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData
) -> None:
    _train(app_engine, settings, loaded)
    with app_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM model_versions WHERE active")
        ).scalar_one()
    assert count == 0
