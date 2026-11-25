"""Errores controlados del entrenamiento (FR-004-31; research R14).

``MlError`` lleva un código estable y un mensaje fijo: nunca valores de datos, rutas internas ni
credenciales.
"""

from typing import Literal

ErrorCode = Literal[
    "insufficient_data",
    "invalid_schema",
    "invalid_parameters",
    "training_in_progress",
    "training_failed",
    "unknown_version",
    "unknown_run",
    "approval_required",
    "no_active_model",
    "artifact_path",
    "artifact_integrity",
    "incompatible_environment",
    "incompatible_features",
]

_MESSAGES: dict[str, str] = {
    "insufficient_data": "No hay datos suficientes para entrenar, calibrar y probar",
    "invalid_schema": "Los vectores no tienen el esquema de características esperado",
    "invalid_parameters": "Los parámetros del entrenamiento o de la puntuación no son válidos",
    "training_in_progress": "Ya hay un entrenamiento en curso",
    "training_failed": "El entrenamiento ha fallado",
    "unknown_version": "La versión de modelo no existe",
    "unknown_run": "El entrenamiento no existe",
    "approval_required": "La operación exige una aprobación explícita",
    "no_active_model": "No hay ninguna versión de modelo activa",
    "artifact_path": "La ubicación del artefacto no es válida",
    "artifact_integrity": "El artefacto no coincide con su registro",
    "incompatible_environment": "Las versiones de las librerías no coinciden con las del modelo",
    "incompatible_features": "El vector no tiene el esquema de características del modelo",
}


class MlError(Exception):
    """Fallo del entrenamiento o de la carga de modelos, con un código y un mensaje fijos."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(_MESSAGES[code])
        self.code: ErrorCode = code
