---

description: "Tareas del incremento 3 — Ingeniería de características"
---

# Tasks: Ingeniería de características

**Input**: Documentos de diseño en `/specs/003-feature-engineering/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (`features-api.md`, `feature-schema.md`), quickstart.md

**Tests**: OBLIGATORIOS (Constitución, Principio V). Cada historia y cada módulo compartido empiezan por sus tareas de test; se escriben y se confirma que FALLAN antes de implementar. Los resultados se registran tal como salen. Los tests de fuga de futuro son la puerta de aceptación del roadmap.

**Organization**: Tareas agrupadas por historia de usuario en el orden de entrega del plan: Cimientos → US1 → US2 → US3 → US4 → US5 → US6 → Cierre. Los módulos `engine.py` (US1 y US2) y `pipeline.py` (US3 y US4) crecen a lo largo de varias historias, así que esas tareas de implementación son secuenciales entre sí aunque las historias sean funcionalmente independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1…US6)
- Cada tarea cita requisitos (FR-003-xx) y rutas exactas

## Notas de ejecución

- Se trabaja en `main`; los commits y pushes (T050 y T051) requieren autorización explícita (Principio VII).
- **Sin dependencias nuevas** (plan, Technical Context): solo biblioteca estándar y Pydantic. Sin `hypothesis`: las pruebas de fuga usan generadores propios con `random.Random(semilla)`. Si surge la necesidad de otra, parar y pedir aprobación (ADR).
- **Sin componentes no pedidos:** ni endpoints, ni variables de entorno, ni CLI, ni persistencia de características.
- Los datos de los tests son ficticios: IPs de rangos de documentación (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), usuarios `user001…`, hosts `srv-demo-NN`. Los seudónimos de las pruebas se generan al vuelo; nunca un valor real.
- Los fixtures de fugas llevan **cadenas centinela** (`SENTINEL-USER-…`, `SENTINEL-HOST-…`, `SENTINEL-ID-…`) para comprobar que no aparecen en vectores, esquemas, errores ni registros.
- `tests/feature_factory.py` incluye una **implementación de referencia lenta** (O(n²), escrita directamente de las definiciones de `contracts/feature-schema.md`) que sirve de oráculo para comprobar el motor; no se usa en el código de producción.
- Comandos de verificación por tarea: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`, y `uv run pytest -q -m "not integration"` o `-m integration` (PostgreSQL temporal de `docs/handoff.md` §8; `DATABASE_URL` es el administrador).

---

## Phase 1: Setup (infraestructura compartida)

**Purpose**: estructura de directorios de test.

- [X] T001 Crear `tests/unit/features/__init__.py`, `tests/integration/features/__init__.py` y `tests/integration/features/conftest.py` (fixture automática que vacía `events` con el rol migrador entre tests, como la de `tests/integration/storage/conftest.py`); comprobar que Ruff y mypy siguen en verde

---

## Phase 2: Foundational (prerrequisitos bloqueantes)

**Purpose**: errores, modelos, esquema v1, clave de orden total y ayudas de test que necesitan todas las historias.

**⚠️ CRITICAL**: ninguna historia puede empezar hasta terminar esta fase.

