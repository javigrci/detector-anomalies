"""SC-001 y SC-005: pruebas de humo de rendimiento con umbrales generosos.

El tiempo esperado es muy inferior a los umbrales. Si la CI fuera lenta se ajusta el umbral; la
medición no se elimina. Los tiempos medidos se imprimen (``pytest -s`` o el resumen de fallos).
"""

import time

from security_anomaly.ingestion import (
    IngestionPolicy,
    Pseudonymizer,
    SyntheticConfig,
    generate_synthetic,
    ingest_records,
)


def test_a_100000_event_dataset_is_generated_in_under_60_seconds() -> None:
    started = time.perf_counter()
    dataset = generate_synthetic(
        SyntheticConfig(
            seed=1,
            n_events=100_000,
            n_users=200,
            n_hosts=10,
            burst_count=20,
            burst_size=50,
            atypical_hour_count=300,
            missing_ip_count=300,
            duplicate_count=500,
            out_of_order_count=200,
            new_category_count=300,
        )
    )
    elapsed = time.perf_counter() - started
    print(f"\n[SC-005] 100.000 eventos sintéticos generados en {elapsed:.2f} s")
    assert len(dataset.events) == 100_000
    assert elapsed < 60


def test_10000_events_are_ingested_and_reported_in_under_10_seconds(
    pseudonymizer: Pseudonymizer,
) -> None:
    dataset = generate_synthetic(
        SyntheticConfig(seed=2, n_events=10_000, burst_count=3, burst_size=40, duplicate_count=50)
    )
    started = time.perf_counter()
    result = ingest_records(dataset.events, policy=IngestionPolicy(), pseudonymizer=pseudonymizer)
    elapsed = time.perf_counter() - started
    print(f"\n[SC-001] 10.000 eventos ingeridos e informados en {elapsed:.2f} s")
    assert result.report.total_records == 10_000
    assert result.report.rejected == 0
    assert elapsed < 10
