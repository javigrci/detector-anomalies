"""FR-002-17, 24: los filtros hostiles se rechazan o se tratan como datos."""

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, text

from security_anomaly.schemas.storage import EventFilter
from security_anomaly.storage import query_events, save_events
from tests.storage_factory import make_events

pytestmark = pytest.mark.integration

HOSTILE = [
    "'; DROP TABLE events; --",
    "x' OR '1'='1",
    "100%",
    "a_b",
    "ñandú\u0000",
    "usr_" + "a" * 32 + "'; --",
    "SENTINEL-USER-alice",
]
# "root" y "user001" no son hostiles como `source` (tienen un formato válido): solo se rechazan
# como seudónimo o IP.
PLAIN_NAMES = ["root", "user001"]


CASES = [
    (field, value)
    for field in ("source", "source_ip", "user_pseudonym")
    for value in [*HOSTILE, *PLAIN_NAMES]
    if not (field == "source" and value in PLAIN_NAMES)
]


@pytest.mark.parametrize(("field", "value"), CASES)
def test_hostile_values_are_rejected_before_the_database(
    app_engine: Engine, field: str, value: str
) -> None:
    save_events(app_engine, make_events(5))
    with pytest.raises(ValidationError) as exc:
        EventFilter.model_validate({field: value})
    assert value not in str(exc.value)
    with app_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM events")).scalar_one() == 5


def test_a_real_username_is_never_accepted_as_a_filter() -> None:
    with pytest.raises(ValidationError):
        EventFilter(user_pseudonym="alice")


def test_valid_filters_with_special_looking_content_return_nothing(app_engine: Engine) -> None:
    save_events(app_engine, make_events(5))
    page = query_events(app_engine, EventFilter(source="a-b"))
    assert page.total == 0
