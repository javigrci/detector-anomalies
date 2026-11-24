"""Errores controlados de las características (FR-003-25; research R9).

``FeatureError`` lleva un código estable y un mensaje fijo: nunca valores de los datos (IP,
seudónimo, host, identificador) ni marcas de tiempo concretas.
"""

from typing import Literal

ErrorCode = Literal[
    "invalid_history_start", "event_before_history", "unsorted_input", "duplicate_event"
]

_MESSAGES: dict[str, str] = {
    "invalid_history_start": "history_start debe ser una fecha con zona horaria",
    "event_before_history": "Hay un evento anterior al inicio declarado de la historia",
    "unsorted_input": "La entrada no está ordenada por (timestamp, source, event_id)",
    "duplicate_event": "La entrada contiene un evento repetido",
}


class FeatureError(Exception):
    """Entrada inválida para el cálculo de características, con un código y un mensaje fijos."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(_MESSAGES[code])
        self.code: ErrorCode = code
