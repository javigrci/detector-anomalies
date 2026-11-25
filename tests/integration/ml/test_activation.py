"""FR-004-26, SC-007: una sola versión activa, solo con aprobación y tras verificar el artefacto."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from security_anomaly.ml import registry
from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.registry import activate_version, get_active_version
from security_anomaly.ml.service import run_training
from tests.integration.ml.conftest import LoadedData

pytestmark = pytest.mark.integration


@pytest.fixture
def two_versions(app_engine: Engine, settings: MlSettings, loaded: LoadedData) -> None:
    for _ in range(2):
        run_training(
            app_engine, settings, loaded.start, loaded.end, history_start=loaded.history_start
        )


def _active_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT count(*) FROM model_versions WHERE active")
            ).scalar_one()
        )


def test_activating_makes_one_version_the_only_active_one(
    app_engine: Engine, settings: MlSettings, two_versions: None
) -> None:
    assert get_active_version(app_engine) is None
    first = activate_version(app_engine, settings, "v0001", approved=True)
    assert first.active is True and first.activated_at is not None
    second = activate_version(app_engine, settings, "v0002", approved=True)
    assert second.active is True
    assert registry.get_version(app_engine, "v0001").active is False
    assert (get_active_version(app_engine) or second).version == "v0002"
    assert _active_count(app_engine) == 1


def test_simultaneous_activations_never_leave_two_active(
    app_engine: Engine, settings: MlSettings, two_versions: None
) -> None:
    def activate(index: int) -> str:
        return activate_version(
            app_engine, settings, "v0001" if index % 2 else "v0002", approved=True
        ).version

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(activate, range(16)))
    assert len(results) == 16
    assert _active_count(app_engine) == 1


@pytest.mark.parametrize("approved", [False, None, "yes", 1])
def test_without_an_explicit_approval_nothing_changes(
    app_engine: Engine, settings: MlSettings, two_versions: None, approved: object
) -> None:
    activate_version(app_engine, settings, "v0001", approved=True)
    with pytest.raises(MlError) as caught:
        activate_version(app_engine, settings, "v0002", approved=approved)  # type: ignore[arg-type]
    assert caught.value.code == "approval_required"
    assert (get_active_version(app_engine) or None) is not None
    assert get_active_version(app_engine).version == "v0001"  # type: ignore[union-attr]


def test_an_unknown_version_is_rejected_and_changes_nothing(
    app_engine: Engine, settings: MlSettings, two_versions: None
) -> None:
    activate_version(app_engine, settings, "v0001", approved=True)
    with pytest.raises(MlError) as caught:
        activate_version(app_engine, settings, "v0099", approved=True)
    assert caught.value.code == "unknown_version"
    assert _active_count(app_engine) == 1
    assert get_active_version(app_engine).version == "v0001"  # type: ignore[union-attr]


def test_a_tampered_or_missing_artifact_cannot_be_activated(
    app_engine: Engine, settings: MlSettings, two_versions: None, tmp_path: Path
) -> None:
    activate_version(app_engine, settings, "v0001", approved=True)
    path = tmp_path / "model-v0002.joblib"
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    with pytest.raises(MlError) as tampered:
        activate_version(app_engine, settings, "v0002", approved=True)
    assert tampered.value.code == "artifact_integrity"
    path.unlink()
    with pytest.raises(MlError) as missing:
        activate_version(app_engine, settings, "v0002", approved=True)
    assert missing.value.code == "artifact_integrity"
    assert get_active_version(app_engine).version == "v0001"  # type: ignore[union-attr]
    assert str(tmp_path) not in f"{tampered.value!s} {missing.value!s}"


def test_training_alone_never_activates(
    app_engine: Engine, settings: MlSettings, loaded: LoadedData
) -> None:
    run_training(app_engine, settings, loaded.start, loaded.end, history_start=loaded.history_start)
    assert get_active_version(app_engine) is None
    assert _active_count(app_engine) == 0
