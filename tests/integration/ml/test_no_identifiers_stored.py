"""FR-004-23, SC-008: ni el artefacto ni los registros contienen identificadores."""

from pathlib import Path

import pytest
from security_anomaly.ml.service import run_training
from sqlalchemy import Engine, text

from security_anomaly.ml.config import MlSettings
from tests.integration.ml.conftest import load_events
from tests.ml_factory import synthetic_vectors

pytestmark = pytest.mark.integration


def test_sentinel_values_never_reach_the_artifact_or_the_registry(
    app_engine: Engine, settings: MlSettings, tmp_path: Path
) -> None:
    data = synthetic_vectors(3, 1500)
    marked = [
        e.model_copy(
            update={
                "event_id": f"SENTINEL-ID-{i}",
                "host": "SENTINEL-HOST-leak",
                "source_ip": "192.0.2.77" if i % 3 == 0 else e.source_ip,
            }
        )
        for i, e in enumerate(data.events)
    ]
    labels = {f"SENTINEL-ID-{i}": data.labels[e.event_id] for i, e in enumerate(data.events)}
    loaded = load_events(app_engine, marked, labels)
    result = run_training(
        app_engine,
        settings,
        loaded.start,
        loaded.end,
        history_start=loaded.history_start,
        labels=labels,
    )
    pseudonyms = {e.user_pseudonym for e in marked if e.user_pseudonym}
    artifact = (tmp_path / result.version.artifact_file).read_bytes()
    with app_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT params::text, metrics::text, dataset_hash, version FROM model_versions")
        ).all()
        runs = connection.execute(
            text("SELECT params::text, dataset_hash FROM training_runs")
        ).all()
    texts = [*(str(c) for row in rows for c in row), *(str(c) for row in runs for c in row)]
    texts.append(result.report.model_dump_json())
    for secret in ("SENTINEL", "192.0.2.77", *pseudonyms):
        assert secret.encode() not in artifact, secret
        assert not any(secret in t for t in texts), secret
