"""FR-003-13, decisión D5, SPEC §4.4: un evento tardío usa lo conocido hasta su instante."""

import random
import secrets
from datetime import timedelta

from security_anomaly.features.engine import event_order_key
from security_anomaly.features.pipeline import compute_event_features, compute_features
from security_anomaly.ingestion import (
    IngestionPolicy,
    Pseudonymizer,
    SyntheticConfig,
    generate_synthetic,
    ingest_records,
)
from security_anomaly.schemas.event import Outcome
from tests.feature_factory import BASE, make_event, random_stream, reference_window

HISTORY_START = BASE - timedelta(hours=1)
IP = "192.0.2.1"


def _stream() -> list:  # type: ignore[type-arg]
    return [
        make_event(
            i,
            event_id=f"e{i:02d}",
            timestamp=BASE + timedelta(seconds=10 * i),
            outcome=Outcome.FAILURE,
            ip=IP,
        )
        for i in range(10)
    ]


def test_a_late_event_sees_only_what_was_known_up_to_its_instant() -> None:
    known = _stream()
    late = make_event(
        99, event_id="late", timestamp=BASE + timedelta(seconds=35), outcome=Outcome.FAILURE, ip=IP
    )
    vector = compute_event_features(late, known, history_start=HISTORY_START)
    assert vector.features["ip_event_count"] == 5  # e00..e03 (hasta +30 s) y él mismo
    want = reference_window([*known, late], late)
    assert vector.features["ip_event_count"] == want["ip_event_count"]
    assert vector.features["ip_failure_count"] == want["ip_failure_count"]


def test_computing_a_late_event_does_not_modify_vectors_already_returned() -> None:
    known = _stream()
    before = list(compute_features(known, history_start=HISTORY_START))
    snapshot = [v.model_dump_json() for v in before]
    late = make_event(99, event_id="late", timestamp=BASE + timedelta(seconds=35), ip=IP)
    compute_event_features(late, known, history_start=HISTORY_START)
    assert [v.model_dump_json() for v in before] == snapshot
    assert list(compute_features(known, history_start=HISTORY_START)) == before


def test_arrival_order_of_a_late_event_does_not_change_its_own_vector() -> None:
    known = _stream()
    late = make_event(99, event_id="late", timestamp=BASE + timedelta(seconds=35), ip=IP)
    a = compute_event_features(late, known, history_start=HISTORY_START)
    shuffled = list(known)
    random.Random(1).shuffle(shuffled)
    b = compute_event_features(late, shuffled, history_start=HISTORY_START)
    assert a == b


def test_a_dataset_with_out_of_order_events_is_independent_of_arrival_order() -> None:
    dataset = generate_synthetic(SyntheticConfig(seed=4, n_events=600, out_of_order_count=25))
    result = ingest_records(
        dataset.events, policy=IngestionPolicy(), pseudonymizer=Pseudonymizer(secrets.token_hex(32))
    )
    assert result.report.out_of_order  # el generador sí produjo eventos tardíos
    arrival = list(result.events)
    start = min(e.timestamp for e in arrival) - timedelta(hours=1)
    in_arrival_order = list(compute_features(arrival, history_start=start))
    in_reverse = list(compute_features(reversed(arrival), history_start=start))
    assert in_arrival_order == in_reverse
    assert [(v.source, v.event_id) for v in in_arrival_order] == [
        (e.source, e.event_id) for e in sorted(arrival, key=event_order_key)
    ]


def test_late_events_match_the_reference_in_random_streams() -> None:
    for seed in range(10):
        events = random_stream(seed, 60, span_seconds=400)
        by_key = {
            (v.source, v.event_id): v for v in compute_features(events, history_start=HISTORY_START)
        }
        for event in events:
            want = reference_window(events, event)
            assert (
                by_key[(event.source, event.event_id)].features["ip_event_count"]
                == want["ip_event_count"]
            )
