"""Orden total de eventos y motor de la ventana deslizante (research R3, R4).

La historia de un evento son los eventos que lo preceden en la clave
``(timestamp UTC, source, event_id)`` más él mismo, dentro de ``(t - 5 min, t]``.
"""

import ipaddress
import math
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Protocol

from security_anomaly.features.errors import FeatureError
from security_anomaly.features.schema import WINDOW
from security_anomaly.schemas.event import Action, EventType, Outcome


class EventLike(Protocol):
    """Lo que el cálculo necesita de un evento (``NormalizedEvent`` y ``StoredEvent``)."""

    @property
    def source(self) -> str: ...
    @property
    def event_id(self) -> str: ...
    @property
    def timestamp(self) -> datetime: ...
    @property
    def event_type(self) -> EventType: ...
    @property
    def action(self) -> Action: ...
    @property
    def outcome(self) -> Outcome: ...
    @property
    def user_pseudonym(self) -> str | None: ...
    @property
    def source_ip(self) -> str | None: ...
    @property
    def host(self) -> str | None: ...


OrderKey = tuple[datetime, str, str]


def event_order_key(event: EventLike) -> OrderKey:
    """Clave del orden total (FR-003-12): instante UTC y, en empate, ``source`` y ``event_id``."""
    return (event.timestamp.astimezone(UTC), event.source, event.event_id)


@dataclass(frozen=True, slots=True)
class WindowFeatures:
    """Las cinco agregadas por ventana de un evento (contracts/feature-schema.md)."""

    ip_event_count: int
    ip_failure_count: int
    ip_failure_rate: float
    ip_distinct_users: int
    user_distinct_ips: int


@lru_cache(maxsize=65536)
def _canonical_ip(value: str) -> str:
    """Forma comprimida de una IP (las formas equivalentes cuentan como la misma)."""
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return value


@dataclass(frozen=True, slots=True)
class _Entry:
    instant: datetime
    ip_key: tuple[str, str] | None
    user_key: tuple[str, str] | None
    ip: str | None
    user: str | None
    failure: bool


def _decrement[K](counts: dict[K, int], key: K) -> None:
    left = counts[key] - 1
    if left:
        counts[key] = left
    else:
        del counts[key]


class FeatureEngine:
    """Ventana deslizante `(t - 5 min, t]` sobre eventos en orden total (research R3).

    Procesa los eventos en orden no decreciente de ``event_order_key``; el estado solo contiene los
    eventos de la ventana (evicción amortizada O(1)), de modo que la memoria no crece con el
    tamaño del dataset. El evento puntuado cuenta como parte de su propia ventana.
    """

    def __init__(self, window: timedelta = WINDOW) -> None:
        self._window = window
        self._queue: deque[_Entry] = deque()
        self._last: OrderKey | None = None
        self._ip_events: dict[tuple[str, str], int] = {}
        self._ip_failures: dict[tuple[str, str], int] = {}
        self._ip_users: dict[tuple[str, str], dict[str, int]] = {}
        self._user_ips: dict[tuple[str, str], dict[str, int]] = {}

    @property
    def state_size(self) -> int:
        """Eventos que contiene ahora la ventana."""
        return len(self._queue)

    def observe(self, event: EventLike) -> WindowFeatures:
        """Añade el evento a la ventana y devuelve sus agregadas."""
        key = event_order_key(event)
        if self._last is not None:
            if key == self._last:
                raise FeatureError("duplicate_event")
            if key < self._last:
                raise FeatureError("unsorted_input")
        self._last = key
        instant = key[0]
        self._evict(instant - self._window)

        ip = None if event.source_ip is None else _canonical_ip(event.source_ip)
        user = event.user_pseudonym
        ip_key = None if ip is None else (event.source, ip)
        user_key = None if user is None else (event.source, user)
        failure = event.outcome == Outcome.FAILURE
        self._add(_Entry(instant, ip_key, user_key, ip, user, failure))

        if ip_key is None:
            ip_events = ip_failures = ip_users = 0
            rate = 0.0
        else:
            ip_events = self._ip_events[ip_key]
            ip_failures = self._ip_failures.get(ip_key, 0)
            ip_users = len(self._ip_users.get(ip_key, ()))
            rate = ip_failures / ip_events
        user_ips = 0 if user_key is None else len(self._user_ips.get(user_key, ()))
        return WindowFeatures(ip_events, ip_failures, rate, ip_users, user_ips)

    def _add(self, entry: _Entry) -> None:
        self._queue.append(entry)
        if entry.ip_key is not None:
            self._ip_events[entry.ip_key] = self._ip_events.get(entry.ip_key, 0) + 1
            if entry.failure:
                self._ip_failures[entry.ip_key] = self._ip_failures.get(entry.ip_key, 0) + 1
            if entry.user is not None:
                users = self._ip_users.setdefault(entry.ip_key, {})
                users[entry.user] = users.get(entry.user, 0) + 1
        if entry.user_key is not None and entry.ip is not None:
            ips = self._user_ips.setdefault(entry.user_key, {})
            ips[entry.ip] = ips.get(entry.ip, 0) + 1

    def _evict(self, lower: datetime) -> None:
        """Quita de la ventana los eventos con ``instante <= lower`` (el borde es exclusivo)."""
        queue = self._queue
        while queue and queue[0].instant <= lower:
            entry = queue.popleft()
            if entry.ip_key is not None:
                _decrement(self._ip_events, entry.ip_key)
                if entry.failure:
                    _decrement(self._ip_failures, entry.ip_key)
                if entry.user is not None:
                    users = self._ip_users[entry.ip_key]
                    _decrement(users, entry.user)
                    if not users:
                        del self._ip_users[entry.ip_key]
            if entry.user_key is not None and entry.ip is not None:
                ips = self._user_ips[entry.user_key]
                _decrement(ips, entry.ip)
                if not ips:
                    del self._user_ips[entry.user_key]


def event_level_features(event: EventLike) -> dict[str, float | int | str]:
    """Características que dependen solo del propio evento (FR-003-01 a 03).

    Hora entera y día de la semana siempre en UTC. Seno y coseno se redondean a 12 decimales: solo
    hay 24 valores posibles, así que el resultado es idéntico entre plataformas. Las categorías se
    entregan tal como están en el catálogo; su codificación es del incremento 4.
    """
    instant = event.timestamp.astimezone(UTC)
    angle = 2 * math.pi * instant.hour / 24
    return {
        "hour_sin": round(math.sin(angle), 12),
        "hour_cos": round(math.cos(angle), 12),
        "day_of_week": instant.weekday(),
        "event_type": event.event_type.value,
        "action": event.action.value,
        "outcome": event.outcome.value,
        "source": event.source,
    }
