"""FR-003-25: errores controlados de las características, sin valores de los datos."""

import pytest

from security_anomaly.features.errors import FeatureError

CODES = ["invalid_history_start", "event_before_history", "unsorted_input", "duplicate_event"]


@pytest.mark.parametrize("code", CODES)
def test_each_code_has_a_fixed_message(code: str) -> None:
    error = FeatureError(code)  # type: ignore[arg-type]
    assert error.code == code
    assert str(error) and str(error) == str(FeatureError(code))


def test_messages_are_distinct_per_code() -> None:
    assert len({str(FeatureError(c)) for c in CODES}) == len(CODES)  # type: ignore[arg-type]


@pytest.mark.parametrize("code", CODES)
def test_no_data_in_text_repr_or_args(code: str) -> None:
    error = FeatureError(code)  # type: ignore[arg-type]
    for text in (str(error), repr(error), repr(error.args)):
        for forbidden in ("SENTINEL", "192.0.2", "usr_", "srv-demo"):
            assert forbidden not in text


def test_it_is_an_exception_that_can_be_raised() -> None:
    with pytest.raises(FeatureError) as caught:
        raise FeatureError("unsorted_input")
    assert caught.value.code == "unsorted_input"
