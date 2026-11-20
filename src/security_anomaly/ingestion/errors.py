"""Excepciones de la ingesta. Sus mensajes nunca incluyen valores de los datos."""

from security_anomaly.schemas.ingestion import BatchRejectionCode


class IngestionError(Exception):
    """Base de los errores de ingesta."""


class BatchRejected(IngestionError):
    """El archivo o el lote se rechazan enteros; ``limit`` es el valor del límite, no del dato."""

    def __init__(self, code: BatchRejectionCode, limit: int | None = None) -> None:
        self.code = code
        self.limit = limit
        message = f"Lote rechazado: {code.value}"
        if limit is not None:
            message += f" (límite {limit})"
        super().__init__(message)


class PseudonymKeyMissing(IngestionError):
    """Hay usuarios que seudonimizar y no hay clave configurada (falla cerrado)."""

    def __init__(self) -> None:
        super().__init__("Falta la clave de seudonimización (PSEUDONYM_KEY); no se emite nada.")
