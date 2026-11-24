"""FR-003-16 y research R7: `features_for_range` sobre eventos guardados con el incremento 2."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from security_anomaly.features.errors import FeatureError
from security_anomaly.features.pipeline import compute_features, features_for_range
from security_anomaly.schemas.event import NormalizedEvent, Outcome
from security_anomaly.schemas.features import FeatureVector
from security_anomaly.storage import save_events
from tests.feature_factory import BASE, make_event, random_stream

pytestmark = pytest.mark.integration

HISTORY_START = BASE - timedelta(hours=1)
START = BASE + timedelta(seconds=300)
END = BASE + timedelta(seconds=900)


def _in_range(
    vectors: Iterable[FeatureVector], start: datetime = START, end: datetime = END
) -> dict[tuple[str, str], FeatureVector]:
    return {(v.source, v.event_id): v for v in vectors if start <= v.timestamp < end}


def _stream() -> list[NormalizedEvent]:
    return random_stream(3, 400, span_seconds=1200, no_user_rate=0.2)


def test_range_vectors_equal_the_in_memory_ones(app_engine: Engine) -> None:
    events = _stream()
    save_events(app_engine, events)
    expected = _in_range(compute_features(events, history_start=HISTORY_START))
    got = {
        (v.source, v.event_id): v
        for v in features_for_range(
            app_engine, START, END, history_start=HISTORY_START, chunk_size=37
        )
    }
    assert expected and got == expected


def test_nothing_at_or_after_end_influences_a_vector(app_engine: Engine) -> None:
    events = _stream()
    flood = [
        make_event(
            900 + i,
            event_id=f"zz-{i:03d}",
            timestamp=END + timedelta(seconds=i // 3),
            outcome=Outcome.FAILURE,
            ip="192.0.2.1",
        )
        for i in range(120)
    ]
    on_the_edge = make_event(
        999, event_id="edge", timestamp=END, outcome=Outcome.FAILURE, ip="192.0.2.1"
    )
    save_events(app_engine, events)
    before = {
        (v.source, v.event_id): v
        for v in features_for_range(app_engine, START, END, history_start=HISTORY_START)
    }
    save_events(app_engine, [*flood, on_the_edge])
    after = {
        (v.source, v.event_id): v
        for v in features_for_range(app_engine, START, END, history_start=HISTORY_START)
    }
    assert after == before
    assert all(START <= v.timestamp < END for v in after.values())
    assert ("linux-auth", "edge") not in after


def test_only_events_inside_the_declared_history_are_used(app_engine: Engine) -> None:
    events = _stream()
    save_events(app_engine, events)
    history_start = BASE + timedelta(seconds=200)
    kept = [e for e in events if e.timestamp.astimezone(UTC) >= history_start]
    expected = _in_range(compute_features(kept, history_start=history_start))
    got = {
        (v.source, v.event_id): v
        for v in features_for_range(app_engine, START, END, history_start=history_start)
    }
    assert got == expected


def test_invalid_arguments_fail_before_reading(app_engine: Engine) -> None:
    with pytest.raises(ValueError, match=r"\S"):
        list(features_for_range(app_engine, END, START, history_start=HISTORY_START))
    with pytest.raises(ValueError, match=r"\S"):
        list(features_for_range(app_engine, datetime(2026, 1, 1), END, history_start=HISTORY_START))
    with pytest.raises(FeatureError) as caught:
        list(features_for_range(app_engine, START, END, history_start=datetime(2026, 1, 1)))
    assert caught.value.code == "invalid_history_start"


def test_an_empty_range_gives_no_vectors(app_engine: Engine) -> None:
    assert list(features_for_range(app_engine, START, END, history_start=HISTORY_START)) == []
