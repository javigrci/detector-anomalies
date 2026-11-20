"""contracts/ingestion-api.md: excepciones de la ingesta, sin valores de datos."""

import pytest

from security_anomaly.ingestion.errors import BatchRejected, IngestionError, PseudonymKeyMissing
from security_anomaly.schemas.ingestion import BatchRejectionCode


def test_batch_rejected_exposes_code_and_limit() -> None:
    error = BatchRejected(BatchRejectionCode.TOO_MANY_EVENTS, limit=10_000)
    assert error.code == BatchRejectionCode.TOO_MANY_EVENTS
    assert error.limit == 10_000
    assert "too_many_events" in str(error)
    assert "10000" in str(error)


def test_batch_rejected_limit_is_optional() -> None:
    error = BatchRejected(BatchRejectionCode.INVALID_FORMAT)
    assert error.limit is None
    assert "invalid_format" in str(error)


def test_errors_share_a_base_class() -> None:
    assert issubclass(BatchRejected, IngestionError)
    assert issubclass(PseudonymKeyMissing, IngestionError)
    with pytest.raises(IngestionError):
        raise PseudonymKeyMissing
    with pytest.raises(IngestionError):
        raise BatchRejected(BatchRejectionCode.FILE_TOO_LARGE, limit=1)


def test_missing_key_message_names_the_variable_only() -> None:
    message = str(PseudonymKeyMissing())
    assert "PSEUDONYM_KEY" in message
