# Data Model: Ingesta y normalización de logs

Sin persistencia en este incremento: son modelos en memoria (Pydantic v2, inmutables).

## EventV1 (entrada)

Esquema de SPEC §4.1. `extra="forbid"`: un campo desconocido se rechaza (`unknown_field`).

| Campo | Tipo de entrada | Obligatorio | Regla |
|---|---|---|---|
| `event_id` | string | Sí | 1–256 caracteres, sin caracteres de control |
| `timestamp` | string ISO 8601 | Sí | con zona horaria; se convierte a UTC; rango 2000-01-01 ≤ t < 2100-01-01 (configurable) |
| `source` | string | Sí | tras minúsculas, `^[a-z0-9][a-z0-9-]{0,63}$` |
| `event_type` | string | Sí | catálogo; fuera de él → `other` |
| `action` | string | Sí | catálogo; fuera de él → `other` |
| `outcome` | string | Sí | `success`, `failure` o `unknown` (tras minúsculas); otro valor → rechazo |
| `username` | string \| null | No | se seudonimiza; vacío → `None` |
| `source_ip` | string \| null | No | IPv4/IPv6 válida, sin `%`; se normaliza a forma comprimida |
| `host` | string \| null | No | minúsculas, ≤ 256 caracteres |

Todos los textos: espacios en los extremos eliminados, NFC, sin caracteres de control, ≤ 256 caracteres.

## Catálogo canónico (versión 1)

| Campo | Valores |
|---|---|
| `event_type` | `authentication`, `privilege_escalation`, `other` |
| `action` | `login`, `invalid_user`, `sudo`, `other` |
| `outcome` | `success`, `failure`, `unknown` |

Cota de cardinalidad: valores distintos ≤ tamaño del catálogo (SC-008). Cambiar el catálogo exige
subir `catalog_version`.

## NormalizedEvent (salida)

| Campo | Tipo | Notas |
|---|---|---|
| `event_id` | str | tal cual (JSON/CSV) o derivado con HMAC (adaptador) |
| `timestamp` | datetime (UTC) | siempre con `tzinfo=UTC` |
| `source` | str | slug |
| `event_type` | str | del catálogo |
| `action` | str | del catálogo |
| `outcome` | str | `success`/`failure`/`unknown` |
| `user_pseudonym` | str \| None | `usr_` + 32 hex; `None` si no había usuario |
| `source_ip` | str \| None | forma comprimida |
| `host` | str \| None | minúsculas |
| `out_of_order` | bool | R9 |
| `position` | int | posición 1-based en el lote |

Nunca contiene el nombre de usuario original.

## Rejection

| Campo | Notas |
|---|---|
| `position` | 1-based; se repite si el mismo registro tiene errores en varios campos (máximo 5) |
| `code` | `RejectionCode` (ver research R3) |
| `field` | nombre del campo afectado; para un campo desconocido, solo si es un identificador seguro (`^[A-Za-z0-9_.-]{1,64}$`), si no el marcador `<invalid-name>`; `None` si no aplica (p. ej. fila CSV mal formada) |

Sin valores de entrada.

## IngestionReport

| Campo | Notas |
|---|---|
| `catalog_version` | 1 |
| `total_records` | registros leídos (excluye líneas ignoradas del adaptador) |
| `accepted` | número de eventos válidos y únicos |
| `rejected` | número de **registros** rechazados (posiciones distintas) |
| `rejections` | lista de `Rejection` en orden de posición; un registro rechazado puede tener hasta 5 entradas (una por campo con error) |
| `duplicates` | lista de `{position, content_differs: bool}` |
| `out_of_order` | posiciones marcadas |
| `ignored_lines` | solo adaptador; líneas no reconocidas o demasiado largas |
| `by_code` | recuento por código de rechazo |

Invariante: `total_records == accepted + rejected + len(duplicates)`; `rejected == número de posiciones distintas en rejections`.

## IngestionResult

`events: tuple[NormalizedEvent, ...]` en orden de lectura + `report: IngestionReport`. Serialización
canónica (`to_canonical_json()`): claves ordenadas, sin espacios, UTF-8.

## IngestionPolicy

| Campo | Por defecto |
|---|---|
| `max_file_bytes` | 10 485 760 |
| `max_events_per_batch` | 10 000 |
| `max_events_per_dataset` | 100 000 |
| `max_field_length` | 256 |
| `timestamp_min` | 2000-01-01T00:00:00Z |
| `timestamp_max` | 2100-01-01T00:00:00Z |

## Pseudonymizer

`key: SecretStr | None` (≥ 32 caracteres y sin el marcador `change-me`; si no, `ConfigError`).
`pseudonym(username)` → `usr_…`; `derive_id(domain, *parts)` → hex HMAC con separación de dominio.
Sin clave y con usuario: `PseudonymKeyMissing`.

## Sintéticos

| Modelo | Campos |
|---|---|
| `SyntheticConfig` | `seed`, `n_events` (≤ 100 000), `n_users`, `n_hosts`, `start` (UTC), `burst_count`, `burst_size`, `atypical_hour_count`, `missing_ip_count`, `duplicate_count`, `out_of_order_count`, `new_category_count` |
| `SyntheticLabel` | `event_id`, `label` (`normal`, `failure_burst`, `atypical_hour`, `missing_ip`), `group` (identificador de la ráfaga o `None`) |
| `SyntheticDataset` | `events: list[dict]` (esquema v1), `labels: tuple[SyntheticLabel, ...]` |

Las etiquetas **nunca** se mezclan con los eventos (Principio III).
