"""SC-004 y SPEC §2: una ráfaga de fallos desde una IP en 5 minutos se refleja en las agregadas."""

import secrets

from security_anomaly.ingestion import (
    IngestionPolicy,
    Pseudonymizer,
    SyntheticConfig,
    generate_synthetic,
    ingest_records,
)
from tests.feature_factory import run_engine


def test_a_thirty_failure_burst_stands_out_from_the_background() -> None:
    dataset = generate_synthetic(
        SyntheticConfig(seed=11, n_events=1500, burst_count=1, burst_size=30)
    )
    result = ingest_records(
        dataset.events, policy=IngestionPolicy(), pseudonymizer=Pseudonymizer(secrets.token_hex(32))
    )
    windows = run_engine(result.events)
    burst_ids = {label.event_id for label in dataset.labels if label.label == "failure_burst"}
    assert len(burst_ids) == 30
    burst = [
        e
        for e in sorted(result.events, key=lambda e: (e.timestamp, e.source, e.event_id))
        if e.event_id in burst_ids
    ]
    last = windows[(burst[-1].source, burst[-1].event_id)]
    assert (last.ip_failure_count, last.ip_failure_rate, last.ip_event_count) == (30, 1.0, 30)
    counts = [
        w.ip_failure_count for (_, event_id), w in windows.items() if event_id not in burst_ids
    ]
    assert max(counts) <= 3
    # La ráfaga crece evento a evento.
    seen = [windows[(e.source, e.event_id)].ip_failure_count for e in burst]
    assert seen == sorted(seen) and seen[-1] > seen[0]
