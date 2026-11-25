"""FR-004-11, 12: puntuación bruta y percentil frente a la distribución de calibración."""

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

from security_anomaly.ml.errors import MlError
from security_anomaly.ml.scoring import percentile, raw_scores

CAL = np.array([1.0, 2.0, 2.0, 3.0, 5.0])


def test_the_percentile_is_the_fraction_of_calibration_scores_not_above() -> None:
    assert percentile(CAL, 3.0) == 4 / 5
    assert percentile(CAL, 1.0) == 1 / 5
    assert percentile(CAL, 2.0) == 3 / 5  # los repetidos cuentan todos
    assert percentile(CAL, 4.0) == 4 / 5


def test_below_the_whole_calibration_is_zero_and_above_it_is_one() -> None:
    assert percentile(CAL, 0.5) == 0.0
    assert percentile(CAL, 5.0) == 1.0
    assert percentile(CAL, 99.0) == 1.0


def test_it_is_monotone_and_stays_in_the_unit_interval() -> None:
    values = np.linspace(-1, 7, 200)
    scores = percentile(CAL, values)
    assert np.all(np.diff(scores) >= 0)
    assert scores.min() >= 0.0 and scores.max() <= 1.0


def test_a_calibration_with_all_scores_equal() -> None:
    flat = np.array([2.0, 2.0, 2.0, 2.0])
    assert percentile(flat, 1.9) == 0.0
    assert percentile(flat, 2.0) == 1.0
    assert percentile(flat, 2.1) == 1.0


def test_empty_input_gives_an_empty_result() -> None:
    assert percentile(CAL, np.array([])).shape == (0,)


def test_an_empty_calibration_is_a_controlled_error() -> None:
    with pytest.raises(MlError) as caught:
        percentile(np.array([]), 1.0)
    assert caught.value.code == "invalid_parameters"


def test_the_raw_score_is_the_negative_of_score_samples_and_higher_means_more_anomalous() -> None:
    rng = np.random.default_rng(0)
    inliers = rng.normal(0, 1, size=(300, 3))
    forest = IsolationForest(random_state=42, n_jobs=1).fit(inliers)
    probe = np.vstack([np.zeros((1, 3)), np.full((1, 3), 12.0)])
    raw = raw_scores(forest, probe)
    assert np.array_equal(raw, -forest.score_samples(probe))
    assert raw[1] > raw[0]  # lo lejano puntúa más alto