- [X] T002 [P] Test en `tests/unit/features/test_errors.py` (primero): `FeatureError` con `code ∈ {invalid_history_start, event_before_history, unsorted_input, duplicate_event}`, mensaje fijo por código, sin valores (centinelas) ni sentencias; `repr` y `args` sin datos; confirmar que falla (FR-003-25)
- [X] T003 [P] Test en `tests/unit/schemas/test_features_models.py` (primero): `FeatureDefinition` (kind y scope válidos), `FeatureSchema` (nombres únicos, `names` en orden, `fingerprint` determinista, hexadecimal de 64 caracteres, sensible al orden, al tipo, a la definición, a la versión y a `window_seconds`), `FeatureVector` inmutable (incluido `features`, expuesto como mapeo de solo lectura), `timestamp` en UTC, `features` con exactamente los nombres del esquema y en su orden; confirmar que falla (FR-003-18, FR-003-19)
- [X] T004 [P] Test en `tests/unit/features/test_order_key.py` (primero): `event_order_key(evento)` devuelve `(timestamp en UTC, source, event_id)`; dos eventos con el mismo instante en zonas horarias distintas empatan en el instante; el desempate por `source` y `event_id` es el de la cadena; sirve igual para `NormalizedEvent` y `StoredEvent`; confirmar que falla (FR-003-12)
- [X] T005 [P] Test en `tests/unit/features/test_schema_contract.py` (primero): `FEATURE_SCHEMA` tiene versión 1, ventana de 300 s y exactamente las 14 características de `contracts/feature-schema.md` en ese orden, con sus tipos (`float`, `int`, `category`) y ámbitos (`event`, `window`, `indicator`); ninguna se llama como un identificador (`ip`, `user`, `host`, `event_id`); confirmar que falla (FR-003-18, FR-003-23)
- [X] T006 Crear `tests/feature_factory.py`: constructores de eventos ficticios (`NormalizedEvent` y `StoredEvent`), un generador `random_stream(seed, n, …)` con muchos empates de `timestamp`, IPs v4 y v6, varios usuarios, fuentes y hosts, eventos sin IP o sin usuario y zonas horarias distintas, y la **implementación de referencia lenta** `reference_features(eventos, índice, history_start)` escrita directamente de las definiciones del contrato; con tests mínimos de la propia referencia en `tests/unit/features/test_reference_oracle.py` (valores de un caso pequeño calculado a mano) (research R11)
- [X] T007 [P] Implementar `src/security_anomaly/features/errors.py` (`FeatureError`); T002 pasa (T002)
- [X] T008 [P] Implementar `src/security_anomaly/schemas/features.py` (`FeatureDefinition`, `FeatureSchema`, `FeatureVector`) con la huella SHA-256 del JSON canónico; T003 pasa (T003)
- [X] T009 Implementar `src/security_anomaly/features/schema.py` (`FEATURE_SCHEMA_VERSION`, `WINDOW`, `FEATURE_SCHEMA` con las 14 definiciones y sus textos); T005 pasa (T005, T008)
- [X] T010 Implementar `event_order_key` y el protocolo `EventLike` (atributos `source`, `event_id`, `timestamp`, `event_type`, `action`, `outcome`, `user_pseudonym`, `source_ip`, `host`, común a `NormalizedEvent` y `StoredEvent`) en `src/security_anomaly/features/engine.py`; T004 pasa (T004)
- [X] T011 [P] Escribir `docs/decisions/0004-semantica-ventana-y-orden-causal.md` (español, estado Aceptada): orden total `(timestamp, source, event_id)` como lectura más estricta que «menor o igual» de SPEC §4.4 y por qué (equivalencia con la inferencia), ventana deslizante `(t − 5 min, t]` frente a cubos fijos, agregación por `(source, IP)` y `(source, usuario)` sumando hosts, contexto declarado por quien llama, ausentes a 0 con indicadores; alternativas descartadas y consecuencias (Constitución VI; FR-003-11, 12, 14, 22)

**Checkpoint**: errores, modelos, esquema v1, clave de orden y ayudas de test listos; las historias pueden empezar.

---

## Phase 3: User Story 1 - Resumir la actividad reciente de cada IP y usuario sin ver el futuro (Priority: P1) 🎯 MVP

**Goal**: ventana deslizante de 5 minutos con eventos, fallos, tasa de fallos y usuarios distintos por IP e IPs distintas por usuario, sin fuga de futuro.

**Independent Test**: un flujo con una ráfaga de fallos: los valores suben a lo largo de la ráfaga y no cambian si se tocan eventos posteriores.

### Tests for User Story 1 (MANDATORY) ⚠️

> Escribirlos primero y confirmar que FALLAN antes de implementar.

