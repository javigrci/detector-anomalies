"""FR-003-19, 20 y SC-003: mismas entradas y esquema, mismos vectores en cualquier ejecución."""

import hashlib
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from security_anomaly.features.pipeline import compute_features
from security_anomaly.features.schema import FEATURE_SCHEMA
from tests.feature_factory import BASE, random_stream

ROOT = Path(__file__).resolve().parents[3]
HISTORY_START = BASE - timedelta(hours=1)

_SCRIPT = """
import hashlib, sys
from datetime import timedelta
sys.path.insert(0, ".")
from security_anomaly.features.pipeline import compute_features
from tests.feature_factory import BASE, random_stream
events = random_stream(17, 1500, span_seconds=900, sources=("linux-auth", "win-sec"))
digest = hashlib.sha256()
for vector in compute_features(events, history_start=BASE - timedelta(hours=1)):
    digest.update(vector.model_dump_json().encode())
print(digest.hexdigest())
"""


def test_two_runs_with_the_same_inputs_are_identical() -> None:
    events = random_stream(17, 1500, span_seconds=900)
    first = list(compute_features(events, history_start=HISTORY_START))
    second = list(compute_features(events, history_start=HISTORY_START))
    assert first == second
    assert [v.model_dump_json() for v in first] == [v.model_dump_json() for v in second]


def test_the_result_does_not_depend_on_the_hash_seed() -> None:
    digests = set()
    for seed in ("0", "1", "4242", "random"):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _SCRIPT],
            cwd=ROOT,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        digests.add(result.stdout.strip())
    assert len(digests) == 1


def test_every_vector_carries_the_schema_version_and_follows_its_order() -> None:
    events = random_stream(2, 200, span_seconds=300)
    for vector in compute_features(events, history_start=HISTORY_START):
        assert vector.schema_version == FEATURE_SCHEMA.version
        assert tuple(vector.features) == FEATURE_SCHEMA.names


def test_the_digest_of_a_fixed_input_is_reproducible_in_process() -> None:
    def digest() -> str:
        h = hashlib.sha256()
        for v in compute_features(
            random_stream(5, 300, span_seconds=200), history_start=HISTORY_START
        ):
            h.update(v.model_dump_json().encode())
        return h.hexdigest()

    assert digest() == digest()
