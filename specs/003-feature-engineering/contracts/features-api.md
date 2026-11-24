# Contrato: API pública de las características

La consumen el incremento 4 (entrenamiento) y el 5 (inferencia). Todo se importa de
`security_anomaly.features`. Son funciones puras salvo `features_for_range`, que lee de PostgreSQL con el rol
`anomaly_app`.

## Funciones

```python
FEATURE_SCHEMA: FeatureSchema          # esquema v1 (versión, ventana, definiciones, huella)

compute_features(events: Iterable[EventLike], *, history_start: datetime,
                 presorted: bool = False) -> Iterator[FeatureVector]
```
Cálculo por lotes. Sin `presorted`, ordena la entrada por la clave `(timestamp, source, event_id)` (memoria
O(n)). Con `presorted=True`, procesa en streaming y lanza `FeatureError("unsorted_input")` si la entrada no
está ordenada (memoria acotada por la ventana). Devuelve un vector por evento, en orden total.

```python
compute_event_features(event: EventLike, history: Iterable[EventLike], *,
                       history_start: datetime) -> FeatureVector
```
Un evento con su historia. Solo usa los elementos de `history` que preceden a `event` en el orden total y caen
en la ventana; ignora el resto (nunca usa nada posterior). Mismo resultado que el cálculo por lotes.

```python
features_for_range(engine: Engine, start: datetime, end: datetime, *,
                   history_start: datetime, chunk_size: int = 5000) -> Iterator[FeatureVector]
```
Lee `read_range` por bloques de `chunk_size`: calienta con `[max(start − 5 min, history_start), start)` y
devuelve vectores de `[start, end)`. Nunca lee ni usa eventos con `timestamp ≥ end` ni anteriores a
`history_start` (no están en la historia declarada, así que aquí no provocan error).

## Garantías

- **Sin fuga de futuro:** el vector de un evento no cambia aunque se añadan, quiten o modifiquen eventos
  posteriores a él en el orden total.
- **Mismo pipeline:** lotes, evento individual y rango usan el mismo motor y dan el mismo vector.
- **Determinismo:** mismas entradas y esquema → mismos vectores, en cualquier orden de entrada o ejecución.
- **Privacidad:** `features` no contiene IP, usuario, host ni `event_id`; errores y logs sin valores.
- **Contexto:** `context_complete = (timestamp − 5 min) ≥ history_start`.

## Excepciones

| Excepción | Cuándo | Atributos |
|---|---|---|
| `FeatureError` | `history_start` sin zona horaria; evento anterior a `history_start`; entrada no ordenada con `presorted`; evento duplicado | `code` ∈ `invalid_history_start`, `event_before_history`, `unsorted_input`, `duplicate_event` |
| `StorageError` | falla la lectura en `features_for_range` | heredado del incremento 2 |
| `ValueError` | `start >= end` o argumentos sin zona horaria en `features_for_range` | mensaje sin valores |

## Correspondencia con SPEC (para los incrementos 4 y 5)

- Entrenamiento: `features_for_range` o `compute_features(..., presorted=True)` sobre el conjunto ordenado.
- Inferencia (`POST /api/v1/score`): `compute_event_features` con la historia de 5 minutos leída con
  `read_range`; `context_complete` va a la respuesta.
- El esquema y su huella se guardan con el modelo (Principio III).
