"""contracts/features-api.md: la API pública se importa de `security_anomaly.features`."""

import inspect

import security_anomaly.features as features


def _params(function: object) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(function).parameters)  # type: ignore[arg-type]


def test_compute_features_signature() -> None:
    params = _params(features.compute_features)
    assert list(params)[:1] == ["events"]
    assert params["history_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["history_start"].default is inspect.Parameter.empty
    assert params["presorted"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["presorted"].default is False


def test_compute_event_features_signature() -> None:
    params = _params(features.compute_event_features)
    assert list(params)[:2] == ["event", "history"]
    assert params["history_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["history_start"].default is inspect.Parameter.empty


def test_features_for_range_signature() -> None:
    params = _params(features.features_for_range)
    assert list(params)[:3] == ["engine", "start", "end"]
    assert params["history_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["history_start"].default is inspect.Parameter.empty
    assert params["chunk_size"].default == 5000


def test_public_names_are_exported() -> None:
    for name in (
        "FEATURE_SCHEMA",
        "FEATURE_SCHEMA_VERSION",
        "FeatureError",
        "FeatureSchema",
        "FeatureVector",
        "EventLike",
        "compute_features",
        "compute_event_features",
        "features_for_range",
    ):
        assert name in features.__all__, name
        assert hasattr(features, name)
