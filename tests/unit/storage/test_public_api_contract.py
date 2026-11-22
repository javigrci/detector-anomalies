"""contracts/storage-api.md: la API pública se importa de `security_anomaly.storage`."""

import inspect

import security_anomaly.storage as storage


def _params(function: object) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(function).parameters)  # type: ignore[arg-type]


def test_save_events_signature() -> None:
    params = _params(storage.save_events)
    assert list(params)[:2] == ["engine", "events"]
    assert params["batch_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["batch_id"].default is None


def test_public_names_are_exported() -> None:
    for name in (
        "save_events",
        "query_events",
        "StorageError",
        "EventFilter",
        "SaveSummary",
        "StoragePolicy",
    ):
        assert name in storage.__all__, name
        assert hasattr(storage, name)


def test_query_events_signature() -> None:
    params = _params(storage.query_events)
    assert list(params)[:2] == ["engine", "filters"]
    for name in ("limit", "offset", "policy"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["limit"].default is None
    assert params["offset"].default == 0
    assert params["filters"].default is None


def test_read_range_signature() -> None:
    params = _params(storage.read_range)
    assert list(params)[:3] == ["engine", "start", "end"]
    assert params["chunk_size"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["chunk_size"].default == 5000


def test_purge_events_signature() -> None:
    params = _params(storage.purge_events)
    assert list(params)[:1] == ["engine"]
    for name, default in (
        ("retention_days", None),
        ("dry_run", False),
        ("now", None),
        ("policy", None),
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[name].default == default


def test_provision_roles_signature() -> None:
    assert list(_params(storage.provision_roles)) == ["admin_engine", "passwords"]
