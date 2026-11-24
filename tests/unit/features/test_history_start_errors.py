"""FR-003-25: entradas inválidas producen errores controlados sin valores de los datos."""

from datetime import timedelta

import pytest

from security_anomaly.features.errors import FeatureError
from security_anomaly.features.pipeline import compute_event_features, compute_features
from tests.feature_factory import BASE, make_event

from datetime import datetime  # isort: skip

NAIVE = datetime(2026, 1, 5, 7, 0)
START = BASE - timedelta(hours=1)


def test_a_naive_history_start_is_rejected_by_compute_features() -> None:
    with pytest.raises(FeatureError) as caught:
        compute_features([make_event(0)], history_start=NAIVE)
    assert caught.value.code == "invalid_history_start"


def test_a_naive_history_start_is_rejected_in_streaming_mode_too() -> None:
    with pytest.raises(FeatureError) as caught:
        compute_features([make_event(0)], history_start=NAIVE, presorted=True)
    assert caught.value.code == "invalid_history_start"


def test_a_naive_history_start_is_rejected_for_a_single_event() -> None:
    with pytest.raises(FeatureError) as caught:
        compute_event_features(make_event(0), [], history_start=NAIVE)
    assert caught.value.code == "invalid_history_start"


def test_an_event_before_the_declared_history_is_rejected_in_both_modes() -> None:
    early = make_event(0, event_id="SENTINEL-ID-early", timestamp=BASE - timedelta(minutes=10))
    ok = make_event(1, event_id="ok", timestamp=BASE)
    for presorted in (False, True):
        with pytest.raises(FeatureError) as caught:
            list(compute_features([early, ok], history_start=BASE, presorted=presorted))
        assert caught.value.code == "event_before_history"
        assert "SENTINEL" not in f"{caught.value!s} {caught.value!r}"


def test_an_event_before_the_declared_history_is_rejected_for_a_single_event() -> None:
    early = make_event(0, event_id="early", timestamp=BASE - timedelta(minutes=10))
    with pytest.raises(FeatureError) as caught:
        compute_event_features(early, [], history_start=BASE)
    assert caught.value.code == "event_before_history"


def test_an_event_exactly_at_history_start_is_valid() -> None:
    vector = compute_event_features(make_event(0, timestamp=BASE), [], history_start=BASE)
    assert vector.context_complete is False
