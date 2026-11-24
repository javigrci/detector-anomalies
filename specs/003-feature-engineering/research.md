# Research: Ingeniería de características

Decisiones del incremento 3. Contexto: [spec.md](spec.md), SPEC §4.4 y §4.5, constitución (Principio III).

## R1. Esquema de características v1

- **Decisión:** 14 características en un orden fijo, descritas en [contracts/feature-schema.md](contracts/feature-schema.md):
  - **Por evento (7):** `hour_sin`, `hour_cos`, `day_of_week`, `event_type`, `action`, `outcome`, `source`.
  - **Por ventana (5):** `ip_event_count`, `ip_failure_count`, `ip_failure_rate`, `ip_distinct_users`,
    `user_distinct_ips`.
  - **Indicadores (2):** `has_ip`, `has_user` (0 o 1).
- **Esquema versionado:** `FEATURE_SCHEMA_VERSION = 1` y una huella SHA-256 sobre un JSON canónico (claves
  ordenadas, sin espacios) con la versión, la longitud de la ventana y, por característica, su nombre, su tipo y
  su texto de definición. Un test fija el par `(versión, huella)`: cualquier cambio de definición, orden o tipo lo
  rompe hasta subir la versión y actualizar ambos (FR-003-18, FR-003-21).
- **Racional:** el esquema es la única fuente de verdad del vector; el incremento 4 lo guardará junto al modelo.
- **Alternativas:** sin huella (un cambio sutil pasaría desapercibido), huella calculada del código fuente
  (frágil ante refactorizaciones sin cambio de comportamiento).

## R2. Características por evento

- **Decisión:** hora entera UTC `h` (0–23): `hour_sin = sin(2πh/24)` y `hour_cos = cos(2πh/24)`, redondeados a
  12 decimales; `day_of_week = timestamp.weekday()` en UTC (lunes = 0 … domingo = 6); `event_type`, `action`,
  `outcome` y `source` como cadenas del catálogo.
- **Racional:** solo hay 24 valores posibles de hora, de modo que el redondeo garantiza resultados idénticos
  entre plataformas (FR-003-01 a 03). El día de la semana como entero 0–6 es el valor de SPEC §4.5; su
  codificación (cíclica u otra) es del incremento 4.
- **Alternativas:** hora fraccionaria con minutos (más ruido y no pedida), día cíclico (decisión diferida al 4),
  codificar las categorías aquí (es del `ColumnTransformer` del 4).

## R3. Motor de ventana deslizante

- **Decisión:** un `FeatureEngine` que procesa eventos en orden total y mantiene solo el estado de la ventana:
  - una cola de entradas `(timestamp, source, ip, usuario, fallo)` ordenadas por llegada;
  - contadores por `(source, ip)`: eventos, fallos y un `Counter` de usuarios;
  - un `Counter` de IPs por `(source, usuario)`.
  Al llegar un evento en `t`, se **evicta** de la cabeza de la cola toda entrada con `timestamp ≤ t − 5 min`,
  decrementando los contadores y borrando las claves a cero; después se añade el evento y se leen los valores.
- **Racional:** coste amortizado O(1) por evento y memoria acotada por los eventos de la ventana, no por el
  dataset (SC-008). La ventana es `(t − 5 min, t]`: un evento a exactamente 5 minutos no cuenta
  (FR-003-07, FR-003-13).
- **Alternativas:** recalcular la ventana desde cero por evento (O(ventana) por evento), cubos fijos (descartados
  en la clarificación), `pandas.rolling` (dependencia no aprobada y semántica de borde distinta).

## R4. Orden total y causalidad

- **Decisión:** clave de orden `(timestamp en UTC, source, event_id)`. La historia de un evento es la de los
  eventos que lo preceden en esa clave más él mismo (clarificado). El motor exige entrada no decreciente en esa
  clave; el modo por defecto ordena, el modo `presorted` la verifica (R5).
- **Racional:** es la misma clave que `read_range` del incremento 2, de modo que lo leído del almacenamiento ya
  llega en el orden correcto sin reordenar. Así los empates no dependen del orden de llegada.
- **Alternativas:** incluir todos los empatados (rompería la equivalencia con inferencia), usar el orden de
  inserción (no determinista entre cargas).

## R5. Un único camino para lotes y evento individual

- **Decisión:**
  - `compute_features(events, *, history_start, presorted=False)`: por lotes. Por defecto ordena la entrada
    por la clave (memoria O(n)); con `presorted=True` procesa en streaming y verifica el orden, lanzando
    `FeatureError` si se viola.
  - `compute_event_features(event, history, *, history_start)`: un evento. Filtra de `history` los eventos
    posteriores al evento (nunca los usa), los ordena y alimenta **el mismo** `FeatureEngine`.
  - `features_for_range(engine, start, end, *, history_start)`: lee `read_range` en bloques, usa los eventos de
    `[max(start − 5 min, history_start), start)` solo para calentar el estado y emite vectores para `[start, end)`.