- [X] T012 [P] [US1] Test en `tests/unit/features/test_window_counts.py`: `ip_event_count`, `ip_failure_count`, `ip_failure_rate` (con el propio evento contado y tasa 0 sin eventos), `ip_distinct_users` (un seudónimo repetido cuenta una vez, nulos no cuentan) y `user_distinct_ips`; las agregadas son por `(source, IP)` y `(source, usuario)`: la misma IP en dos fuentes cuenta por separado y distintos `host` de la misma fuente se suman; IPv6 abreviada y completa cuentan como la misma IP; solo `failure` cuenta como fallo (FR-003-04…06, 08…10)
- [X] T013 [P] [US1] Test en `tests/unit/features/test_window_boundary.py`: un evento a exactamente `t − 5 min` no cuenta; a `t − 5 min + 1 µs` sí; uno a `t − 5 min − 1 µs` no; ventana vacía salvo el propio evento; huecos de más de 5 minutos no arrastran actividad anterior (FR-003-07)
- [X] T014 [P] [US1] Test en `tests/unit/features/test_ties_order.py`: dos eventos de la misma IP con el mismo `timestamp`: el que va después en `(timestamp, source, event_id)` cuenta al otro en su historia y el que va antes no cuenta al posterior; el resultado es el mismo en cualquier ejecución y con la entrada en cualquier orden; empates con IPs, fuentes y usuarios distintos (clarificación 1; FR-003-12)
- [X] T015 [P] [US1] Test en `tests/unit/features/test_no_future_leak.py` (**puerta de aceptación del roadmap**): con ≥ 50 semillas fijas y flujos con muchos empates, para cada evento elegido se añaden, quitan y modifican eventos posteriores a él en el orden total y se comprueba que su vector y los de todos los anteriores no cambian (SC-001); un caso dirigido con una ráfaga; la mutación incluye cambiar IP, usuario, resultado y `timestamp` de los posteriores (FR-003-11)
- [X] T016 [P] [US1] Test en `tests/unit/features/test_window_vs_reference.py`: el motor da los mismos valores que la implementación de referencia de T006 en ≥ 30 flujos generados con semillas fijas, incluidos empates, IPv6, usuarios nulos y huecos (FR-003-04, 05, 07)
- [X] T017 [P] [US1] Test en `tests/unit/features/test_burst_synthetic.py`: con `generate_synthetic` (semilla fija, `burst_count` ≥ 1 y una ráfaga de 30 fallos) ingerido con `ingest_records`, el último evento de la ráfaga tiene `ip_failure_count` = 30 y `ip_failure_rate` = 1, y el tráfico de fondo tiene a lo sumo 3 fallos por IP y una tasa menor (SC-004; SPEC §2)

### Implementation for User Story 1

- [X] T018 [US1] Implementar `FeatureEngine` en `src/security_anomaly/features/engine.py`: cola de la ventana, contadores por `(source, ip)` y por `(source, usuario)`, evicción de lo `≤ t − 5 min` con borrado de claves a cero, comparación de IPs por valor, y un método que devuelve las cinco agregadas de un evento; exige orden no decreciente en la clave de orden total; T012–T017 pasan (T012–T017, T010, T006)

**Checkpoint**: US1 funcional y comprobable de forma independiente.

---

## Phase 4: User Story 2 - Describir cada evento por sí mismo (Priority: P1)

**Goal**: hora cíclica, día de la semana y categorías, siempre en UTC y solo a partir del propio evento.

**Independent Test**: eventos con horas, días y categorías conocidas comparados con los valores esperados.

### Tests for User Story 2 (MANDATORY) ⚠️

- [X] T019 [P] [US2] Test en `tests/unit/features/test_event_features.py`: `hour_sin` y `hour_cos` de las 00:00, 06:00, 12:00 y 18:00; las 23:59 y las 00:01 casi idénticas y las 12:00 opuestas a las 00:00; redondeo a 12 decimales; un `timestamp` en otra zona horaria (por ejemplo UTC+02:00 y UTC−05:00) da la hora y el día en UTC, también cuando cambia de día o de año; `day_of_week` lunes = 0 … domingo = 6; tipo, acción, resultado y fuente se conservan como cadenas del catálogo; una fuente no vista se conserva sin error; las características por evento no dependen de ningún otro evento (mismo evento con historias distintas, mismos valores) (FR-003-01…03)

### Implementation for User Story 2

- [X] T020 [US2] Implementar la función de características por evento en `src/security_anomaly/features/engine.py` (hora entera UTC, seno y coseno redondeados, día de la semana, categorías); T019 pasa (T019, T018)

**Checkpoint**: US1 y US2 funcionan de forma independiente.

---

## Phase 5: User Story 3 - Calcular las características igual en entrenamiento y en inferencia (Priority: P1)

