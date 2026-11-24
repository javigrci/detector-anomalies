# Data Model: Ingeniería de características

Modelos en memoria (Pydantic v2, inmutables) en `schemas/features.py`. No hay tablas nuevas: las
características no se persisten en este incremento.

## FeatureDefinition

| Campo | Tipo | Regla |
|---|---|---|
| `name` | `str` | identificador único dentro del esquema |
| `kind` | `"float" \| "int" \| "category"` | tipo del valor |
| `scope` | `"event" \| "window" \| "indicator"` | de dónde sale |
| `definition` | `str` | texto que fija el significado; forma parte de la huella |

## FeatureSchema

| Campo | Tipo | Regla |
|---|---|---|
| `version` | `int` | ≥ 1; sube con cualquier cambio de definición, orden o tipo |
| `window_seconds` | `int` | 300 en la v1; forma parte de la huella |
| `definitions` | `tuple[FeatureDefinition, ...]` | orden = posición en el vector |
| `names` (propiedad) | `tuple[str, ...]` | nombres en orden |
| `fingerprint` (propiedad) | `str` | SHA-256 hexadecimal del JSON canónico (claves ordenadas) |

## FeatureVector

| Campo | Tipo | Regla |
|---|---|---|
| `source`, `event_id` | `str` | identifican el evento; **no** son características |
| `timestamp` | `datetime` | UTC |
| `schema_version` | `int` | versión con la que se calculó |
| `context_complete` | `bool` | ventana completa dentro de la historia declarada |
| `features` | `dict[str, float \| int \| str]` | exactamente los nombres del esquema y en su orden |

`features` nunca contiene IP, usuario, seudónimo, host ni `event_id`.

## Estado interno del motor (no público)

| Elemento | Contenido | Ciclo de vida |
|---|---|---|
| Cola de la ventana | `(timestamp, source, ip, usuario, fallo)` en orden | se evicta lo `≤ t − 5 min` |
| Contadores por `(source, ip)` | eventos, fallos, `Counter` de usuarios | claves a cero se borran |
| Contadores por `(source, usuario)` | `Counter` de IPs | claves a cero se borran |

La memoria es proporcional a los eventos de la ventana, no al tamaño del dataset.

## Entrada

Cualquier objeto con los atributos `source`, `event_id`, `timestamp`, `event_type`, `action`, `outcome`,
`user_pseudonym`, `source_ip` y `host` (los `NormalizedEvent` del incremento 1 y los `StoredEvent` del 2).

## Orden total

`(timestamp en UTC, source, event_id)` ascendente. La historia de un evento son los eventos que lo preceden en
esa clave más él mismo, dentro de la ventana `(t − 5 min, t]`.

## FeatureError

`code ∈ {invalid_history_start, event_before_history, unsorted_input, duplicate_event}` y un mensaje fijo. Sin
valores de los datos.
