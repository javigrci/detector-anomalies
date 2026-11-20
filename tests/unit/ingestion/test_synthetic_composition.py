"""FR-001-27, 28 y 29: composición, etiquetas aparte y datos solo ficticios."""

import ipaddress
import re
from collections import Counter
from datetime import datetime

import pytest

from security_anomaly.ingestion import (
    IngestionPolicy,
    Pseudonymizer,
    SyntheticConfig,
    SyntheticDataset,
    generate_synthetic,
    ingest_records,
)
from security_anomaly.schemas.event import EventType, EventV1

DOC_NETWORKS = [
    ipaddress.ip_network(n)
    for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
]
V1_KEYS = {
    "event_id",
    "timestamp",
    "source",
    "event_type",
    "action",
    "outcome",
    "username",
    "source_ip",
    "host",
}


@pytest.fixture(scope="module")
def dataset() -> SyntheticDataset:
    return generate_synthetic(
        SyntheticConfig(
            seed=42,
            n_events=1000,
            n_users=15,
            burst_count=2,
            burst_size=30,
            atypical_hour_count=10,
            missing_ip_count=15,
            duplicate_count=20,
            out_of_order_count=12,
            new_category_count=25,
        )
    )


def _ts(event: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(event["timestamp"]))


def test_ingesting_the_dataset_matches_what_was_injected(
    dataset: SyntheticDataset, pseudonymizer: Pseudonymizer
) -> None:
    result = ingest_records(dataset.events, policy=IngestionPolicy(), pseudonymizer=pseudonymizer)
    report = result.report
    assert report.total_records == 1000
    assert report.rejected == 0
    assert report.accepted == 980
    assert [d.content_differs for d in report.duplicates] == [False] * 20
    assert len(report.out_of_order) == 12
    assert sum(1 for e in result.events if e.event_type == EventType.OTHER) == 25
    assert sum(1 for e in result.events if e.source_ip is None) == 15


def test_every_event_is_a_valid_v1_event_without_label_keys(dataset: SyntheticDataset) -> None:
    for event in dataset.events:
        assert set(event) == V1_KEYS
        EventV1.model_validate(event)


def test_labels_live_apart_and_cover_every_unique_event(dataset: SyntheticDataset) -> None:
    ids = [str(e["event_id"]) for e in dataset.events]
    unique = set(ids)
    assert len(unique) == 980
    assert [label.event_id for label in dataset.labels] == list(dict.fromkeys(ids))
    counts = Counter(label.label for label in dataset.labels)
    assert counts == {
        "normal": 895,
        "failure_burst": 60,
        "atypical_hour": 10,
        "missing_ip": 15,
    }


def test_bursts_are_failures_from_one_ip_within_five_minutes(dataset: SyntheticDataset) -> None:
    by_id = {str(e["event_id"]): e for e in dataset.events}
    groups: dict[str, list[dict[str, object]]] = {}
    for label in dataset.labels:
        if label.label == "failure_burst":
            assert label.group is not None
            groups.setdefault(label.group, []).append(by_id[label.event_id])
    assert len(groups) == 2
    for events in groups.values():
        assert len(events) == 30
        assert len({e["source_ip"] for e in events}) == 1
        assert {e["outcome"] for e in events} == {"failure"}
        stamps = [_ts(e) for e in events]
        assert (max(stamps) - min(stamps)).total_seconds() < 300


def test_atypical_hour_events_happen_between_02_and_04_utc(dataset: SyntheticDataset) -> None:
    by_id = {str(e["event_id"]): e for e in dataset.events}
    atypical = [by_id[label.event_id] for label in dataset.labels if label.label == "atypical_hour"]
    assert len(atypical) == 10
    assert all(2 <= _ts(e).hour < 4 for e in atypical)


def test_only_fictitious_data_is_generated(dataset: SyntheticDataset) -> None:
    for event in dataset.events:
        ip = event["source_ip"]
        if ip is not None:
            address = ipaddress.ip_address(str(ip))
            assert any(address in network for network in DOC_NETWORKS), ip
        assert re.fullmatch(r"user\d{3}", str(event["username"]))
        assert re.fullmatch(r"srv-demo-\d{2}", str(event["host"]))
        assert event["source"] == "linux-auth"


def test_labels_reference_existing_events_only(dataset: SyntheticDataset) -> None:
    ids = {str(e["event_id"]) for e in dataset.events}
    assert all(label.event_id in ids for label in dataset.labels)


def test_no_injection_means_only_normal_labels() -> None:
    plain = generate_synthetic(SyntheticConfig(seed=7, n_events=200))
    assert {label.label for label in plain.labels} == {"normal"}
    assert len(plain.labels) == 200