**Goal**: un único cálculo para un conjunto de eventos, un evento individual con su historia y un rango leído del almacenamiento por bloques.

**Independent Test**: calcular un conjunto por lotes y evento a evento con su historia, y comparar.

### Tests for User Story 3 (MANDATORY) ⚠️

- [X] T021 [P] [US3] Test en `tests/unit/features/test_batch_vs_individual.py`: sobre ≥ 5.000 eventos generados con semilla fija, `compute_features` y `compute_event_features` (con la historia de cada evento) dan vectores idénticos en el 100 % de los eventos; incluye empates, IPs v4 y v6, y eventos sin IP o sin usuario (SC-002; FR-003-15)
- [X] T022 [P] [US3] Test en `tests/unit/features/test_input_order.py`: la misma colección en varios órdenes barajados (semillas fijas) da los mismos vectores por evento con `compute_features` por defecto, y los devuelve en orden total (SC-003; FR-003-12)
- [X] T023 [P] [US3] Test en `tests/unit/features/test_presorted_streaming.py`: con `presorted=True` se consume la entrada de forma perezosa (un generador que cuenta lo consumido no se agota antes de obtener el primer vector) y da los mismos vectores que el modo por defecto; una entrada no ordenada lanza `FeatureError("unsorted_input")` y un evento repetido `FeatureError("duplicate_event")`, sin valores en el mensaje; una entrada vacía devuelve cero vectores (FR-003-16, 25)
- [X] T024 [P] [US3] Test en `tests/unit/features/test_compute_event_features.py`: ignora los elementos de la historia posteriores al evento en el orden total (añadir eventos futuros no cambia el vector); ignora los más antiguos que la ventana; no necesita ningún dato posterior; una historia vacía da un vector válido; no modifica la historia recibida (FR-003-17)
- [X] T025 [P] [US3] Test en `tests/unit/features/test_features_logging.py`: el registro `features_computed` contiene solo recuentos (eventos, contexto incompleto), duración y versión del esquema; con centinelas de IP, seudónimo, host e identificador en los eventos, ninguno aparece en el registro (FR-003-24)
- [X] T026 [P] [US3] Test de integración en `tests/integration/features/test_features_for_range.py`: con eventos guardados con `save_events` y bloques pequeños, `features_for_range` da los mismos vectores que `compute_features` en memoria; calienta con los eventos de `[start − 5 min, start)` y solo emite los de `[start, end)`; no lee ni usa eventos con `timestamp ≥ end` (un evento exactamente en `end` y otros posteriores no cambian ningún vector); `start >= end` o argumentos sin zona horaria lanzan `ValueError` antes de consultar; la memoria no carga todo el rango (FR-003-16)
- [X] T027 [P] [US3] Test en `tests/unit/features/test_public_api_contract.py`: las firmas de `compute_features`, `compute_event_features` y `features_for_range` y los nombres exportados por `security_anomaly.features` (`FEATURE_SCHEMA`, `FeatureError`, `FeatureVector`, …) coinciden con `contracts/features-api.md`

### Implementation for User Story 3

- [X] T028 [US3] Implementar `compute_features` en `src/security_anomaly/features/pipeline.py`: modo por defecto (ordena por la clave) y `presorted` (streaming con verificación de orden y duplicados), ensamblado de `FeatureVector` con las características en el orden del esquema; T021–T023 pasan (T021–T023, T018, T020, T009)
- [X] T029 [US3] Implementar `compute_event_features` en `src/security_anomaly/features/pipeline.py`: filtra la historia a los eventos que preceden al evento, los ordena y alimenta el mismo `FeatureEngine`; T024 pasa (T024, T028)
- [X] T030 [US3] Implementar `features_for_range` en `src/security_anomaly/features/pipeline.py`: lectura con `read_range` por bloques, calentamiento con `[max(start − 5 min, history_start), start)` y vectores solo de `[start, end)`; validación previa de argumentos; T026 pasa (T026, T028)
- [X] T031 [US3] Añadir el registro `features_computed` (recuentos, duración, versión del esquema) y exportar la API en `src/security_anomaly/features/__init__.py`; T025 y T027 pasan (T025, T027, T028–T030)

**Checkpoint**: US1 a US3 funcionan; entrenamiento e inferencia comparten el motor.

---

