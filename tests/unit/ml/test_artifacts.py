"""FR-004-21, 29: guardado atómico de artefactos y resolución segura de su ruta."""

import os
import re
from pathlib import Path

import joblib
import pytest

from security_anomaly.ml.artifacts import (
    artifact_filename,
    resolve_artifact_path,
    save_artifact,
    sha256_file,
)
from security_anomaly.ml.errors import MlError


def _dump(path: Path, payload: object = None) -> Path:
    joblib.dump(payload if payload is not None else {"x": 1}, path)
    return path


def test_the_file_name_is_derived_from_the_version_with_a_strict_pattern() -> None:
    assert artifact_filename("v0001") == "model-v0001.joblib"
    for bad in ("../v0001", "v1", "V0001", "v0001/../x", "", "v0001.joblib", "v0001 "):
        with pytest.raises(MlError) as caught:
            artifact_filename(bad)
        assert caught.value.code == "artifact_path"


def test_saving_writes_one_file_atomically_and_returns_its_sha256(tmp_path: Path) -> None:
    file_name, digest = save_artifact(tmp_path, "v0001", {"model": [1, 2, 3]})
    assert file_name == "model-v0001.joblib"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["model-v0001.joblib"]  # sin temporales
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == sha256_file(tmp_path / file_name)
    assert joblib.load(tmp_path / file_name) == {"model": [1, 2, 3]}


def test_saving_never_overwrites_an_existing_artifact(tmp_path: Path) -> None:
    save_artifact(tmp_path, "v0001", {"a": 1})
    with pytest.raises(MlError) as caught:
        save_artifact(tmp_path, "v0001", {"a": 2})
    assert caught.value.code == "artifact_path"
    assert joblib.load(tmp_path / "model-v0001.joblib") == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["model-v0001.joblib"]


def test_a_failure_while_saving_leaves_no_temporary_file(tmp_path: Path) -> None:
    class Unpicklable:
        def __reduce__(self) -> tuple[object, ...]:
            raise RuntimeError("no se puede serializar")

    with pytest.raises(MlError):
        save_artifact(tmp_path, "v0002", Unpicklable())
    assert list(tmp_path.iterdir()) == []


def test_the_sha256_changes_with_one_byte(tmp_path: Path) -> None:
    path = _dump(tmp_path / "model-v0001.joblib")
    before = sha256_file(path)
    data = bytearray(path.read_bytes())
    data[-1] ^= 0x01
    path.write_bytes(bytes(data))
    assert sha256_file(path) != before


def test_a_valid_path_resolves_inside_the_model_directory(tmp_path: Path) -> None:
    path = _dump(tmp_path / "model-v0001.joblib")
    assert resolve_artifact_path(tmp_path, "model-v0001.joblib") == path.resolve()


@pytest.mark.parametrize(
    "name",
    ["../model-v0001.joblib", "/etc/passwd", "sub/model-v0001.joblib", "model-v0001.joblib/..", ""],
)
def test_names_with_path_components_are_rejected_without_the_path(
    tmp_path: Path, name: str
) -> None:
    with pytest.raises(MlError) as caught:
        resolve_artifact_path(tmp_path, name)
    assert caught.value.code == "artifact_path"
    assert str(tmp_path) not in f"{caught.value!s} {caught.value!r}"


def test_a_symlink_that_escapes_the_directory_is_rejected(tmp_path: Path) -> None:
    outside = _dump(tmp_path / "outside.bin")
    models = tmp_path / "models"
    models.mkdir()
    (models / "model-v0001.joblib").symlink_to(outside)
    with pytest.raises(MlError) as caught:
        resolve_artifact_path(models, "model-v0001.joblib")
    assert caught.value.code == "artifact_path"


def test_a_symlink_inside_the_directory_is_also_rejected(tmp_path: Path) -> None:
    real = _dump(tmp_path / "model-v0009.joblib")
    os.symlink(real, tmp_path / "model-v0001.joblib")
    with pytest.raises(MlError) as caught:
        resolve_artifact_path(tmp_path, "model-v0001.joblib")
    assert caught.value.code == "artifact_path"


def test_a_directory_or_a_missing_file(tmp_path: Path) -> None:
    (tmp_path / "model-v0001.joblib").mkdir()
    with pytest.raises(MlError) as caught:
        resolve_artifact_path(tmp_path, "model-v0001.joblib")
    assert caught.value.code == "artifact_path"
    with pytest.raises(MlError) as missing:
        resolve_artifact_path(tmp_path, "model-v0002.joblib")
    assert missing.value.code == "artifact_integrity"
