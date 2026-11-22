"""Errores controlados de la persistencia (FR-002-25; research R11).

``StorageError`` lleva un código estable y un mensaje fijo: nunca credenciales, valores de eventos
ni sentencias con parámetros. La excepción original se descarta.
"""

from typing import Literal

from sqlalchemy.exc import DBAPIError, OperationalError

ErrorCode = Literal["unavailable", "permission_denied", "integrity", "unknown"]

_MESSAGES: dict[str, str] = {
    "unavailable": "La base de datos no está disponible",
    "permission_denied": "La base de datos denegó la operación por falta de privilegios",
    "integrity": "La base de datos rechazó los datos por una restricción de integridad",
    "unknown": "Error de base de datos",
}


class StorageError(Exception):
    """Fallo de la base de datos con un código estable y un mensaje fijo."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(_MESSAGES[code])
        self.code: ErrorCode = code


def _sqlstate(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", exc)
    state = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return state if isinstance(state, str) else None


def translate_db_error(exc: BaseException) -> StorageError:
    """Traduce una excepción de la base de datos; el llamador debe relanzar con ``from None``."""
    state = _sqlstate(exc)
    if state is not None:
        if state == "42501":
            return StorageError("permission_denied")
        if state.startswith("23"):
            return StorageError("integrity")
        if state.startswith(("08", "57", "53")):
            return StorageError("unavailable")
        return StorageError("unknown")
    if isinstance(exc, OperationalError):
        return StorageError("unavailable")
    if isinstance(exc, DBAPIError):
        return StorageError("unknown")
    return StorageError("unknown")