## Phase 6: User Story 4 - Tratar los eventos fuera de orden y avisar cuando falta contexto (Priority: P2)

**Goal**: los eventos tardíos se puntúan con lo conocido hasta su instante y el vector indica si la ventana está respaldada por historia.

**Independent Test**: calcular un evento tardío y uno al inicio del rango y comprobar sus valores y su indicador de contexto.

### Tests for User Story 4 (MANDATORY) ⚠️

- [X] T032 [P] [US4] Test en `tests/unit/features/test_out_of_order.py`: un evento con `timestamp` anterior a otros ya conocidos se calcula solo con los conocidos de instante menor o igual al suyo en el orden total; calcularlo no modifica los vectores ya devueltos (son inmutables) ni el estado de otros cálculos; un dataset con eventos fuera de orden (`out_of_order_count` del generador sintético) da los mismos vectores sea cual sea el orden de llegada (FR-003-13; decisión D5; SPEC §4.4)
- [X] T033 [P] [US4] Test en `tests/unit/features/test_context_complete.py`: `context_complete` es verdadero si `timestamp − 5 min ≥ history_start` (incluido el borde exacto) y falso si es anterior; una ventana vacía pero cubierta por la historia es completa; el primer evento del rango con `history_start` igual a su instante es incompleto; con `history_start` suficientemente antiguo, completo; el indicador no depende de los datos de entrada (FR-003-14)
- [X] T034 [P] [US4] Test en `tests/unit/features/test_history_start_errors.py`: un `history_start` sin zona horaria lanza `FeatureError("invalid_history_start")`; un evento anterior a `history_start` lanza `FeatureError("event_before_history")` también en `compute_event_features` y `features_for_range`; los mensajes no contienen valores (centinelas) (FR-003-25)

### Implementation for User Story 4

- [X] T035 [US4] Implementar en `src/security_anomaly/features/pipeline.py` el cálculo de `context_complete`, la validación de `history_start` y de los eventos anteriores a él, en `compute_features`, `compute_event_features` y `features_for_range`; T032–T034 pasan (T032–T034, T028–T030)

**Checkpoint**: US1 a US4 funcionan.

---

## Phase 7: User Story 5 - Identificar y reproducir el esquema de características (Priority: P2)

**Goal**: esquema versionado con huella fijada y resultados reproducibles.

**Independent Test**: calcular dos veces con las mismas entradas y comparar; cambiar una definición y comprobar que la huella cambia.

### Tests for User Story 5 (MANDATORY) ⚠️

- [X] T036 [P] [US5] Test en `tests/unit/features/test_schema_golden.py`: el par `(FEATURE_SCHEMA_VERSION, FEATURE_SCHEMA.fingerprint)` coincide con el valor fijado en el propio test; el mensaje de fallo explica que un cambio de definición, orden o tipo exige subir la versión y actualizar ambos valores (FR-003-18, FR-003-21; SC-007)
- [X] T037 [P] [US5] Test en `tests/unit/features/test_schema_sensitivity.py`: construir variantes del esquema (renombrar, reordenar, cambiar el tipo, el ámbito o el texto de definición de cada una de las 14 características; cambiar la ventana; quitar y añadir una característica) y comprobar que la huella cambia en el 100 % de los casos (SC-007)
- [X] T038 [P] [US5] Test en `tests/unit/features/test_determinism.py`: dos cálculos con las mismas entradas dan vectores idénticos; el mismo cálculo en procesos con `PYTHONHASHSEED` distintos da el mismo JSON de vectores; cada vector lleva `schema_version` y sus `features` tienen exactamente los nombres y el orden del esquema (FR-003-19, 20; SC-003)

### Implementation for User Story 5

- [X] T039 [US5] Fijar en el código la versión 1 y comprobar que `FeatureVector.schema_version` se rellena desde `FEATURE_SCHEMA` en todos los caminos; si T036–T038 revelan una discrepancia (por ejemplo, una dependencia del orden de iteración), corregir el código o el contrato; T036–T038 pasan (T036–T038, T028–T030)

**Checkpoint**: US1 a US5 funcionan.

---

## Phase 8: User Story 6 - Manejar datos ausentes y no exponer identificadores (Priority: P3)

**Goal**: valores ausentes deterministas con indicadores, y vectores sin identificadores.

