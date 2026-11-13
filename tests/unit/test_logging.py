"""FR-000-05: logs estructurados y legibles por máquina."""

import io
import json
import logging
from collections.abc import Iterator
from datetime import datetime

import pytest

from security_anomaly.core.logging import JsonFormatter, configure_logging
from security_anomaly.core.request_id import request_id_var


@pytest.fixture
def stream_logger() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.json")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    yield logger, stream
    logger.handlers = []


def _last(stream: io.StringIO) -> dict[str, object]:
    line = stream.getvalue().strip().splitlines()[-1]
    parsed: dict[str, object] = json.loads(line)
    return parsed


def test_record_has_required_fields(stream_logger: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = stream_logger
    logger.info("hola")
    record = _last(stream)
    assert record["level"] == "INFO"
    assert record["logger"] == "test.json"
    assert record["message"] == "hola"
    parsed = datetime.fromisoformat(str(record["timestamp"]))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_request_id_is_included_only_when_present(
    stream_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = stream_logger
    logger.info("sin id")
    assert "request_id" not in _last(stream)
    token = request_id_var.set("abc-123")
    try:
        logger.info("con id")
    finally:
        request_id_var.reset(token)
    assert _last(stream)["request_id"] == "abc-123"


def test_message_with_newlines_stays_on_one_line(
    stream_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = stream_logger
    logger.info("linea1\nlinea2")
    assert len(stream.getvalue().strip().splitlines()) == 1
    assert _last(stream)["message"] == "linea1\nlinea2"


def test_extra_fields_are_serialized(stream_logger: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = stream_logger
    logger.info("peticion", extra={"fields": {"status": 200}})
    assert _last(stream)["status"] == 200


def test_exception_is_logged_as_text(stream_logger: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = stream_logger
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("fallo")
    assert "ValueError" in str(_last(stream)["exception"])


def test_configure_logging_respects_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
    configure_logging("INFO")
    assert logging.getLogger().level == logging.INFO
