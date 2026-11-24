"""Cálculo de características: por lotes, de un evento individual y por rango (research R5, R7).

Los tres caminos usan el mismo ``FeatureEngine``, de modo que entrenamiento e inferencia no pueden
divergir (NFR-04, Principio III). Todo valor del vector sale de agregados, indicadores y categorías:
nunca de la IP, el usuario, el host ni el identificador del evento.
"""

import logging
import time
from collections.abc import Iterable, Iterator
from datetime import datetime

from sqlalchemy import Engine

from security_anomaly.features.engine import (
    EventLike,
    FeatureEngine,
    WindowFeatures,
    event_level_features,
    event_order_key,
)
from security_anomaly.features.errors import FeatureError
from security_anomaly.features.schema import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION, WINDOW
from security_anomaly.schemas.features import FeatureValue, FeatureVector
from security_anomaly.storage import read_range

logger = logging.getLogger(__name__)


def _log_computed(events: int, incomplete: int, seconds: float) -> None:
    """Solo recuentos, duración y versión del esquema (FR-003-24)."""
    logger.info(
        "features_computed",
        extra={
            "fields": {
                "events": events,
                "incomplete_context": incomplete,
                "duration_ms": round(seconds * 1000),
                "schema_version": FEATURE_SCHEMA_VERSION,
            }
        },
    )


def _require_history_start(history_start: datetime) -> None:
    if history_start.tzinfo is None or history_start.utcoffset() is None:
        raise FeatureError("invalid_history_start")


def _context_complete(event: EventLike, history_start: datetime) -> bool:
    """Completo si la ventana entera queda dentro de la historia declarada (FR-003-14)."""
    if event.timestamp < history_start:
        raise FeatureError("event_before_history")
    return event.timestamp - WINDOW >= history_start


def _vector(event: EventLike, window: WindowFeatures, context_complete: bool) -> FeatureVector:
    values: dict[str, FeatureValue] = {
        **event_level_features(event),
        "ip_event_count": window.ip_event_count,
        "ip_failure_count": window.ip_failure_count,
        "ip_failure_rate": window.ip_failure_rate,
        "ip_distinct_users": window.ip_distinct_users,
        "user_distinct_ips": window.user_distinct_ips,
        "has_ip": 0 if event.source_ip is None else 1,
        "has_user": 0 if event.user_pseudonym is None else 1,
    }
    return FeatureVector(
        source=event.source,
        event_id=event.event_id,
        timestamp=event.timestamp,
        schema_version=FEATURE_SCHEMA_VERSION,
        context_complete=context_complete,
        features={name: values[name] for name in FEATURE_SCHEMA.names},
    )


def _stream(
    events: Iterable[EventLike],
    history_start: datetime,
    emit_from: datetime | None = None,
) -> Iterator[FeatureVector]:
    """Motor sobre eventos ya ordenados; ``emit_from`` deja los anteriores como calentamiento."""
    started = time.perf_counter()
    engine = FeatureEngine()
    emitted = incomplete = 0
    try:
        for event in events:
            complete = _context_complete(event, history_start)
            window = engine.observe(event)
            if emit_from is not None and event.timestamp < emit_from:
                continue
            vector = _vector(event, window, complete)
            emitted += 1
            incomplete += 0 if vector.context_complete else 1
            yield vector
    finally:
        _log_computed(emitted, incomplete, time.perf_counter() - started)


def compute_features(
    events: Iterable[EventLike],
    *,
    history_start: datetime,
    presorted: bool = False,
) -> Iterator[FeatureVector]:
    """Un vector por evento, en orden total ``(timestamp, source, event_id)``.

    Por defecto ordena la entrada (memoria O(n)) y rechaza eventos repetidos. Con ``presorted=True``
    procesa en streaming (memoria acotada por la ventana) y verifica que la entrada esté ordenada.
    """
    _require_history_start(history_start)
    if presorted:
        return _stream(events, history_start)
    ordered = sorted(events, key=event_order_key)
    identities = {(e.source, e.event_id) for e in ordered}
    if len(identities) != len(ordered):
        raise FeatureError("duplicate_event")
    return _stream(ordered, history_start)


def compute_event_features(
    event: EventLike,
    history: Iterable[EventLike],
    *,
    history_start: datetime,
) -> FeatureVector:
    """Vector de un evento con su historia previa; ignora lo que no lo precede ni cae en ventana."""
    started = time.perf_counter()
    _require_history_start(history_start)
    complete = _context_complete(event, history_start)
    key = event_order_key(event)
    lower = key[0] - WINDOW
    relevant = sorted(
        (e for e in history if lower < event_order_key(e)[0] and event_order_key(e) < key),
        key=event_order_key,
    )
    engine = FeatureEngine()
    for earlier in relevant:
        engine.observe(earlier)
    vector = _vector(event, engine.observe(event), complete)
    _log_computed(1, 0 if vector.context_complete else 1, time.perf_counter() - started)
    return vector


def features_for_range(
    engine: Engine,
    start: datetime,
    end: datetime,
    *,
    history_start: datetime,
    chunk_size: int = 5000,
) -> Iterator[FeatureVector]:
    """Vectores de los eventos guardados en ``[start, end)``, leídos por bloques.

    Calienta el estado con ``[max(start - 5 min, history_start), start)`` y nunca lee ni usa eventos
    con ``timestamp >= end``.
    """
    _require_history_start(history_start)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start y end deben tener zona horaria")
    if start >= end:
        raise ValueError("start debe ser anterior a end")
    warm_start = max(start - WINDOW, history_start)
    if warm_start >= end:
        return iter(())
    chunks = read_range(engine, warm_start, end, chunk_size=chunk_size)
    flattened = (event for chunk in chunks for event in chunk)
    return _stream(flattened, history_start, emit_from=start)
