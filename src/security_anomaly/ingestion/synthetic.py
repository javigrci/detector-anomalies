"""Generador de eventos sintéticos estilo Linux auth, reproducible (FR-001-26…29, SPEC §15).

- Determinista: ``random.Random(seed)`` y solo ``random()`` más aritmética propia (sin ``choice`` ni
  ``shuffle``, cuyas implementaciones pueden cambiar entre versiones de Python).
- Solo datos ficticios: IPs de los rangos de documentación (RFC 5737 y RFC 3849), usuarios
  ``userNNN`` y hosts ``srv-demo-NN``.
- Las etiquetas de anomalías **nunca** se mezclan con los eventos (Principio III): van aparte.

Los datos sintéticos validan el comportamiento del software, no demuestran capacidad real de
detección (SPEC §14).
"""

import random
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from security_anomaly.ingestion.policy import IngestionPolicy

Label = Literal["normal", "failure_burst", "atypical_hour", "missing_ip"]

_DAY = 86_400
_BURST_WINDOW = 300
_FAILURE_RATE = 0.03
_EVENTS_PER_DAY = 150


class SyntheticConfig(BaseModel):
    """Configuración del generador. ``n_events`` es el total de eventos devueltos."""

    model_config = ConfigDict(frozen=True)

    seed: int
    n_events: int = Field(gt=0)
    n_users: int = Field(default=20, ge=1, le=1000)
    n_hosts: int = Field(default=3, ge=1, le=99)
    start: datetime = datetime(2026, 1, 5, tzinfo=UTC)
    burst_count: int = Field(default=0, ge=0)
    burst_size: int = Field(default=40, ge=1)
    atypical_hour_count: int = Field(default=0, ge=0)
    missing_ip_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    out_of_order_count: int = Field(default=0, ge=0)
    new_category_count: int = Field(default=0, ge=0)

    @field_validator("start")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("se requiere zona horaria")
        return value.astimezone(UTC)


