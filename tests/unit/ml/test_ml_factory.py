"""La ayuda de test genera datasets reproducibles con ráfagas etiquetadas."""

from tests.ml_factory import synthetic_vectors


def test_synthetic_vectors_are_reproducible_and_ordered() -> None:
    a, b = synthetic_vectors(3, 600), synthetic_vectors(3, 600)
    assert [v.event_id for v in a.vectors] == [v.event_id for v in b.vectors]
    assert a.vectors == b.vectors
    stamps = [(v.timestamp, v.source, v.event_id) for v in a.vectors]
    assert stamps == sorted(stamps)


def test_labels_cover_the_bursts_and_only_use_the_generator_labels() -> None:
    data = synthetic_vectors(4, 900, burst_count=3, burst_size=30)
    assert sum(1 for label in data.labels.values() if label == "failure_burst") == 90
    assert {v.event_id for v in data.vectors} <= set(data.labels)


def test_a_different_seed_gives_a_different_dataset() -> None:
    assert synthetic_vectors(1, 400).vectors != synthetic_vectors(2, 400).vectors
