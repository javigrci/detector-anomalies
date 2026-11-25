"""CLI mínima de operación: ``train``, ``status``, ``list`` y ``activate`` (research R13).

Solo ``argparse``. Una línea JSON con recuentos, estados, versiones y códigos; nunca valores de
datos, rutas ni credenciales. Códigos de salida: 0 correcto, 2 configuración o argumentos inválidos
(se nombra la variable, no su valor), 1 error controlado (solo su ``code``). Entrenar y activar los
lanza una persona; ``activate`` exige ``--approve`` (Principio VII).
"""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import Engine, create_engine

from security_anomaly.core.config import ConfigError, load_settings
from security_anomaly.features import FeatureError
from security_anomaly.ml.config import load_ml_settings
from security_anomaly.ml.errors import MlError
from security_anomaly.ml.registry import (
    activate_version,
    get_training_run,
    list_training_runs,
    list_versions,
)
from security_anomaly.ml.service import run_training
from security_anomaly.schemas.ml import MlPolicy, ModelVersion, TrainingRun
from security_anomaly.storage import StorageError

EngineFactory = Callable[[str], Engine]
MAX_LABELS_BYTES = 5_000_000
_CONNECT_TIMEOUT_S = 5


def _default_engine(url: str) -> Engine:
    return create_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": _CONNECT_TIMEOUT_S}
    )


class _Usage(Exception):
    """Argumentos inválidos; el mensaje es fijo y no repite lo escrito."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, "Argumentos inválidos.\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m security_anomaly.ml")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train", help="entrena, evalúa y registra un modelo (no lo activa)")
    train.add_argument("--start", required=True)
    train.add_argument("--end", required=True)
    train.add_argument("--history-start", default=None)
    train.add_argument("--labels", default=None, help="JSON {event_id: etiqueta}")
    train.add_argument("--n-estimators", type=int, default=None)
    status = commands.add_parser("status", help="estado de un entrenamiento o de los recientes")
    status.add_argument("--run", default=None)
    commands.add_parser("list", help="versiones registradas")
    activate = commands.add_parser("activate", help="activa una versión (exige --approve)")
    activate.add_argument("version")
    activate.add_argument("--approve", action="store_true")
    return parser


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _Usage from None
    if parsed.tzinfo is None:
        raise _Usage
    return parsed


def _read_labels(path: str) -> dict[str, str]:
    """Etiquetas externas: solo JSON de tamaño acotado, nunca código ni ``pickle``."""
    file = Path(path)
    try:
        if file.stat().st_size > MAX_LABELS_BYTES:
            raise _Usage
        data = json.loads(file.read_text())
    except (OSError, ValueError):
        raise _Usage from None
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise _Usage
    return data


def _run_json(run: TrainingRun) -> dict[str, object]:
    return {
        "run_id": str(run.id),
        "status": run.status,
        "version": run.version,
        "error_code": run.error_code,
        "n_train": run.n_train,
        "n_calibration": run.n_calibration,
        "n_test": run.n_test,
        "started_at": run.started_at.isoformat(),
        "finished_at": None if run.finished_at is None else run.finished_at.isoformat(),
    }


def _version_json(version: ModelVersion) -> dict[str, object]:
    return {
        "version": version.version,
        "number": version.number,
        "active": version.active,
        "schema_version": version.schema_version,
        "created_at": version.created_at.isoformat(),
        "activated_at": None if version.activated_at is None else version.activated_at.isoformat(),
    }


def _engine(environ: Mapping[str, str] | None, factory: EngineFactory) -> Engine:
    return factory(load_settings(environ).database_url.get_secret_value())


def _command(
    args: argparse.Namespace, environ: Mapping[str, str] | None, factory: EngineFactory
) -> dict[str, object]:
    if args.command == "activate" and not args.approve:
        raise MlError("approval_required")
    if args.command == "train":
        start = _instant(args.start)
        end = _instant(args.end)
        history_start = start if args.history_start is None else _instant(args.history_start)
        if start >= end:
            raise _Usage
        labels = None if args.labels is None else _read_labels(args.labels)
        settings = load_ml_settings(environ)
        policy = settings.policy
        if args.n_estimators is not None:
            try:
                policy = MlPolicy.model_validate(
                    {**policy.model_dump(), "n_estimators": args.n_estimators}
                )
            except ValidationError:
                raise _Usage from None
        engine = _engine(environ, factory)
        try:
            result = run_training(
                engine,
                settings,
                start,
                end,
                history_start=history_start,
                policy=policy,
                labels=labels,
            )
        finally:
            engine.dispose()
        return {
            "run_id": str(result.run_id),
            "version": result.version.version,
            "n_test": result.report.n_test,
            "alert_rate": result.report.alert_rate,
            "labelled": result.report.labelled,
        }
    engine = _engine(environ, factory)
    try:
        if args.command == "status":
            if args.run is None:
                return {"runs": [_run_json(r) for r in list_training_runs(engine, 10)]}
            try:
                run_id = UUID(args.run)
            except ValueError:
                raise _Usage from None
            return _run_json(get_training_run(engine, run_id))
        if args.command == "list":
            return {"versions": [_version_json(v) for v in list_versions(engine)]}
        settings = load_ml_settings(environ)
        return _version_json(activate_version(engine, settings, args.version, approved=True))
    finally:
        engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    engine_factory: EngineFactory = _default_engine,
) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exit_:
        return int(exit_.code) if isinstance(exit_.code, int) else 2
    try:
        print(json.dumps(_command(args, environ, engine_factory)))
        return 0
    except _Usage:
        print("Argumentos inválidos.", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (MlError, StorageError, FeatureError) as exc:
        print(json.dumps({"error": exc.code}), file=sys.stderr)
        return 1
    except Exception:
        print(json.dumps({"error": "unknown"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
