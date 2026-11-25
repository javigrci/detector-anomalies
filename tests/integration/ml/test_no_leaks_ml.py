"""SC-008, FR-004-31: ningún valor sensible sale en artefactos, registros, informes, CLI ni logs."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine

from security_anomaly.ml import (
    MlSettings,
    activate_version,
    list_versions,
    load_model,
    run_training,
    score_vectors,
)
from security_anomaly.ml import __main__ as cli
from security_anomaly.ml.dataset import build_dataset
from tests.integration.ml.conftest import load_events
from tests.ml_factory import synthetic_vectors

pytestmark = pytest.mark.integration

PASSWORD = "SENTINEL-PASSWORD-zzz"


def test_no_sensitive_value_leaves_any_operation(
    app_engine: Engine,
    settings: MlSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = synthetic_vectors(5, 1500)
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
    pseudonyms = {e.user_pseudonym for e in marked if e.user_pseudonym}
    outputs: list[str] = []
    with caplog.at_level(logging.DEBUG):
        result = run_training(
            app_engine,
            settings,
            loaded.start,
            loaded.end,
            history_start=loaded.history_start,
            labels=labels,
        )
        outputs.append(result.report.model_dump_json())
        outputs.extend(v.model_dump_json() for v in list_versions(app_engine))
        activate_version(app_engine, settings, "v0001", approved=True)
        model = load_model(app_engine, settings, "v0001")
        dataset = build_dataset(
            app_engine, loaded.start, loaded.end, history_start=loaded.history_start
        )
        outputs.extend(s.model_dump_json() for s in score_vectors(model, dataset.vectors[:50]))
        # CLI: argumentos y configuración inválidos y errores controlados.
        bad_url = f"postgresql+psycopg://anomaly_app:{PASSWORD}@127.0.0.1:1/db"
        env = {"DATABASE_URL": bad_url, "MODEL_DIR": str(tmp_path)}
        start = "2026-01-01T00:00:00+00:00"
        end = "2026-02-01T00:00:00+00:00"
        cli.main(["train", "--start", start, "--end", end], env, engine_factory=MagicMock())
        cli.main(["train", "--start", "SENTINEL-DATE", "--end", end], env)
        cli.main(["train", "--start", start, "--end", end], {"DATABASE_URL": bad_url})
        cli.main(["activate", "SENTINEL-VERSION"], env)
        cli.main(["status", "--run", "SENTINEL-RUN"], env)
        cli.main(["list"], {"DATABASE_URL": "mysql://u:" + PASSWORD + "@h/db"})

    captured = capsys.readouterr()
    outputs.extend([captured.out, captured.err, caplog.text, json.dumps(str(result.version))])
    blob = "\n".join(outputs)
    for secret in ("SENTINEL", PASSWORD, "192.0.2.77", str(tmp_path), *pseudonyms):
        assert secret not in blob, secret
    assert "training_finished" in caplog.text and "model_activated" in caplog.text
