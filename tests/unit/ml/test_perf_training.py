"""SC-004, SC-005: 100.000 eventos en menos de 5 minutos; puntuar un evento en menos de 50 ms."""

import os
import platform
import statistics
import time

from security_anomaly.ml.dataset import make_dataset, split_temporal
from security_anomaly.ml.evaluation import evaluate
from security_anomaly.ml.pipeline import score_vector, train_model
from security_anomaly.schemas.ml import MlPolicy
from tests.ml_factory import synthetic_vectors

VOLUME = 100_000
TRAIN_THRESHOLD_S = 300.0  # umbral de SC-004
SINGLE_P95_THRESHOLD_S = 0.050  # umbral de SC-005


def _environment() -> str:
    return (
        f"cpus={os.cpu_count()} os={platform.platform()} python={platform.python_version()} "
        "| máquina de desarrollo (WSL2), sin otras cargas controladas"
    )


def test_training_and_evaluation_of_one_hundred_thousand_events_and_single_scoring() -> None:
    data = synthetic_vectors(11, VOLUME, burst_count=60, burst_size=30, n_users=200)
    started = time.perf_counter()
    partition = split_temporal(make_dataset(data.vectors), MlPolicy())
    model = train_model(partition, MlPolicy())
    report = evaluate(model, partition, labels=data.labels)
    elapsed = time.perf_counter() - started
    print(
        f"\n[SC-004] {VOLUME} eventos (entrenar + calibrar + evaluar): {elapsed:.2f} s "
        f"(umbral {TRAIN_THRESHOLD_S:.0f} s) | {_environment()}"
    )
    assert report.n_test > 0 and elapsed < TRAIN_THRESHOLD_S

    sample = partition.test[:300]
    timings = []
    for vector in sample:
        t0 = time.perf_counter()
        score_vector(model, vector)
        timings.append(time.perf_counter() - t0)
    p95 = statistics.quantiles(timings, n=100)[94]
    print(
        f"[SC-005] puntuar un evento: p95 {p95 * 1000:.2f} ms, máx {max(timings) * 1000:.2f} ms "
        f"(umbral {SINGLE_P95_THRESHOLD_S * 1000:.0f} ms) | {_environment()}"
    )
    assert p95 < SINGLE_P95_THRESHOLD_S