**Independent Test**: eventos sin IP, sin usuario y sin ambos, con valores centinela en los campos identificadores.

### Tests for User Story 6 (MANDATORY) ⚠️

- [X] T040 [P] [US6] Test en `tests/unit/features/test_missing_fields.py`: sin IP, `ip_event_count`, `ip_failure_count`, `ip_failure_rate`, `ip_distinct_users` y `has_ip` valen 0; sin usuario, `user_distinct_ips` y `has_user` valen 0; un evento con IP y sin usuario cuenta en `ip_event_count` y `ip_failure_count` pero no en `ip_distinct_users`; un evento con usuario y sin IP ve las IPs de ese usuario en la ventana; la forma del vector no cambia y ningún evento se descarta (FR-003-22)
- [X] T041 [P] [US6] Test en `tests/unit/features/test_no_identifier_leak.py`: con IP, seudónimo, host e identificador centinela, ninguno aparece en `features`, en `model_dump_json()` del vector (salvo el identificador `(source, event_id)` en su propio campo), en el esquema, en `FeatureError`, ni en los registros de actividad; `features` solo contiene valores numéricos y categorías del catálogo o la fuente (FR-003-23, 24; SC-006)

### Implementation for User Story 6

- [X] T042 [US6] Si T040 o T041 revelan una discrepancia (un valor ausente mal tratado o un identificador filtrado), corregir `engine.py` o `pipeline.py`; no se añaden características con identificadores (FR-003-22, 23) (T040, T041, T018, T028)

**Checkpoint**: las seis historias funcionan.

---

## Phase 9: Polish y cierre

**Purpose**: rendimiento y memoria, documentación, evidencia y revisión.

