"""Registro de entrenamientos y versiones de modelo en PostgreSQL (research R9-R12; ADR 0006).

Rol de BD: ``anomaly_app``. La concurrencia 1 y la única versión activa las garantizan índices
únicos parciales; la inmutabilidad de las versiones, los permisos por columna. Las consultas están
parametrizadas y los errores se traducen a ``MlError`` o ``StorageError`` sin valores de datos.
"""

import logging
import time
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from security_anomaly.ml import artifacts
from security_anomaly.ml.config import MlSettings
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.schema import model_versions, training_runs
from security_anomaly.schemas.ml import ModelVersion, TrainingRun
from security_anomaly.storage.errors import translate_db_error

logger = logging.getLogger(__name__)

_ONE_RUNNING = "uq_training_runs_one_running"
_ADVISORY_KEY = 4_204_001  # candado de asesoramiento de las activaciones


def _to_run(row: Any) -> TrainingRun:
    return TrainingRun.model_validate(dict(row._mapping))


def _to_version(row: Any) -> ModelVersion:
    return ModelVersion.model_validate(dict(row._mapping))


def next_version(engine: Engine) -> str:
    """Siguiente versión (``v0001``…); segura porque solo hay un entrenamiento a la vez."""
    try:
        with engine.connect() as connection:
            highest = connection.execute(
                select(func.coalesce(func.max(model_versions.c.number), 0))
            )
            return f"v{int(highest.scalar_one()) + 1:04d}"
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def begin_training_run(engine: Engine, params: dict[str, object]) -> UUID:
    """Abre un entrenamiento ``running``; un segundo a la vez lo impide el índice único."""
    run_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(training_runs).values(id=run_id, status="running", params=params)
            )
    except IntegrityError as exc:
        diag = getattr(exc.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == _ONE_RUNNING:
            raise MlError("training_in_progress") from None
        raise translate_db_error(exc) from None
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    return run_id


def _update_run(engine: Engine, run_id: UUID, **values: object) -> None:
    try:
        with engine.begin() as connection:
            result = connection.execute(
                update(training_runs).where(training_runs.c.id == run_id).values(**values)
            )
            if result.rowcount == 0:
                raise MlError("unknown_run")
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def touch_training_run(engine: Engine, run_id: UUID) -> None:
    """Actualiza el latido: un entrenamiento vivo lo hace en cada fase."""
    _update_run(engine, run_id, heartbeat_at=func.now())


def record_training_dataset(
    engine: Engine,
    run_id: UUID,
    *,
    dataset_hash: str,
    n_train: int,
    n_calibration: int,
    n_test: int,
) -> None:
    _update_run(
        engine,
        run_id,
        heartbeat_at=func.now(),
        dataset_hash=dataset_hash,
        n_train=n_train,
        n_calibration=n_calibration,
        n_test=n_test,
    )


def fail_training_run(engine: Engine, run_id: UUID, error_code: str) -> None:
    """Marca el entrenamiento como fallido con un código sin valores de datos."""
    _update_run(
        engine,
        run_id,
        status="failed",
        finished_at=func.now(),
        heartbeat_at=func.now(),
        error_code=error_code,
    )


def mark_stale_runs_failed(engine: Engine, max_age: timedelta) -> int:
    """Marca ``failed`` (``stale``) los entrenamientos ``running`` sin latido reciente."""
    try:
        with engine.begin() as connection:
            result = connection.execute(
                update(training_runs)
                .where(
                    training_runs.c.status == "running",
                    training_runs.c.heartbeat_at < func.now() - max_age,
                )
                .values(status="failed", finished_at=func.now(), error_code="stale")
            )
            return int(result.rowcount)
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def register_model_version(
    engine: Engine,
    *,
    run_id: UUID,
    version: str,
    schema_version: int,
    schema_fingerprint: str,
    params: dict[str, object],
    metrics: dict[str, object],
    dataset_hash: str,
    artifact_file: str,
    artifact_sha256: str,
    library_versions: dict[str, str],
) -> ModelVersion:
    """Registra la versión (sin activarla) y cierra el entrenamiento, en una transacción."""
    try:
        with engine.begin() as connection:
            number = int(version[1:])
            connection.execute(
                insert(model_versions).values(
                    version=version,
                    number=number,
                    run_id=run_id,
                    schema_version=schema_version,
                    schema_fingerprint=schema_fingerprint,
                    params=params,
                    metrics=metrics,
                    dataset_hash=dataset_hash,
                    artifact_file=artifact_file,
                    artifact_sha256=artifact_sha256,
                    library_versions=library_versions,
                )
            )
            connection.execute(
                update(training_runs)
                .where(training_runs.c.id == run_id)
                .values(
                    status="succeeded",
                    finished_at=func.now(),
                    heartbeat_at=func.now(),
                    version=version,
                )
            )
            row = connection.execute(
                select(model_versions).where(model_versions.c.version == version)
            ).one()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    return _to_version(row)


def get_training_run(engine: Engine, run_id: UUID) -> TrainingRun:
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(training_runs).where(training_runs.c.id == run_id)
            ).first()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    if row is None:
        raise MlError("unknown_run")
    return _to_run(row)


