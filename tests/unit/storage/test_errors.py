"""FR-002-25: errores de la base de datos sin credenciales, valores ni sentencias."""

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from security_anomaly.storage.errors import StorageError, translate_db_error


class _Orig(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("SENTINEL-PASSWORD-x SENTINEL-USER-y")
        self.sqlstate = sqlstate


def _dbapi(sqlstate: str | None) -> DBAPIError:
    return DBAPIError(
        "INSERT INTO events VALUES ('SENTINEL-USER-y')", {"u": "SENTINEL-USER-y"}, _Orig(sqlstate)
    )


@pytest.mark.parametrize(
    "sqlstate,code",
    [
        ("08006", "unavailable"),
        ("08001", "unavailable"),
        ("57P01", "unavailable"),
        ("42501", "permission_denied"),
        ("23505", "integrity"),
        ("23514", "integrity"),
        ("XX000", "unknown"),
        (None, "unknown"),
    ],
)
def test_sqlstate_maps_to_code(sqlstate: str | None, code: str) -> None:
    assert translate_db_error(_dbapi(sqlstate)).code == code


def test_connection_failure_without_sqlstate_is_unavailable() -> None:
    exc = OperationalError("SELECT 1", {}, _Orig(None), connection_invalidated=False)
    assert translate_db_error(exc).code in {"unavailable", "unknown"}


def test_message_is_fixed_and_leaks_nothing() -> None:
    error = translate_db_error(_dbapi("23514"))
    for text in (str(error), repr(error), error.args.__repr__()):
        assert "SENTINEL" not in text
        assert "INSERT" not in text


def test_original_exception_is_discarded() -> None:
    def raiser() -> None:
        try:
            raise _dbapi("23514")
        except DBAPIError as exc:
            raise translate_db_error(exc) from None

    with pytest.raises(StorageError) as caught:
        raiser()
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_unexpected_exception_type_is_unknown() -> None:
    assert translate_db_error(RuntimeError("SENTINEL-USER-y")).code == "unknown"
