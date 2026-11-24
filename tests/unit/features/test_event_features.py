"""FR-003-01…03: características que dependen solo del propio evento."""

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from security_anomaly.features.engine import event_level_features
from security_anomaly.schemas.event import Action, EventType, Outcome
from tests.feature_factory import make_event

D = datetime(2026, 1, 5, tzinfo=UTC)  # lunes


def _hour(hour: int, minute: int = 0) -> dict[str, float | int | str]:
    return event_level_features(make_event(0, timestamp=D.replace(hour=hour, minute=minute)))


def test_cyclic_hour_at_the_cardinal_points() -> None:
    assert (_hour(0)["hour_sin"], _hour(0)["hour_cos"]) == (0.0, 1.0)
    assert (_hour(6)["hour_sin"], _hour(6)["hour_cos"]) == (1.0, 0.0)
    assert (_hour(12)["hour_sin"], _hour(12)["hour_cos"]) == (0.0, -1.0)
    assert (_hour(18)["hour_sin"], _hour(18)["hour_cos"]) == (-1.0, -0.0)


def test_midnight_neighbours_are_close_and_opposites_are_far() -> None:
    late, early = _hour(23, 59), _hour(0, 1)
    gap = math.hypot(
        float(late["hour_sin"]) - float(early["hour_sin"]),
        float(late["hour_cos"]) - float(early["hour_cos"]),
    )
    assert gap < 0.3
    noon, midnight = _hour(12), _hour(0)
    assert float(noon["hour_cos"]) == -float(midnight["hour_cos"])  # opuestas


def test_only_the_whole_hour_matters() -> None:
    assert _hour(7, 0) == _hour(7, 59)


def test_hour_values_are_rounded_to_twelve_decimals() -> None:
    for hour in range(24):
        for name in ("hour_sin", "hour_cos"):
            value = _hour(hour)[name]
            assert isinstance(value, float) and value == round(value, 12)


def test_hour_and_day_are_always_utc() -> None:
    plus2 = timezone(timedelta(hours=2))
    # 01:30 del martes 6 en UTC+2 es 23:30 del lunes 5 en UTC.
    event = make_event(0, timestamp=datetime(2026, 1, 6, 1, 30, tzinfo=plus2))
    features = event_level_features(event)
    assert features["day_of_week"] == 0
    assert (features["hour_sin"], features["hour_cos"]) == (
        _hour(23)["hour_sin"],
        _hour(23)["hour_cos"],
    )
    minus5 = timezone(timedelta(hours=-5))
    # 22:00 del 31/12/2025 en UTC-5 es 03:00 del 1/1/2026 (jueves) en UTC: cambio de año.
    nye = event_level_features(make_event(0, timestamp=datetime(2025, 12, 31, 22, tzinfo=minus5)))
    assert nye["day_of_week"] == 3
    assert nye == event_level_features(make_event(0, timestamp=datetime(2026, 1, 1, 3, tzinfo=UTC)))


@pytest.mark.parametrize("offset", range(7))
def test_day_of_week_monday_is_zero(offset: int) -> None:
    event = make_event(0, timestamp=D + timedelta(days=offset))
    assert event_level_features(event)["day_of_week"] == offset


def test_categories_are_kept_as_catalog_strings() -> None:
    event = make_event(
        0,
        source="linux-auth",
        event_type=EventType.PRIVILEGE_ESCALATION,
        action=Action.SUDO,
        outcome=Outcome.FAILURE,
    )
    features = event_level_features(event)
    assert features["event_type"] == "privilege_escalation"
    assert features["action"] == "sudo"
    assert features["outcome"] == "failure"
    assert features["source"] == "linux-auth"
    assert all(type(features[k]) is str for k in ("event_type", "action", "outcome", "source"))


def test_a_source_never_seen_before_is_kept_without_error() -> None:
    assert event_level_features(make_event(0, source="never-seen-1"))["source"] == "never-seen-1"


def test_event_level_values_do_not_depend_on_other_fields_or_events() -> None:
    a = make_event(
        0, event_id="a", timestamp=D, user="usr_" + "a" * 32, ip="192.0.2.1", host="srv-demo-01"
    )
    b = make_event(7, event_id="b", timestamp=D, user=None, ip=None, host=None)
    assert event_level_features(a) == event_level_features(b)


def test_exactly_the_seven_event_level_names_are_returned_in_order() -> None:
    assert list(event_level_features(make_event(0))) == [
        "hour_sin",
        "hour_cos",
        "day_of_week",
        "event_type",
        "action",
        "outcome",
        "source",
    ]