def list_training_runs(engine: Engine, limit: int = 20) -> list[TrainingRun]:
    """Los entrenamientos más recientes primero."""
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(training_runs).order_by(training_runs.c.started_at.desc()).limit(limit)
            ).all()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    return [_to_run(row) for row in rows]


def list_versions(engine: Engine) -> list[ModelVersion]:
    """Las versiones registradas, de la más antigua a la más reciente."""
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(model_versions).order_by(model_versions.c.number)
            ).all()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    return [_to_version(row) for row in rows]


def get_version(engine: Engine, version: str) -> ModelVersion:
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(model_versions).where(model_versions.c.version == version)
            ).first()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    if row is None:
        raise MlError("unknown_version")
    return _to_version(row)


def get_active_version(engine: Engine) -> ModelVersion | None:
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(model_versions).where(model_versions.c.active.is_(True))
            ).first()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    return None if row is None else _to_version(row)


def _activate_in_database(engine: Engine, version: str) -> ModelVersion:
    """Una sola versión activa: candado de asesoramiento y dos UPDATE en una transacción."""
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_KEY})
            connection.execute(
                update(model_versions).where(model_versions.c.active.is_(True)).values(active=False)
            )
            result = connection.execute(
                update(model_versions)
                .where(model_versions.c.version == version)
                .values(active=True, activated_at=func.now())
            )
            if result.rowcount == 0:
                raise MlError("unknown_version")
            row = connection.execute(
                select(model_versions).where(model_versions.c.version == version)
            ).one()
    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    return _to_version(row)


def activate_version(
    engine: Engine, settings: MlSettings, version: str, *, approved: bool
) -> ModelVersion:
    """Activa una versión solo con aprobación explícita y tras verificar su artefacto.

    Deja una sola versión activa a la vez, incluso con activaciones simultáneas.
    """
    if approved is not True:
        raise MlError("approval_required")
    started = time.perf_counter()
    record = get_version(engine, version)
    path = artifacts.resolve_artifact_path(settings.model_dir, record.artifact_file)
    artifacts.verify_digest(path, record.artifact_sha256)
    activated = _activate_in_database(engine, version)
    log_activated(activated.version, time.perf_counter() - started)
    return activated


def load_model(engine: Engine, settings: MlSettings, version: str) -> Any:
    """Carga una versión registrada desde ``MODEL_DIR`` tras verificar su integridad."""
    return artifacts.load_artifact(settings.model_dir, get_version(engine, version))


def load_active_model(engine: Engine, settings: MlSettings) -> Any:
    """Carga la versión activa; ``MlError("no_active_model")`` si no hay ninguna."""
    record = get_active_version(engine)
    if record is None:
        raise MlError("no_active_model")
    return artifacts.load_artifact(settings.model_dir, record)


def log_activated(version: str, seconds: float) -> None:
    """Solo la versión y la duración (FR-004-31)."""
    logger.info(
        "model_activated",
        extra={"fields": {"version": version, "duration_ms": round(seconds * 1000)}},
    )
