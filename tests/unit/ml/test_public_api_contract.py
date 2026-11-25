"""contracts/ml-api.md: la API pública se importa de `security_anomaly.ml`."""

import inspect

import security_anomaly.ml as ml


def _params(function: object) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(function).parameters)  # type: ignore[arg-type]


def test_dataset_and_split_signatures() -> None:
    assert list(_params(ml.build_dataset))[:3] == ["engine", "start", "end"]
    assert _params(ml.build_dataset)["history_start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert list(_params(ml.dataset_fingerprint)) == ["dataset"]
    assert list(_params(ml.split_temporal)) == ["dataset", "policy"]


def test_training_and_scoring_signatures() -> None:
    assert list(_params(ml.train_model)) == ["partition", "policy"]
    assert list(_params(ml.score_vectors)) == ["model", "vectors"]
    assert list(_params(ml.score_vector)) == ["model", "vector"]
    evaluate = _params(ml.evaluate)
    assert list(evaluate)[:2] == ["model", "partition"]
    assert (
        evaluate["labels"].kind is inspect.Parameter.KEYWORD_ONLY
        and evaluate["labels"].default is None
    )


def test_run_training_signature() -> None:
    params = _params(ml.run_training)
    assert list(params)[:4] == ["engine", "settings", "start", "end"]
    for name, default in (("policy", None), ("labels", None)):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[name].default == default
    assert params["history_start"].default is inspect.Parameter.empty


def test_registry_and_loading_signatures() -> None:
    activate = _params(ml.activate_version)
    assert list(activate)[:3] == ["engine", "settings", "version"]
    assert activate["approved"].kind is inspect.Parameter.KEYWORD_ONLY
    assert activate["approved"].default is inspect.Parameter.empty  # no hay aprobación por defecto
    assert list(_params(ml.get_active_version)) == ["engine"]
    assert list(_params(ml.get_training_run)) == ["engine", "run_id"]
    assert list(_params(ml.list_versions)) == ["engine"]
    assert list(_params(ml.load_model)) == ["engine", "settings", "version"]
    assert list(_params(ml.load_active_model)) == ["engine", "settings"]


def test_public_names_are_exported() -> None:
    for name in (
        "build_dataset",
        "dataset_fingerprint",
        "split_temporal",
        "train_model",
        "score_vectors",
        "score_vector",
        "evaluate",
        "run_training",
        "activate_version",
        "get_active_version",
        "get_training_run",
        "list_versions",
        "load_model",
        "load_active_model",
        "MlError",
        "MlPolicy",
        "MlSettings",
        "TrainedModel",
        "Score",
        "TrainingResult",
    ):
        assert name in ml.__all__, name
        assert hasattr(ml, name)