- **Racional:** al compartir motor, la equivalencia lote/individual se cumple por construcción y un test la
  comprueba sobre ≥ 5.000 eventos (FR-003-15 a 17, NFR-04).
- **Alternativas:** dos implementaciones (riesgo de divergencia), una función puramente funcional por evento
  (O(ventana) por evento).

## R6. Contexto completo

- **Decisión:** `context_complete = (timestamp − 5 min) ≥ history_start`, con `history_start` obligatorio, con
  zona horaria, aportado por quien llama (clarificado). Un evento anterior a `history_start` provoca
  `FeatureError("event_before_history")` (FR-003-14, FR-003-25).
- **Racional:** única regla válida igual en entrenamiento y en inferencia; no deduce nada de los datos.
- **Alternativas:** deducirlo del primer evento de la entrada (no sirve para un evento individual).

## R7. Lectura desde el almacenamiento

- **Decisión:** `features_for_range` consume `read_range` por bloques (el límite superior exclusivo evita la
  fuga) y usa el calentamiento de R5. No se ofrece una función «un evento desde el almacenamiento»: el
  llamador aporta la historia (FR-003-16); la derivará el incremento 5 con `read_range`.
- **Racional:** mantiene el incremento acotado y probado; el puente de BD es una capa fina con su test de
  integración.
- **Alternativas:** una función de evento individual desde la BD (es de la API del incremento 5).

## R8. Valores ausentes y privacidad

- **Decisión:** sin IP, `ip_*` = 0, `has_ip` = 0; sin usuario, `user_distinct_ips` = 0, `has_user` = 0 (y
  `ip_distinct_users` sigue contando los usuarios con IP). El vector contiene el identificador `(source,
  event_id)` y `timestamp` **fuera** de `features`; `features` solo lleva agregados, indicadores y categorías del
  catálogo. El estado interno (IPs y seudónimos) vive en memoria y nunca se registra ni se devuelve.
- **Racional:** forma fija del vector, sin descartar eventos y sin exponer identificadores (FR-003-22, 23;
  SPEC §5.1).
- **Alternativas:** `NaN` (Isolation Forest de scikit-learn no los admite sin imputar), descartar eventos.

## R9. Errores y registro

- **Decisión:** `FeatureError` con un código estable (`invalid_history_start`, `event_before_history`,
  `unsorted_input`, `duplicate_event`) y un mensaje fijo, sin valores. Un registro `features_computed` por
  llamada con recuentos (eventos, contexto incompleto), duración y versión del esquema (FR-003-24, 25).
- **Racional:** mismo patrón que `StorageError` y las excepciones de la ingesta.
- **Alternativas:** `ValueError` genéricos (mensajes con valores).

## R10. Determinismo

- **Decisión:** sin aleatoriedad; los resultados solo dependen de recuentos (independientes del orden de
  iteración de `Counter` y `dict`); el redondeo de seno/coseno a 12 decimales; el orden de las claves de
  `features` es el del esquema.
- **Racional:** FR-003-20 y SC-003.

## R11. Pruebas

- **Unitarias (sin servicios):** valores de cada característica; borde exacto de la ventana (`t − 5 min`
  excluido, `t − 5 min + 1 µs` incluido); empates; zonas horarias; **fuga por mutación del futuro** (añadir,
  quitar y modificar eventos posteriores con muchos flujos de semillas fijas); equivalencia lote/individual
  (≥ 5.000 eventos); entradas barajadas; determinismo; esquema y huella fijados; ausentes; centinelas de
  privacidad; ráfaga de 30 fallos (SC-004) con el generador sintético; memoria con `tracemalloc`; rendimiento.
- **Integración (PostgreSQL real, marcador `integration`):** `features_for_range` sobre eventos guardados con el
  incremento 2 da los mismos vectores que el cálculo en memoria y no lee nada en `end` o después.
- **CI:** los jobs existentes bastan; no hay servicios nuevos.
- **Sin `hypothesis`:** generadores propios con `random.Random(semilla)` (dependencia no aprobada).

## R12. Dependencias

- **Decisión:** ninguna. `numpy`/`pandas` no son necesarios para estos cálculos y no están aprobados; el
  incremento 4 introducirá `scikit-learn` (y con él `numpy`) con su ADR.
- **Racional:** AGENTS.md regla 3 y SPEC §2.
