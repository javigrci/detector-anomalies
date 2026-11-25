"""Ayudas de test del entrenamiento: datasets sintéticos con vectores, etiquetas y resúmenes.

Solo datos sintéticos del generador del incremento 1. La clave de seudonimización es una constante
de prueba (no un secreto) para que los resultados sean idénticos entre procesos.
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from security_anomaly.features import compute_features
from security_anomaly.ingestion import (
    IngestionPolicy,
    Pseudonymizer,
    SyntheticConfig,
    generate_synthetic,
    ingest_records,
)
from security_anomaly.schemas.event import NormalizedEvent
from security_anomaly.schemas.features import FeatureVector

TEST_KEY = "ml-test-key-" + "x" * 40


@dataclass(frozen=True)
class SyntheticVectors:
    events: list[NormalizedEvent]
    vectors: list[FeatureVector]
    labels: Mapping[str, str]  # event_id -> etiqueta del generador (solo para evaluar)


def synthetic_vectors(
    seed: int = 1,
    n_events: int = 3000,
    *,
    burst_count: int = 6,
    burst_size: int = 30,
    n_users: int = 20,
) -> SyntheticVectors:
    """Dataset sintético reproducible con ráfagas de fallos inyectadas y sus etiquetas."""
    dataset = generate_synthetic(
        SyntheticConfig(
            seed=seed,
            n_events=n_events,
            burst_count=burst_count,
            burst_size=burst_size,
            n_users=n_users,
        )
    )
    policy = IngestionPolicy(max_events_per_batch=max(10_000, n_events))
    result = ingest_records(dataset.events, policy=policy, pseudonymizer=Pseudonymizer(TEST_KEY))
    events = list(result.events)
    start = min(e.timestamp for e in events) - timedelta(hours=1)
    vectors = list(compute_features(events, history_start=start))
    labels = {label.event_id: label.label for label in dataset.labels}
    return SyntheticVectors(events, vectors, dict(labels))


def _digest(*chunks: bytes) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def transformer_digest(model: Any) -> str:
    """Resumen de las transformaciones ajustadas (categorías aprendidas por bloque)."""
    encoder = model.transformer.named_transformers_["categorical"]
    parts = [repr([list(map(str, cats)) for cats in encoder.categories_]).encode()]
    return _digest(*parts)


def forest_digest(model: Any) -> str:
    """Resumen de la estructura de todos los árboles del bosque."""
    parts: list[bytes] = [
        repr(model.forest.get_params()).encode(),
        repr(model.forest.offset_).encode(),
    ]
    for tree in model.forest.estimators_:
        t = tree.tree_
        parts.extend(
            [
                t.feature.tobytes(),
                t.threshold.tobytes(),
                t.children_left.tobytes(),
                t.children_right.tobytes(),
            ]
        )
    return _digest(*parts)


def calibration_digest(model: Any) -> str:
    return _digest(model.calibration.tobytes())


def model_digest(model: Any) -> str:
    return _digest(
        transformer_digest(model).encode(),
        forest_digest(model).encode(),
        calibration_digest(model).encode(),
    )


def fake_vector(index: int, timestamp: datetime, **overrides: Any) -> FeatureVector:
    """Vector sintético mínimo con el esquema v1 y valores neutros (para probar la partición)."""
    from security_anomaly.features.schema import FEATURE_SCHEMA

    defaults: dict[str, Any] = {}
    for definition in FEATURE_SCHEMA.definitions:
        defaults[definition.name] = (
            0.0 if definition.kind == "float" else 0 if definition.kind == "int" else "other"
        )
    defaults["source"] = "linux-auth"
    defaults.update(overrides)
    return FeatureVector(
        source="linux-auth",
        event_id=f"fake-{index:06d}",
        timestamp=timestamp,
        schema_version=FEATURE_SCHEMA.version,
        context_complete=True,
        features=defaults,
    )


def tweak(vector: FeatureVector, **changes: Any) -> FeatureVector:
    """Copia validada del vector con algunas características cambiadas."""
    return FeatureVector(
        source=vector.source,
        event_id=vector.event_id,
        timestamp=vector.timestamp,
        schema_version=vector.schema_version,
        context_complete=vector.context_complete,
        features={**vector.features, **changes},
    )
