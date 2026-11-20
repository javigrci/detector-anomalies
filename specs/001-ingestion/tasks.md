---

description: "Tareas del incremento 1 — Ingesta y normalización de logs"
---

# Tasks: Ingesta y normalización de logs

**Input**: Documentos de diseño en `/specs/001-ingestion/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: OBLIGATORIOS (Constitución, Principio V). Cada historia empieza por sus tareas de test; se escriben y se confirma que FALLAN antes de implementar. Los módulos compartidos (Foundational) también tienen su test antes del código.

**Organization**: Tareas agrupadas por historia de usuario, en el orden de entrega del plan: US1 → US2 → US4 → US5 → US3 → US6. Los módulos `normalizer.py`, `readers.py` y `pipeline.py` crecen a lo largo de varias historias, así que esas tareas son secuenciales entre sí aunque las historias sean funcionalmente independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: historia a la que pertenece (US1…US6)
- Cada tarea cita requisitos (FR-001-xx) y rutas exactas

## Notas de ejecución

- Se trabaja en `main`; los commits y pushes (T068 y T069) requieren autorización explícita (Principio VII).
- **Sin dependencias nuevas** (plan, Technical Context): solo biblioteca estándar y Pydantic. Si surge la necesidad de otra, parar y pedir aprobación (ADR).
- Los tests usan una clave de seudonimización **generada al vuelo** (`secrets.token_hex(32)`) en las fixtures; nunca un valor fijo ni la clave real. Los datos de los fixtures son ficticios: IPs de rangos de documentación (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), usuarios `user001…`, hosts `srv-demo-NN`.
- Los fixtures que prueban fugas llevan **cadenas centinela** (por ejemplo `SENTINEL-USER-…`) para comprobar que no aparecen en ninguna salida.
- Los fixtures contienen contenido hostil como dato (comandos, instrucciones): nunca se ejecuta ni se interpreta; se leen solo con las funciones de la ingesta.
- Decisión tomada (aclaración de la spec): un archivo vacío o una lista vacía devuelve un resultado con 0 registros, sin error; T030 lo fija con un test.
- Los resultados de cada tarea de verificación se registran tal como salen (Principio V).

---

## Phase 1: Setup (infraestructura compartida)

**Purpose**: estructura de directorios y variables de entorno nuevas.

- [X] T001 Crear los directorios y `__init__.py`: `src/security_anomaly/ingestion/adapters/__init__.py`, `tests/unit/ingestion/__init__.py`, `tests/unit/schemas/__init__.py` y `tests/fixtures/ingestion/` (con un `README.md` que explique que todo el contenido es ficticio y que incluye cadenas centinela); comprobar que Ruff y mypy siguen en verde
- [X] T002 Ampliar `tests/unit/test_repo_hygiene.py` (test primero): `EXPECTED_VARS` incluye `PSEUDONYM_KEY` y las seis variables `INGEST_*` de `contracts/environment.md`, y `PSEUDONYM_KEY` debe contener el marcador `change-me`; confirmar que falla
- [X] T003 Añadir a `.env.example` `PSEUDONYM_KEY=change-me-use-at-least-32-random-characters` y las seis variables `INGEST_*` con sus valores por defecto (FR-001-24; contracts/environment.md) (T002)
- [X] T004 Ejecutar Ruff, formato, mypy y pytest: los tests de higiene de `.env.example` pasan con las variables nuevas y todo lo anterior (85 tests del incremento 0) sigue en verde

---

## Phase 2: Foundational (bloquea todas las historias)

**Purpose**: carga de configuración reutilizable, modelos de datos, política, errores y seudonimizador.

**⚠️ CRITICAL**: ninguna historia empieza hasta terminar esta fase.

### Tests (escribir primero; deben fallar)

- [X] T005 [P] Escribir `tests/unit/test_load_model.py`: `load_model(model_cls, env_names, environ)` valida un modelo arbitrario; valores vacíos = ausentes; el error nombra la variable y el tipo, nunca el valor; los tests existentes de `test_config.py` siguen pasando (research R11)
- [X] T006 [P] Escribir `tests/unit/schemas/test_event_models.py`: `EventV1` prohíbe campos extra y exige los 6 obligatorios; el catálogo v1 tiene los valores de `data-model.md` y `catalog_version == 1`; `NormalizedEvent` es inmutable y no tiene atributo `username`; **las propiedades y los `required` de `EventV1` coinciden con `contracts/event-v1.schema.json`** (FR-001-01)
- [X] T007 [P] Escribir `tests/unit/schemas/test_ingestion_models.py`: el conjunto de `RejectionCode` es exactamente el documentado (12 códigos de registro y 6 de lote en `ingestion-api.md`); invariante `total_records == accepted + rejected + len(duplicates)`; `rejected` = posiciones distintas; máximo 5 entradas por registro; `to_canonical_json()` con claves ordenadas, sin espacios y estable entre llamadas (FR-001-21, SC-003)
- [X] T008 [P] Escribir `tests/unit/ingestion/test_policy.py`: valores por defecto (10 485 760 / 10 000 / 100 000 / 256 / 2000-01-01 / 2100-01-01); `from_environ` válida e inválida (nombra la variable, no el valor); límites positivos; `timestamp_min < timestamp_max`; fechas ISO con zona obligatoria; vacío = por defecto (FR-001-17)
- [X] T009 [P] Escribir `tests/unit/ingestion/test_pseudonym.py`: mismo usuario y clave → mismo seudónimo; usuarios distintos → distintos; otra clave → otro; formato `usr_` + 32 hex; distingue mayúsculas; normaliza NFC y espacios; clave de menos de 32 caracteres → `ConfigError`; **clave que contiene `change-me` (incluido el valor de `.env.example`) → `ConfigError`**; sin clave y con usuario → `PseudonymKeyMissing`; `derive_id` con dominios distintos da resultados distintos; la clave no aparece en `repr`/`str` (FR-001-23, FR-001-24)
- [X] T010 [P] Escribir `tests/unit/ingestion/test_errors.py`: `BatchRejected` expone `code` y `limit` y su mensaje no contiene valores de datos; `PseudonymKeyMissing` es una `IngestionError`; ambas jerarquías se pueden capturar con la base (contracts/ingestion-api.md)

### Implementación

- [X] T011 Refactorizar `src/security_anomaly/core/config.py`: extraer `load_model(model_cls, env_names, environ)` con el saneo existente y hacer que `load_settings` lo use sin cambiar su comportamiento (research R11) (T005)
- [X] T012 [P] Implementar `src/security_anomaly/schemas/event.py`: `EventV1` (`extra="forbid"`), `NormalizedEvent` inmutable, enums y catálogo v1 con `CATALOG_VERSION = 1` (data-model.md) (T006)
- [X] T013 [P] Implementar `src/security_anomaly/schemas/ingestion.py`: `RejectionCode` (`StrEnum`), `Rejection`, `Duplicate`, `IngestionReport`, `IngestionResult` y `to_canonical_json()` (data-model.md) (T007)
- [X] T014 [P] Implementar `src/security_anomaly/ingestion/errors.py`: `IngestionError`, `BatchRejected(code, limit)`, `PseudonymKeyMissing` (T010)
- [X] T015 Implementar `src/security_anomaly/ingestion/policy.py`: `IngestionPolicy` y `from_environ()` sobre `load_model` (T008, T011)
- [X] T016 Implementar `src/security_anomaly/ingestion/pseudonym.py`: `Pseudonymizer` con HMAC-SHA256, `pseudonym()`, `derive_id()` con separación de dominio, `from_environ()`, clave `SecretStr` y rechazo de claves cortas o con el marcador `change-me` (research R6) (T009, T011, T014)
- [X] T017 Añadir fixtures compartidas en `tests/conftest.py`: `policy` (por defecto), `pseudonymizer` (clave aleatoria generada con `secrets.token_hex(32)`) y `other_pseudonymizer` (otra clave); sin claves fijas
- [X] T018 Ejecutar T005–T010 y confirmar que pasan; Ruff, formato y mypy en verde; `test_config.py` sin cambios en su resultado

**Checkpoint**: configuración, modelos, política, errores y seudonimizador listos.

---

## Phase 3: User Story 1 — Cargar un lote de eventos y obtener un informe fiable (Priority: P1) 🎯

**Goal**: ingerir JSON y CSV válidos y obtener eventos normalizados más un informe con aceptados y duplicados.

**Independent Test**: ingerir los fixtures válidos y de duplicados y comparar el informe con lo esperado.

### Tests (escribir primero; deben fallar)

- [X] T019 [P] [US1] Crear fixtures en `tests/fixtures/ingestion/`: `valid.json`, `valid.jsonl` y `valid.csv` con los mismos 5 eventos (distintos `outcome`, un usuario repetido, uno sin IP, uno con `+02:00`); `duplicates.json` con una repetición idéntica y otra con contenido distinto bajo el mismo `(source, event_id)`
- [X] T020 [P] [US1] Escribir `tests/unit/ingestion/test_readers.py`: JSON lista, JSON Lines y CSV producen los mismos registros con posiciones 1-based; detección de formato por extensión (`.json`, `.jsonl`, `.ndjson`, `.csv`); extensión desconocida → `BatchRejected("invalid_format")`; BOM tolerado; CSV con cabecera obligatoria (FR-001-02)
- [X] T021 [P] [US1] Escribir `tests/unit/ingestion/test_normalizer_basic.py`: un evento válido da un `NormalizedEvent` con timestamp en UTC (desde `+02:00`), `event_id` intacto, `user_pseudonym` en lugar del usuario, opcionales ausentes en `None`, IP comprimida, host y `source` en minúsculas (FR-001-01, FR-001-03, FR-001-11)
- [X] T022 [P] [US1] Escribir `tests/unit/ingestion/test_pipeline_basic.py`: `ingest_file` de JSON, JSONL y CSV da resultados idénticos (`to_canonical_json()`); ingerir dos veces el mismo archivo da resultados idénticos (SC-003); orden de lectura conservado; duplicado: se conserva el primero y el segundo cuenta como duplicado indicando si su contenido difería; invariante del informe; **`ingest_file` e `ingest_records` son importables desde `security_anomaly.ingestion`**; ingerir el mismo evento en dos llamadas distintas lo acepta en ambas (sin estado entre lotes) (FR-001-19, FR-001-21)

### Implementación

- [X] T023 [US1] Implementar `src/security_anomaly/ingestion/readers.py` (camino válido): `read_json`, `read_csv`, detección de formato, lectura UTF-8 (`utf-8-sig`), posiciones 1-based (research R4) (T020)
- [X] T024 [US1] Implementar `src/security_anomaly/ingestion/normalizer.py` (camino válido): validación con `EventV1`, conversión a UTC, minúsculas, IP comprimida, vacío → `None`, seudonimización (research R5) (T021, T012, T016)
- [X] T025 [US1] Implementar `src/security_anomaly/ingestion/pipeline.py`: recorrido único con deduplicación `(source, event_id)`, informe y `ingest_records` (research R8, R9) (T022, T013, T024)
- [X] T026 [US1] Exponer `ingest_file` e `ingest_records` en `src/security_anomaly/ingestion/__init__.py` con `__all__` (contracts/ingestion-api.md) (T023, T025)
- [X] T027 [US1] Ejecutar T020–T022 y confirmar que pasan; Ruff, formato y mypy en verde

**Checkpoint**: la ingesta de lotes válidos funciona y es verificable de forma independiente.

---

## Phase 4: User Story 2 — Rechazar entradas inválidas sin exponer datos (Priority: P1)

**Goal**: rechazar lo inválido con códigos estables y aplicar los límites, sin reproducir nunca valores de entrada.

**Independent Test**: ingerir los fixtures inválidos y comprobar códigos, campos y la ausencia de centinelas en las salidas.

### Tests (escribir primero; deben fallar)

- [X] T028 [P] [US2] Crear fixtures `tests/fixtures/ingestion/invalid_records.json` (un registro por código: `missing_field` con varios campos ausentes, `unknown_field`, `invalid_type`, `invalid_timestamp` sin zona, `timestamp_out_of_range` año 0001 y 9999, `invalid_ip` y con `%eth0`, `invalid_outcome`, `invalid_source`, `field_too_long` de 257 caracteres, `invalid_characters` con carácter de control, elemento que no es objeto, y registros con un campo desconocido de nombre seguro y otros con un nombre hostil o con un centinela como **nombre** de campo) y `invalid_rows.csv` (fila con columnas de más y de menos, columna desconocida, y una cabecera con nombre hostil), todos con valores centinela; más `single_object.json` (un único objeto con formato legible)
- [X] T029 [P] [US2] Escribir `tests/unit/ingestion/test_normalizer_rejections.py`: cada código con su `field` esperado; varios campos ausentes dan varias entradas (máximo 5) para una sola posición y cuentan como un registro rechazado; un campo desconocido de nombre seguro se informa por su nombre y uno con nombre hostil o con caracteres de control se informa como `<invalid-name>`; se informan como máximo 5 por registro; un lote totalmente inválido produce informe sin error global (FR-001-04, FR-001-05, FR-001-13, FR-001-16)
- [X] T030 [P] [US2] Escribir `tests/unit/ingestion/test_limits.py`: archivo mayor que `max_file_bytes` → `BatchRejected("file_too_large")` en menos de 1 s **sin leer el archivo** (se simula que `open` falla); 10 001 eventos → `too_many_events` sin procesamiento parcial; campo de 257 caracteres → ese registro `field_too_long` y el resto sigue; límites personalizados; archivo inexistente, ilegible o directorio → `file_unreadable`/`not_a_regular_file`; UTF-8 inválido → `invalid_encoding`; archivo (0 bytes o solo espacios) o lista vacíos → resultado con 0 registros y sin error; `single_object.json` y un JSON Lines cuya primera línea no vacía es inválida → `BatchRejected("invalid_format")` (FR-001-02, FR-001-17, FR-001-18, SC-007)
- [X] T031 [P] [US2] Escribir `tests/unit/ingestion/test_no_value_leak_rejections.py`: serializar informe, rechazos, excepciones (`str`, `repr`, traza) y logs capturados al ingerir los fixtures inválidos y comprobar que **ningún centinela aparece, ni como valor ni como nombre de campo**; el log `ingestion_completed` contiene solo recuentos y duración (FR-001-22, SC-002)
- [X] T032 [P] [US2] Escribir `tests/unit/ingestion/test_hostile_input.py`: valores con comandos y órdenes dirigidas a un asistente se tratan solo como datos (no crean archivos ni ejecutan nada); JSON anidado profundo → `invalid_format` sin caer; `NaN`/`Infinity` rechazados; campos CSV enormes → fila `invalid_record`; entrada mal formada no interrumpe el resto del lote (FR-001-20)

### Implementación

- [X] T033 [US2] Ampliar `src/security_anomaly/ingestion/normalizer.py` con la validación y los rechazos: traducción de errores de Pydantic a `(campo, código)` sin `input`, caracteres de control, longitudes, rango de fechas, IP sin `%`, `source` acotado, `outcome`, y nombre de campo desconocido informado solo si cumple `^[A-Za-z0-9_.-]{1,64}$` (si no, `<invalid-name>`) (research R2, R3, R5) (T029)
- [X] T034 [US2] Ampliar `src/security_anomaly/ingestion/readers.py`: comprobar el tamaño con `stat` antes de leer, tipos de archivo, UTF-8 estricto, JSON seguro (`parse_constant`, recursión), filas CSV mal formadas, fallo de la primera línea no vacía en JSON Lines → `invalid_format` y recuento de eventos antes de normalizar (research R4) (T030, T032)
- [X] T035 [US2] Ampliar `src/security_anomaly/ingestion/pipeline.py`: agregación de rechazos (`rejected`, `by_code`, máximo 5 por registro), propagación de `BatchRejected` y un único log `ingestion_completed` con recuentos (research R8, R12) (T031)
- [X] T036 [US2] Ejecutar T029–T032 y confirmar que pasan; Ruff, formato y mypy en verde

**Checkpoint**: entradas inválidas y límites controlados, sin fugas de valores.

---

## Phase 5: User Story 4 — Normalización determinista y categorías acotadas (Priority: P2)

**Goal**: la misma información produce siempre la misma salida y las categorías están acotadas; los eventos fuera de orden se marcan.

**Independent Test**: ingerir variaciones del mismo contenido y comprobar salida idéntica; ingerir categorías desconocidas y comprobar `other`.

### Tests (escribir primero; deben fallar)

- [X] T037 [P] [US4] Crear fixtures `tests/fixtures/ingestion/variants.json` (mismo contenido con mayúsculas, espacios, zonas horarias, IPv6 abreviado y completo, cadenas vacías), `unknown_categories.json` y `out_of_order.json` (con un evento anterior al máximo, uno igual y uno duplicado anterior)
- [X] T038 [P] [US4] Escribir `tests/unit/ingestion/test_normalization_determinism.py`: las variantes de `variants.json` dan `to_canonical_json()` idéntico; el orden de las claves no importa; IPv6 equivalentes dan la misma cadena; `event_type`/`action` desconocidos → `other`; `outcome` desconocido → rechazo; con 1 000 categorías aleatorias (semillas en un bucle) los valores distintos nunca superan el catálogo más uno; ausentes siempre `None` (FR-001-11, FR-001-12, FR-001-14, SC-008)
- [X] T039 [P] [US4] Escribir `tests/unit/ingestion/test_out_of_order.py`: marca solo los eventos con timestamp anterior al mayor visto antes en el lote; el igual no se marca; rechazados y duplicados no actualizan el máximo; sin estado entre llamadas; posiciones en el informe y bandera en el evento (FR-001-15)

### Implementación

- [X] T040 [US4] Completar la normalización en `src/security_anomaly/ingestion/normalizer.py`: NFC, catálogo con `other`, `outcome` en minúsculas, ausentes deterministas (research R5) (T038)
- [X] T041 [US4] Añadir la detección de fuera de orden en `src/security_anomaly/ingestion/pipeline.py` (research R9) (T039)
- [X] T042 [US4] Ejecutar T038–T039 y confirmar que pasan; Ruff, formato y mypy en verde

**Checkpoint**: salida determinista y categorías acotadas.

---

## Phase 6: User Story 5 — Proteger la identidad del usuario (Priority: P2)

**Goal**: el nombre de usuario nunca sale del módulo en claro y el sistema falla cerrado sin clave.

**Independent Test**: ingerir eventos con usuarios conocidos y buscar el nombre en todas las salidas, logs y excepciones.

### Tests (escribir primero; deben fallar)

- [X] T043 [P] [US5] Escribir `tests/unit/ingestion/test_pseudonymization_pipeline.py`: el mismo usuario recibe el mismo seudónimo en eventos y llamadas distintas; usuarios distintos, seudónimos distintos; otra clave, otro seudónimo; variantes de espacios y NFC dan el mismo seudónimo; mayúsculas distintas dan seudónimos distintos (FR-001-23)
- [X] T044 [P] [US5] Escribir `tests/unit/ingestion/test_no_username_leak.py`: serializar eventos, informe, rechazos (incluidos registros rechazados **después** de leer el usuario), excepciones y logs a nivel `DEBUG` y comprobar 0 coincidencias de los nombres de usuario centinela (FR-001-25, SC-006)
- [X] T045 [P] [US5] Escribir `tests/unit/ingestion/test_key_missing.py`: sin clave y con usuarios → `PseudonymKeyMissing` y ningún evento devuelto (falla cerrado); sin clave y sin usuarios → funciona; lote mixto → falla cerrado (FR-001-24)

### Implementación

- [X] T046 [US5] Endurecer `src/security_anomaly/ingestion/normalizer.py` y `pipeline.py`: el usuario original no se guarda en excepciones, informes ni logs; comprobación de clave antes de devolver nada; errores de Pydantic sin `input` (research R6, R12) (T043, T044, T045)
- [X] T047 [US5] Ejecutar T043–T045 y confirmar que pasan; Ruff, formato y mypy en verde

**Checkpoint**: privacidad verificada en todas las salidas.

---

## Phase 7: User Story 3 — Convertir logs reales de Linux a eventos (Priority: P2)

**Goal**: convertir `auth.log` clásico (SSH correcto y fallido, usuario inválido, `sudo` correcto y fallido) en eventos v1.

**Independent Test**: convertir los fixtures de `auth.log` y comprobar eventos, ignorados, fechas e identificadores.

### Tests (escribir primero; deben fallar)

- [X] T048 [P] [US3] Crear fixtures `tests/fixtures/ingestion/linux_auth_sample.log` (Debian/Ubuntu: `Accepted password`/`publickey`, `Failed password` con usuario válido e inválido, `Invalid user`, `sudo` correcto, `sudo` con `incorrect password attempts` y `NOT in sudoers`, líneas PAM de `sudo`, ruido de `cron`, líneas repetidas idénticas, comando de `sudo` con centinela), `linux_auth_rhel.log` (variante RHEL), `linux_auth_year_rollover.log` (31 dic → 1 ene) y `linux_auth_hostile.log` (línea de 3 000 caracteres, cadenas patológicas para expresiones regulares, órdenes como datos)
- [X] T049 [P] [US3] Escribir `tests/unit/ingestion/test_linux_auth_parsing.py`: cada tipo de línea produce el evento esperado (tipo, acción, `outcome`, IP, host); `Failed password for invalid user` y `Invalid user` distintos; `sudo` correcto y fallido sin comando, directorio ni usuario destino en ninguna salida; líneas PAM y ajenas ignoradas y contadas en `ignored_lines`; líneas de más de 2 048 caracteres ignoradas; **`ingest_linux_auth` es importable desde `security_anomaly.ingestion`** (FR-001-06, FR-001-07, FR-001-10)
- [X] T050 [P] [US3] Escribir `tests/unit/ingestion/test_linux_auth_time.py`: `start_year` y zona `Europe/Madrid` dan UTC correcto; verano e invierno; hora ambigua con `fold=0`; hora inexistente → `invalid_timestamp`; diciembre → enero suma un año; `start_year=None` → todas `missing_time_context` (FR-001-08)
- [X] T051 [P] [US3] Escribir `tests/unit/ingestion/test_linux_auth_ids.py`: reingerir el mismo archivo da los mismos `event_id`; líneas idénticas en posiciones distintas dan identificadores distintos; otra clave da otros; el identificador **no** es el `SHA-256` de la línea (no permite ataque de diccionario); sin clave → `PseudonymKeyMissing` (FR-001-09, research R6)
- [X] T052 [P] [US3] Escribir `tests/unit/ingestion/test_linux_auth_redos.py`: las cadenas patológicas de `linux_auth_hostile.log` se procesan en menos de 1 s en total (riesgo ReDoS del plan)

### Implementación

- [X] T053 [US3] Implementar `src/security_anomaly/ingestion/adapters/linux_auth.py`: cabecera syslog y cuatro familias de mensaje con expresiones regulares ancladas y cuantificadores acotados, fecha con año y zona, identificadores con HMAC y descarte de comando, directorio y usuario destino (research R7) (T049, T050, T051, T052, T016)
- [X] T054 [US3] Añadir `ingest_linux_auth` al pipeline y exponerlo en `src/security_anomaly/ingestion/__init__.py`, con `ignored_lines` en el informe y los eventos pasando por el mismo normalizador (contracts/ingestion-api.md) (T053)
- [X] T055 [US3] Ejecutar T049–T052 y confirmar que pasan; Ruff, formato y mypy en verde

**Checkpoint**: el primer formato real está soportado y verificado.

---

## Phase 8: User Story 6 — Generar datos sintéticos reproducibles (Priority: P3)

**Goal**: generar eventos sintéticos con semilla, perfiles normales y anomalías inyectadas, con etiquetas aparte.

**Independent Test**: generar dos veces con la misma semilla (idéntico) y comprobar que el informe de ingesta coincide con lo inyectado.

### Tests (escribir primero; deben fallar)

- [X] T056 [P] [US6] Escribir `tests/unit/ingestion/test_synthetic_determinism.py`: misma configuración → resultados idénticos; semillas distintas → distintos; más de `policy.max_events_per_dataset` (parámetro `policy` de `generate_synthetic`, con la política por defecto si se omite) → `ValueError` con motivo claro, y una política con otro máximo cambia el límite; configuración incoherente (por ejemplo, ráfaga mayor que `n_events`) → `ValueError`; **`generate_synthetic`, `SyntheticConfig` y `SyntheticDataset` son importables desde `security_anomaly.ingestion`** (FR-001-26, FR-001-29, SC-005)
- [X] T057 [P] [US6] Escribir `tests/unit/ingestion/test_synthetic_composition.py`: todos los eventos validan con `EventV1`; al ingerirlos el informe coincide con lo inyectado (duplicados, fuera de orden, categorías nuevas → `other`, IPs ausentes); ráfaga: al menos `burst_size` fallos desde una IP en 5 minutos; horario atípico entre 02:00 y 04:00 UTC; las etiquetas viven aparte, referencian eventos existentes y los eventos no tienen clave de etiqueta; IPs solo de rangos de documentación; usuarios y hosts ficticios (FR-001-27, FR-001-28, FR-001-29)
- [X] T058 [P] [US6] Escribir `tests/unit/ingestion/test_synthetic_scale.py`: 100 000 eventos sintéticos en menos de 60 s (SC-005) y 10 000 eventos ingeridos e informados en menos de 10 s (SC-001); imprimir los tiempos medidos. Son pruebas de humo con umbrales generosos (el tiempo esperado es muy inferior); si la CI es lenta se ajusta el umbral, nunca se elimina la medición

### Implementación

- [X] T059 [US6] Implementar `src/security_anomaly/ingestion/synthetic.py`: `SyntheticConfig`, `SyntheticLabel`, `SyntheticDataset`, `generate_synthetic(config, *, policy=None)` (`None` = política por defecto) con `random.Random(seed)` usando solo `random()` y aritmética propia, perfiles normal, ráfaga, horario atípico, IP ausente, y duplicados, fuera de orden y categorías nuevas (research R10) (T056, T057, T058)
- [X] T060 [US6] Exponer `generate_synthetic`, `SyntheticConfig` y `SyntheticDataset` en `src/security_anomaly/ingestion/__init__.py` (contracts/ingestion-api.md) (T059)
- [X] T061 [US6] Ejecutar T056–T058 y confirmar que pasan; registrar los tiempos reales; Ruff, formato y mypy en verde

**Checkpoint**: datos sintéticos reproducibles listos para los incrementos 3 y 4.

---

## Phase 9: Polish y cierre

**Purpose**: contrato público, documentación, evidencia y cierre.

- [X] T062 [P] Escribir `tests/unit/ingestion/test_public_api_contract.py` y confirmar que pasa: `security_anomaly.ingestion` exporta exactamente `ingest_file`, `ingest_records`, `ingest_linux_auth`, `generate_synthetic` y los modelos documentados; las firmas coinciden con `contracts/ingestion-api.md` (incluido el parámetro `policy` de `generate_synthetic`); los códigos de rechazo y de lote coinciden con la documentación. Es la comprobación final: las aserciones de importación de cada función ya se escriben antes en T022, T049 y T056 (FR-001-30)
- [X] T063 [P] Crear `docs/data-contract.md` a partir de `contracts/event-v1.schema.json`, el catálogo v1, los códigos de rechazo y las reglas de normalización (SPEC §3.2)
- [X] T064 Actualizar `README.md`: estado del proyecto (incremento 1), sección breve de la biblioteca de ingesta con un ejemplo mínimo de uso, variables `PSEUDONYM_KEY` e `INGEST_*`, y la advertencia de que los datos sintéticos validan el software, no la capacidad real de detección (Principio II)
- [X] T065 Ejecutar los 9 escenarios de `quickstart.md`, medir el rendimiento y registrar los resultados reales en `specs/001-ingestion/verification.md`, con la tabla FR-001-01…30 y SC-001…008 y las desviaciones
- [X] T066 [P] Búsqueda de fugas y secretos: ningún nombre de usuario, centinela, clave ni comando de `sudo` en salidas, logs, informes ni `git grep` del árbol y del historial; los fixtures solo contienen datos ficticios (IPs de rangos de documentación); `.env` no versionado (SC-006)
- [X] T067 [P] Verificación completa final: Ruff, formato, mypy (`src` y `tests`), pytest con y sin `integration`, `docker compose up --build -d --wait` con `/health` y `/ready` en 200 y `down -v`; comprobar que `pyproject.toml` no tiene dependencias nuevas y que el OpenAPI solo documenta `/health` y `/ready` (FR-001-30)
- [X] T068 **Requiere autorización del usuario (commit y push):** hacer commit del trabajo hasta esta tarea (sin `.env` ni secretos), subirlo a `main` y observar la ejecución real de los tres jobs de CI en GitHub; registrar el resultado
- [X] T069 Revisar los criterios de aceptación uno a uno y el Constitution Check del plan; proponer el mensaje de commit de cierre y **pedir autorización** antes de hacer commit y push de `verification.md` y `tasks.md` (Principio VII; Definition of Done)

---

## Dependencies & Execution Order

### Orden de fases

- **Setup (1)** → **Foundational (2)** → historias en este orden: **US1 (3) → US2 (4) → US4 (5) → US5 (6) → US3 (7) → US6 (8)** → **Polish (9)**.
- US1 y US2 son P1 y comparten `readers.py`, `normalizer.py` y `pipeline.py`; US4 y US5 (P2) los completan; US3 (adaptador) reutiliza el normalizador ya terminado; US6 (P3) reutiliza todo para sus tests de composición.

### Dependencias entre historias

- **US1**: depende de Foundational.
- **US2**: depende de US1 (amplía los mismos módulos).
- **US4**: depende de US1 y US2 (normalizador y pipeline).
- **US5**: depende de US1–US2 (el usuario ya se seudonimiza en US1; US5 verifica y endurece).
- **US3**: depende de Foundational (seudonimizador, claves) y de US1–US2/US4 (normalizador completo).
- **US6**: depende de US1–US4 para sus tests de composición.

### Dentro de cada historia

Tests (fallan) → implementación → verificación. Las tareas de test [P] de una misma historia son paralelas entre sí; las de implementación de un mismo archivo son secuenciales.

### Oportunidades de paralelismo

- Foundational: T005–T010 juntos; T012, T013, T014 juntos.
- US1: T019–T022 juntos.
- US2: T028–T032 juntos.
- US4: T037–T039 juntos.
- US5: T043–T045 juntos.
- US3: T048–T052 juntos.
- US6: T056–T058 juntos.
- Polish: T062, T063 y T066, T067 en paralelo.

### Ejemplo de paralelismo (US2)

```text
T028 tests/fixtures/ingestion/invalid_records.json · invalid_rows.csv
T029 tests/unit/ingestion/test_normalizer_rejections.py
T030 tests/unit/ingestion/test_limits.py
T031 tests/unit/ingestion/test_no_value_leak_rejections.py
T032 tests/unit/ingestion/test_hostile_input.py
```

---

## Implementation Strategy

### Entrega mínima (US1 → US2)

1. Setup + Foundational.
2. US1: lotes válidos de JSON y CSV con informe y deduplicación.
3. US2: rechazos y límites sin fugas. **PARAR y validar**: ya existe una ingesta segura y utilizable para el incremento 2.

### Entrega incremental

4. US4 (normalización completa y fuera de orden) → 5. US5 (privacidad verificada) → 6. US3 (adaptador de Linux auth) → 7. US6 (datos sintéticos) → 8. Polish.

### Criterio de cierre

El incremento está terminado solo si T062–T069 se completan con evidencia real, pytest, Ruff y mypy pasan, no hay valores de entrada ni nombres de usuario en ninguna salida y no hay dependencias nuevas. Si algún criterio falla, no se declara terminado (Principio V).
