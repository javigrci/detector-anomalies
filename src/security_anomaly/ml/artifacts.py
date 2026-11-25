"""Guardado atómico y carga segura de artefactos de modelo (research R8; ADR 0006).

``joblib`` usa ``pickle``: deserializar un archivo manipulado ejecuta código. Por eso un artefacto
solo se abre desde ``MODEL_DIR``, con un nombre derivado de la versión registrada, y **después** de
verificar que su huella SHA-256 coincide con la registrada. Nunca se abre una ruta recibida de un
usuario.
"""

import contextlib
import hashlib
import hmac
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import joblib

from security_anomaly.ml.errors import MlError
from security_anomaly.schemas.ml import ModelVersion

_VERSION = re.compile(r"v[0-9]{4,}")
_FILE = re.compile(r"model-v[0-9]{4,}\.joblib")
_CHUNK = 1024 * 1024


def artifact_filename(version: str) -> str:
    """Nombre del archivo de una versión; patrón estricto, sin componentes de ruta."""
    if not _VERSION.fullmatch(version):
        raise MlError("artifact_path")
    return f"model-{version}.joblib"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artifact_path(model_dir: Path, file_name: str) -> Path:
    """Ruta real del artefacto, garantizada dentro de ``model_dir`` y de un archivo regular."""
    if not _FILE.fullmatch(file_name):
        raise MlError("artifact_path")
    real_dir = model_dir.resolve()
    candidate = real_dir / file_name
    if candidate.is_symlink():
        raise MlError("artifact_path")
    if not candidate.exists():
        raise MlError("artifact_integrity")
    resolved = candidate.resolve()
    if resolved.parent != real_dir or not resolved.is_file():
        raise MlError("artifact_path")
    return resolved


def save_artifact(model_dir: Path, version: str, model: Any) -> tuple[str, str]:
    """Guarda el modelo de forma atómica y devuelve ``(nombre de archivo, SHA-256)``.

    Escribe en un temporal del mismo directorio y lo renombra; nunca sobrescribe un artefacto.
    """
    file_name = artifact_filename(version)
    final = model_dir.resolve() / file_name
    if final.exists() or final.is_symlink():
        raise MlError("artifact_path")
    descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".joblib", dir=model_dir)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        joblib.dump(model, temporary_path)
        os.replace(temporary_path, final)
    except Exception:
        with contextlib.suppress(OSError):
            temporary_path.unlink()
        raise MlError("artifact_path") from None
    return file_name, sha256_file(final)


def remove_artifact(model_dir: Path, file_name: str) -> None:
    """Elimina un artefacto propio (p. ej. tras un fallo al registrarlo); nunca falla."""
    with contextlib.suppress(MlError, OSError):
        resolve_artifact_path(model_dir, file_name).unlink()


def verify_digest(path: Path, expected_sha256: str) -> None:
    """Comprueba que la huella del archivo coincide con la registrada, sin abrirlo como modelo."""
    if not hmac.compare_digest(sha256_file(path), expected_sha256):
        raise MlError("artifact_integrity")


def load_artifact(model_dir: Path, record: ModelVersion) -> Any:
    """Carga el modelo registrado: ruta segura, huella verificada **antes** de abrirlo y versiones.

    Nunca se abre un archivo cuya huella no coincide con la registrada ni con otras versiones de las
    librerías de las que se entrenó.
    """
    from security_anomaly.ml.pipeline import TrainedModel, library_versions

    path = resolve_artifact_path(model_dir, record.artifact_file)
    verify_digest(path, record.artifact_sha256)
    if dict(record.library_versions) != library_versions():
        raise MlError("incompatible_environment")
    try:
        model = joblib.load(path)
    except Exception:
        raise MlError("artifact_integrity") from None
    if not isinstance(model, TrainedModel) or model.schema_fingerprint != record.schema_fingerprint:
        raise MlError("artifact_integrity")
    return model