- [X] T043 [P] Test de rendimiento en `tests/unit/features/test_perf_features.py`: 100.000 eventos sintéticos calculados en menos de 60 s y un evento individual con su historia de 5 minutos en menos de 100 ms (p95 sobre ≥ 200 mediciones); el umbral del test es el del SC y solo se ajusta con una justificación registrada; se imprimen el tiempo real, el volumen, el hardware y las condiciones (Constitución VI) (SC-005)
- [X] T044 [P] Test de memoria en `tests/unit/features/test_memory_bounded.py`: con `tracemalloc`, procesar 100.000 eventos en `presorted=True` con la misma actividad concurrente que 10.000 usa un pico de memoria del mismo orden de magnitud (relación acotada y documentada), y el estado del motor queda vacío al final de un hueco largo (SC-008; FR-003-16)
- [X] T045 [P] Documentar en `README.md` la biblioteca de características (qué calcula, la ventana, el orden total, la ausencia de fuga, el esquema versionado y un ejemplo) y añadir a `docs/data-contract.md` la sección «Características» con la tabla del esquema v1 y las reglas del contrato; mantener la advertencia de que una anomalía no es un ataque y que los datos de prueba son sintéticos (Principio II)
- [X] T046 [P] Actualizar `docs/handoff.md` (estado del incremento 3, decisiones de la clarificación, pendientes y número de tests) y `docs/roadmap.md` si procede
- [X] T047 Ejecutar la calidad completa: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`, `uv run pytest -q -m "not integration"` y `uv run pytest -q -m integration` contra PostgreSQL temporal; registrar los resultados reales sin editarlos; si algo falla, el incremento no está cerrado (AGENTS.md reglas 6 y 8)
- [X] T048 Ejecutar el `quickstart.md` completo (escenarios 1 a 8) y escribir `specs/003-feature-engineering/verification.md` con resultados reales, tiempos y memoria medidos (SC-005, SC-008) junto con hardware, volumen y condiciones, matriz FR/SC → test, riesgos y decisiones pendientes; marcar `[X]` solo lo comprobado; comprobar con una mutación que los tests de fuga fallan si el motor mira un evento posterior (T047)
- [X] T049 Confirmar que no hay dependencias nuevas (`git diff` de `pyproject.toml` y `uv.lock` vacío), ni endpoints, ni variables de entorno nuevas, ni persistencia de características, ni secretos en el diff (FR-003-26; AGENTS.md regla 3) (T047)
- [X] T050 **Requiere autorización explícita:** commit en `main` con el mensaje de cierre en español y la línea `Co-Authored-By` fijada por el entorno (T048, T049)
- [X] T051 **Requiere autorización explícita:** `git push` y comprobar que los tres jobs de la CI quedan en verde, anotando el identificador del run en `verification.md` (T050)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sin dependencias.
- **Foundational (Fase 2)**: depende de Setup; **bloquea** todas las historias.
- **Historias (Fases 3 a 8)**: dependen de Foundational. Orden de entrega: US1 → US2 → US3 → US4 → US5 → US6.
- **Cierre (Fase 9)**: depende de las historias.

### Dependencias entre historias

- **US1**: sin dependencias de otras historias (necesita el esquema y la clave de orden de Foundational).
- **US2**: independiente de US1 en su comportamiento; comparte `engine.py`, así que su implementación va después de T018.
- **US3**: depende de US1 y US2 (ensambla ambas en el vector).
- **US4**: depende de US3 (añade el contexto a `pipeline.py`).
- **US5**: depende de que existan los vectores (US3); sus tests de esquema solo dependen de Foundational.
- **US6**: depende de US1 y US3.

### Dentro de cada historia

- Tests primero y confirmados en rojo; luego implementación, registro y API pública.
- Después de cada tarea: Ruff, mypy y los tests afectados.

### Parallel Opportunities

- T002–T005 (archivos distintos) y luego T007 y T008.
- Todos los tests de una historia marcados [P].
- Los tests de US4, US5 y US6 pueden prepararse en paralelo con la implementación de US3, salvo los archivos compartidos (`engine.py`, `pipeline.py`).
- T043 a T046 en el cierre.

## Parallel Example: User Story 1

```bash
# Tests de US1 juntos:
Task: "Test en tests/unit/features/test_window_counts.py"
Task: "Test en tests/unit/features/test_window_boundary.py"
Task: "Test en tests/unit/features/test_ties_order.py"
Task: "Test en tests/unit/features/test_no_future_leak.py"
Task: "Test en tests/unit/features/test_window_vs_reference.py"
Task: "Test en tests/unit/features/test_burst_synthetic.py"
```

## Implementation Strategy

### MVP primero (US1)

1. Fase 1 y Fase 2 (cimientos).
2. Fase 3 (US1): motor de ventana sin fuga de futuro.
3. **PARAR y validar** con el escenario 3 de `quickstart.md` (cero fugas); es la puerta de aceptación del roadmap.

### Entrega incremental

1. Cimientos → US1 → US2 → US3 (lo que necesitan los incrementos 4 y 5).
2. US4 y US5 (contexto, esquema versionado) antes de entrenar ningún modelo.
3. US6 (ausentes y privacidad) y cierre con `verification.md`.

## Cobertura de requisitos

| Requisito | Tareas |
|---|---|
| FR-003-01…03 | T019, T020 |
| FR-003-04…06, 08…10 | T012, T016, T017, T018 |
| FR-003-07 | T013, T016, T018 |
| FR-003-11, 12 | T004, T010, T014, T015, T022 |
| FR-003-13 | T032 |
| FR-003-14 | T033, T035 |
| FR-003-15…17 | T021, T022, T023, T024, T026, T028–T030 |
| FR-003-18, 19 | T003, T005, T008, T009, T038 |
| FR-003-20, 21 | T036, T037, T038 |
| FR-003-22 | T040, T042 |
| FR-003-23 | T005, T041 |
| FR-003-24 | T025, T031, T041 |
| FR-003-25 | T002, T007, T023, T034, T035 |
| FR-003-26 | T049 |
| SC-001 | T015 |
| SC-002 | T021 |
| SC-003 | T022, T038 |
| SC-004 | T017 |
| SC-005 | T043 |
| SC-006 | T041 |
| SC-007 | T036, T037 |
| SC-008 | T044 |

## Notes

- [P] = archivos distintos y sin dependencias pendientes.
- La etiqueta [Story] vincula cada tarea con su historia.
- Verificar que los tests fallan antes de implementar; si un test pasa sin código nuevo, hacer una prueba de mutación (acuerdo del handoff §7).
- Parar en cada checkpoint para validar la historia.
- Evitar: tareas vagas, conflictos en el mismo archivo y dependencias entre historias que rompan su independencia.