class SyntheticLabel(BaseModel):
    """Etiqueta de un evento: normal o tipo de anomalía inyectada (``group`` agrupa una ráfaga)."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    label: Label
    group: str | None = None


class SyntheticDataset(BaseModel):
    """Eventos en el esquema v1 (sin etiquetas) y etiquetas aparte, una por evento único."""

    model_config = ConfigDict(frozen=True)

    events: list[dict[str, Any]]
    labels: tuple[SyntheticLabel, ...]


class _Draft:
    """Evento en construcción: segundos desde ``start``, datos v1 y etiqueta."""

    __slots__ = ("data", "group", "label", "seconds")

    def __init__(
        self, seconds: int, data: dict[str, Any], label: Label, group: str | None = None
    ) -> None:
        self.seconds = seconds
        self.data = data
        self.label = label
        self.group = group


def _below(rng: random.Random, n: int) -> int:
    """Entero en ``[0, n)`` usando solo ``random()``."""
    return min(int(rng.random() * n), n - 1)


def _sample(rng: random.Random, population: list[int], k: int) -> list[int]:
    """``k`` elementos distintos de ``population`` (Fisher-Yates parcial), en su orden original."""
    pool = list(population)
    for i in range(k):
        j = i + _below(rng, len(pool) - i)
        pool[i], pool[j] = pool[j], pool[i]
    return sorted(pool[:k])


def _user_ips(index: int) -> list[str]:
    ips = [f"192.0.2.{10 + (index * 7) % 200}", f"198.51.100.{10 + (index * 11) % 200}"]
    if index % 5 == 0:
        ips.append(f"2001:db8::{index + 1:x}")
    return ips[: 1 + index % len(ips)]


def _stamp(start: datetime, seconds: int) -> str:
    return (start + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_synthetic(
    config: SyntheticConfig, *, policy: IngestionPolicy | None = None
) -> SyntheticDataset:
    """Genera un dataset sintético reproducible; ``ValueError`` si la configuración no es válida."""
    limits = policy or IngestionPolicy()
    if config.n_events > limits.max_events_per_dataset:
        raise ValueError(
            f"n_events supera el máximo del dataset ({limits.max_events_per_dataset} eventos)"
        )
    burst_events = config.burst_count * config.burst_size
    injected = (
        burst_events + config.atypical_hour_count + config.missing_ip_count + config.duplicate_count
    )
    normal_total = config.n_events - injected
    if normal_total < 1:
        raise ValueError(
            "configuración incoherente: las anomalías inyectadas no dejan eventos normales"
        )
    if config.out_of_order_count > normal_total - 1:
        raise ValueError("configuración incoherente: demasiados eventos fuera de orden")
    if config.new_category_count > normal_total:
        raise ValueError("configuración incoherente: demasiadas categorías nuevas")

    rng = random.Random(config.seed)  # noqa: S311 - datos de prueba reproducibles, no criptografía
    first_monday = config.start.date()
    first_monday += timedelta(days=(7 - first_monday.weekday()) % 7)
    origin = datetime(first_monday.year, first_monday.month, first_monday.day, tzinfo=UTC)
    days = max(1, normal_total // _EVENTS_PER_DAY)

    def day_seconds(day: int) -> int:
        weeks, weekday = divmod(day, 5)
        return (weeks * 7 + weekday) * _DAY

    users = [f"user{n:03d}" for n in range(1, config.n_users + 1)]
    ips = [_user_ips(i) for i in range(config.n_users)]

    def base(user: int, seconds: int, outcome: str, ip: str | None, host: int) -> dict[str, Any]:
        return {
            "event_id": "",
            "timestamp": _stamp(origin, seconds),
            "source": "linux-auth",
            "event_type": "authentication",
            "action": "login",
            "outcome": outcome,
            "username": users[user],
            "source_ip": ip,
            "host": f"srv-demo-{host + 1:02d}",
        }

    drafts: list[_Draft] = []

    def working_hours(day: int) -> int:
        return day_seconds(day) + 8 * 3600 + _below(rng, 10 * 3600)

    for _ in range(normal_total):
        user = _below(rng, config.n_users)
        outcome = "failure" if rng.random() < _FAILURE_RATE else "success"
        ip = ips[user][_below(rng, len(ips[user]))]
        seconds = working_hours(_below(rng, days))
        drafts.append(
            _Draft(seconds, base(user, seconds, outcome, ip, _below(rng, config.n_hosts)), "normal")
        )

    for _ in range(config.atypical_hour_count):
        user = _below(rng, config.n_users)
        seconds = day_seconds(_below(rng, days)) + 2 * 3600 + _below(rng, 2 * 3600)
        drafts.append(
            _Draft(
                seconds,
                base(user, seconds, "success", ips[user][0], _below(rng, config.n_hosts)),
                "atypical_hour",
            )
        )

    for _ in range(config.missing_ip_count):
        user = _below(rng, config.n_users)
        seconds = working_hours(_below(rng, days))
        drafts.append(
            _Draft(
                seconds,
                base(user, seconds, "success", None, _below(rng, config.n_hosts)),
                "missing_ip",
            )
        )

    for burst in range(config.burst_count):
        attacker = f"203.0.113.{1 + burst % 250}"
        host = _below(rng, config.n_hosts)
        targets = [_below(rng, config.n_users) for _ in range(3)]
        start = day_seconds(_below(rng, days)) + _below(rng, _DAY - _BURST_WINDOW)
        for _ in range(config.burst_size):
            seconds = start + _below(rng, _BURST_WINDOW)
            user = targets[_below(rng, len(targets))]
            drafts.append(
                _Draft(
                    seconds,
                    base(user, seconds, "failure", attacker, host),
                    "failure_burst",
                    f"burst-{burst + 1}",
                )
            )

    # Orden estable por instante y, a igualdad, por orden de creación.
    drafts = [d for _, d in sorted(enumerate(drafts), key=lambda pair: (pair[1].seconds, pair[0]))]
    for number, draft in enumerate(drafts, start=1):
        draft.data["event_id"] = f"syn-{number:06d}"

    normal_positions = [i for i, d in enumerate(drafts) if d.label == "normal"]

    # Fuera de orden: un evento normal (no el primero) recibe un instante anterior al máximo visto.
    late = set(_sample(rng, [i for i in normal_positions if i >= 1], config.out_of_order_count))
    latest = drafts[0].seconds if drafts else 0
    for index, draft in enumerate(drafts):
        if index in late:
            draft.data["timestamp"] = _stamp(origin, latest - 1)
        else:
            latest = max(latest, draft.seconds)

    # Categorías nuevas: tipo y acción fuera del catálogo (la normalización las agrupa en "other").
    for count, index in enumerate(
        _sample(rng, normal_positions, config.new_category_count), start=1
    ):
        drafts[index].data["event_type"] = f"new_type_{count % 7}"
        drafts[index].data["action"] = f"new_action_{count % 5}"

    events = [draft.data for draft in drafts]
    labels = tuple(
        SyntheticLabel(event_id=d.data["event_id"], label=d.label, group=d.group) for d in drafts
    )

    # Duplicados: copias exactas de eventos existentes, al final del flujo.
    for index in _sample(rng, list(range(len(drafts))), config.duplicate_count):
        events.append(dict(events[index]))

    return SyntheticDataset(events=events, labels=labels)
