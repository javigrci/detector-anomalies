"""Orquestación del entrenamiento: dataset, separación, modelo, evaluación, artefacto y registro.

Un entrenamiento nunca activa su resultado (Principio VII) y un fallo deja el registro en ``failed``
sin versión a medias ni artefacto huérfano.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Engine

from security_anomaly.features import FeatureError
from security_anomaly.ml import artifacts, registry
from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.dataset import build_dataset, dataset_fingerprint, split_temporal
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.evaluation import evaluate
from security_anomaly.ml.pipeline import train_model
from security_anomaly.schemas.ml import EvaluationReport, MlPolicy, ModelVersion
from security_anomaly.storage import StorageError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingResult:
    run_id: UUID
    version: ModelVersion
    report: EvaluationReport


def _error_code(error: Exception) -> str:
    if isinstance(error, (MlError, StorageError, FeatureError)):
        return str(error.code)
    return "training_failed"


def run_training(
    engine: Engine,
    settings: MlSettings,
    start: datetime,
    end: datetime,
    *,
    history_start: datetime,
    policy: MlPolicy | None = None,
    labels: Any = None,
) -> TrainingResult:
    """Entrena, evalúa, guarda y registra un modelo; no lo activa."""
    started = time.perf_counter()
    effective = policy if policy is not None else settings.policy
    registry.mark_stale_runs_failed(engine, timedelta(minutes=settings.stale_minutes))
    run_id = registry.begin_training_run(engine, effective.model_dump())
    logger.info("training_started", extra={"fields": {"run_id": str(run_id)}})
    saved: str | None = None
    try:
        dataset = build_dataset(engine, start, end, history_start=history_start)
        partition = split_temporal(dataset, effective)
        fingerprint = dataset_fingerprint(dataset)
        registry.record_training_dataset(
            engine,
            run_id,
            dataset_hash=fingerprint,
            n_train=len(partition.train),
            n_calibration=len(partition.calibration),
            n_test=len(partition.test),
        )
        model = train_model(partition, effective)
        registry.touch_training_run(engine, run_id)
        report = evaluate(model, partition, labels=labels)
        registry.touch_training_run(engine, run_id)
        version_name = registry.next_version(engine)
        saved, digest = artifacts.save_artifact(settings.model_dir, version_name, model)
        version = registry.register_model_version(
            engine,
            run_id=run_id,
            version=version_name,
            schema_version=model.schema_version,
            schema_fingerprint=model.schema_fingerprint,
            params=effective.model_dump(),
            metrics=report.model_dump(mode="json"),
            dataset_hash=fingerprint,
            artifact_file=saved,
            artifact_sha256=digest,
            library_versions=model.library_versions,
        )
    except Exception as error:
        if saved is not None:
            artifacts.remove_artifact(settings.model_dir, saved)
        registry.fail_training_run(engine, run_id, _error_code(error))
        if isinstance(error, (MlError, StorageError, FeatureError)):
            raise
        raise MlError("training_failed") from None
    logger.info(
        "training_finished",
        extra={
            "fields": {
                "run_id": str(run_id),
                "version": version.version,
                "n_train": len(partition.train),
                "n_calibration": len(partition.calibration),
                "n_test": len(partition.test),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
        },
    )
    return TrainingResult(run_id=run_id, version=version, report=report)
