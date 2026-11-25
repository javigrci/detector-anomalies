"""FR-004-29, 30, SC-006: carga segura y mismo pipeline para entrenar y puntuar."""

import os
from pathlib import Path

import joblib
import pytest
from sqlalchemy import Engine, text

from security_anomaly.features import FEATURE_SCHEMA
from security_anomaly.ml import load_active_model, load_model
from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.dataset import build_dataset, split_temporal
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.pipeline import TrainedModel, score_vector, score_vectors, train_model
from security_anomaly.ml.registry import activate_version
from security_anomaly.ml.service import run_training
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.schemas.ml import MlPolicy
from tests.integration.ml.conftest import LoadedData

pytestmark = pytest.mark.integration


def _load(engine: Engine, settings: MlSettings, version: str) -> TrainedModel:
    model: TrainedModel = load_model(engine, settings, version)
    return model


@pytest.fixture
def trained(app_engine: Engine, settings: MlSettings, loaded: LoadedData) -> str:
    return run_training(
        app_engine, settings, loaded.start, loaded.end, history_start=loaded.history_start
    ).version.version


def test_a_loaded_model_scores_exactly_like_a_freshly_trained_one(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData, trained: str
) -> None:
    dataset = build_dataset(
        app_engine, loaded.start, loaded.end, history_start=loaded.history_start
    )
    partition = split_temporal(dataset, MlPolicy())
    fresh = train_model(partition, MlPolicy())
    loaded_model = _load(app_engine, settings, trained)
    assert score_vectors(loaded_model, dataset.vectors) == score_vectors(fresh, dataset.vectors)
    assert (
        score_vector(loaded_model, dataset.vectors[0])
        == score_vectors(fresh, dataset.vectors[:1])[0]
    )


def test_the_active_model_loads_and_no_active_model_is_a_controlled_error(
    app_engine: Engine, settings: MlSettings, trained: str
) -> None:
    with pytest.raises(MlError) as none:
        load_active_model(app_engine, settings)
    assert none.value.code == "no_active_model"
    activate_version(app_engine, settings, trained, approved=True)
    assert load_active_model(app_engine, settings).schema_fingerprint == FEATURE_SCHEMA.fingerprint


def test_a_tampered_artifact_is_rejected_before_anything_is_deserialized(
    app_engine: Engine,
    settings: MlSettings,
    trained: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[object] = []

    def must_not_run(*args: object, **kwargs: object) -> None:
        opened.append(args)
        raise AssertionError("joblib.load no debe ejecutarse sobre un artefacto manipulado")

    monkeypatch.setattr(joblib, "load", must_not_run)
    path = tmp_path / f"model-{trained}.joblib"
    data = bytearray(path.read_bytes())
    data[len(data) // 3] ^= 0x01
    path.write_bytes(bytes(data))
    with pytest.raises(MlError) as caught:
        _load(app_engine, settings, trained)
    assert caught.value.code == "artifact_integrity"
    assert opened == []  # nada se deserializó
    assert str(tmp_path) not in f"{caught.value!s} {caught.value!r}"


def test_a_missing_artifact_is_a_controlled_error(
    app_engine: Engine, settings: MlSettings, trained: str, tmp_path: Path
) -> None:
    (tmp_path / f"model-{trained}.joblib").unlink()
    with pytest.raises(MlError) as caught:
        _load(app_engine, settings, trained)
    assert caught.value.code == "artifact_integrity"


def test_a_symlink_in_place_of_the_artifact_is_rejected_before_opening(
    app_engine: Engine, settings: MlSettings, trained: str, tmp_path: Path
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.bin"
    outside.write_bytes((tmp_path / f"model-{trained}.joblib").read_bytes())
    (tmp_path / f"model-{trained}.joblib").unlink()
    os.symlink(outside, tmp_path / f"model-{trained}.joblib")
    with pytest.raises(MlError) as caught:
        _load(app_engine, settings, trained)
    assert caught.value.code == "artifact_path"


def test_an_unknown_version_is_a_controlled_error(
    app_engine: Engine, settings: MlSettings, trained: str
) -> None:
    with pytest.raises(MlError) as caught:
        _load(app_engine, settings, "v0099")
    assert caught.value.code == "unknown_version"


def test_other_library_versions_are_rejected_before_loading(
    app_engine: Engine,
    migrator_engine: Engine,
    settings: MlSettings,
    trained: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[object] = []

    def must_not_run(*args: object, **kwargs: object) -> None:
        opened.append(args)
        raise AssertionError("no debe cargarse con otras versiones de las librerías")

    with migrator_engine.begin() as connection:
        connection.execute(
            text('UPDATE model_versions SET library_versions = \'{"scikit-learn": "0.0.1"}\'')
        )
    monkeypatch.setattr(joblib, "load", must_not_run)
    with pytest.raises(MlError) as caught:
        _load(app_engine, settings, trained)
    assert caught.value.code == "incompatible_environment"
    assert opened == []


def test_scoring_vectors_with_another_schema_is_rejected(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData, trained: str
) -> None:
    model = _load(app_engine, settings, trained)
    dataset = build_dataset(
        app_engine, loaded.start, loaded.end, history_start=loaded.history_start
    )
    base = dataset.vectors[0]
    other_version = FeatureVector.model_validate({**base.model_dump(), "schema_version": 2})
    with pytest.raises(MlError) as caught:
        score_vector(model, other_version)
    assert caught.value.code == "incompatible_features"
    model.schema_fingerprint = "0" * 64
    with pytest.raises(MlError) as other:
        score_vector(model, base)
    assert other.value.code == "incompatible_features"
