# Verificación del incremento 1

**Fecha:** 2026-11-20 · **Estado del código:** árbol de trabajo previo al commit de T068 ·
**Entorno:** WSL2 (Ubuntu), Docker Desktop 29.3.0, Compose 5.1.0, uv 0.11.29, Python 3.12.3.

Todos los resultados son los observados en la ejecución; los tiempos son de una máquina de
desarrollo y no son garantías. La CI de GitHub **todavía no se ha ejecutado** para este incremento
(se registra tras T068).

## Resultado global

| Comprobación | Resultado |
|---|---|
| Ruff (lint) | All checks passed |
| Ruff (formato) | 121 files already formatted |
| mypy estricto (`src` y `tests`) | 0 errores (32 + 47 archivos) |
| pytest sin integración | **329 passed** (85 del incremento 0 + 244 nuevos), 2 deselected |
| pytest integración (PostgreSQL 16 real) | **2 passed** |
| `alembic upgrade head` | salida 0 |
| `uv lock --check` | salida 0: `uv.lock` vigente |
| Dependencias | sin cambios: el único cambio de `pyproject.toml` es una excepción de Ruff para los tests (`S311`) |
| OpenAPI | solo documenta `/health` y `/ready` (sin rutas nuevas) |
| `docker compose up --build -d --wait` | API y base de datos *Healthy* en 25 s; `/health` 200, `/ready` 200; la imagen importa `security_anomaly.ingestion` (19 exportaciones); proceso con UID 10001 |

## Escenarios de `quickstart.md`

Ejecutados con un script contra la API pública (fixtures de `tests/fixtures/ingestion/` y datos
sintéticos). Las 26 comprobaciones salieron OK.

| # | Escenario | Resultado |
|---|---|---|
| 1 | Calidad y tests | OK (tabla anterior) |
| 2 | Lote válido JSON y CSV | OK. JSON y CSV dan el mismo `to_canonical_json()`; 5 aceptados, 0 rechazados, 0 duplicados; dos ejecuciones idénticas |
| 3 | Rechazos y duplicados | OK. `invalid_records.json`: 16 registros, 16 rechazados, invariante cumplido, **0 centinelas** en el informe; duplicados `(3, False)` y `(4, True)` |
| 4 | Límites | OK. Archivo de 11 MB → `file_too_large` en 0,0000 s (sin abrirlo); 10.001 eventos → `too_many_events`; campo de 257 caracteres → solo se rechaza ese registro |
| 5 | Linux auth | OK. `linux_auth_sample.log`: 10 eventos y 3 líneas ignoradas; sin comando de `sudo` ni usuarios en la salida; `start_year=None` → 10 `missing_time_context`; diciembre → enero: años 2026, 2027, 2027; mismos `event_id` al reingerir |
| 6 | Normalización | OK. Las 6 variantes de `variants.json` normalizan igual (1 aceptado + 5 duplicados idénticos); fuera de orden = posiciones (3, 8); categorías nuevas → `other` |
| 7 | Seudonimización | OK. Mismo usuario, mismo seudónimo; otra clave, otro seudónimo; sin clave → `PseudonymKeyMissing` |
| 8 | Datos sintéticos | OK. Misma semilla → idéntico; otra semilla → distinto; el informe coincide con lo inyectado (20 duplicados, 10 fuera de orden, 0 rechazados); 100.000 eventos en 1,59 s; 100.001 → `ValueError` |
| 9 | Rendimiento (SC-001) | OK. 10.000 eventos ingeridos e informados en **0,361 s** |

## Requisitos funcionales

| FR | Evidencia |
|---|---|
| 001-01 | `schemas/test_event_models.py` (incluida la coincidencia con `event-v1.schema.json`), `test_normalizer_basic.py` |
| 001-02 | `test_readers.py`, `test_pipeline_basic.py`, `test_limits.py` (objeto único, JSONL con primera línea inválida) |
| 001-03 | `test_normalizer_rejections.py` (sin zona, 0001 y 9999), `test_policy.py`, `test_normalizer_basic.py` (UTC) |
| 001-04 | `test_normalizer_rejections.py`, `test_normalization_determinism.py` (`outcome`) |
| 001-05 | `test_normalizer_rejections.py` (campo seguro, nombre hostil → `<invalid-name>`, máximo 5), `test_no_value_leak_rejections.py` |
| 001-06 | `test_linux_auth_parsing.py` (SSH correcto y fallido, usuario inválido, `sudo` correcto y fallido; variantes Debian/Ubuntu y RHEL) |
| 001-07 | `test_linux_auth_parsing.py` (3 ignoradas), `test_linux_auth_redos.py` |
| 001-08 | `test_linux_auth_time.py` (año, zona, ambiguas, inexistentes, cambio de año, sin `start_year`) |
| 001-09 | `test_linux_auth_ids.py` |
| 001-10 | `test_linux_auth_parsing.py` (centinelas de comando, directorio y clave SSH ausentes) |
| 001-11 | `test_normalization_determinism.py` (variantes idénticas byte a byte), `test_pipeline_basic.py` |
| 001-12 | `test_normalization_determinism.py` (`other`, `outcome` rechazado, cardinalidad con 5 semillas × 1.000 categorías) |
| 001-13 | `test_normalizer_rejections.py` (`invalid_source`) |
| 001-14 | `test_normalization_determinism.py` (ausentes, `None`, vacío, espacios idénticos) |
| 001-15 | `test_out_of_order.py` |
| 001-16 | `test_normalizer_rejections.py` (los 12 códigos con su campo), `test_limits.py` |
| 001-17 | `test_policy.py`, `test_limits.py` |
| 001-18 | `test_limits.py` (archivo, lote, campo) |
| 001-19 | `test_pipeline_basic.py` (duplicados, sin estado entre llamadas) |
| 001-20 | `test_hostile_input.py`, `test_linux_auth_redos.py` |
| 001-21 | `schemas/test_ingestion_models.py`, `test_pipeline_basic.py` |
| 001-22 | `test_no_value_leak_rejections.py`; escenario 3 |
| 001-23 | `test_pseudonym.py`, `test_pseudonymization_pipeline.py` |
| 001-24 | `test_key_missing.py`, `test_pseudonym.py` (clave corta y marcador `change-me`) |
| 001-25 | `test_no_username_leak.py` (incluye registros rechazados y excepciones) |
| 001-26 | `test_synthetic_determinism.py` |
| 001-27 | `test_synthetic_composition.py` |
| 001-28 | `test_synthetic_composition.py` (etiquetas aparte, 980 únicas) |
| 001-29 | `test_synthetic_composition.py` (rangos de documentación, `userNNN`, `srv-demo-NN`), `test_synthetic_determinism.py` (máximo desde la política) |
| 001-30 | `test_public_api_contract.py`; sin dependencias nuevas, sin rutas nuevas, sin persistencia |

## Criterios de éxito

| SC | Evidencia |
|---|---|
| 001 | 10.000 eventos ingeridos en 0,36–0,44 s (umbral 10 s) |
| 002 | `test_no_value_leak_rejections.py` y escenario 3: 100 % de rechazos con posición, código y campo y 0 valores en informe y logs |
| 003 | Tests de determinismo y escenario 2: resultados idénticos, incluidos los `event_id` |
| 004 | Fixtures de Linux auth: 100 % de las líneas dan el evento esperado o se ignoran; ninguna línea hostil interrumpe el proceso |
| 005 | 100.000 eventos en 1,59–1,75 s (umbral 60 s); misma semilla → idéntico |
| 006 | Tests de fuga con nombres centinela y escenario 7: 0 nombres de usuario en salidas, logs y excepciones; escaneo del árbol y del historial sin hallazgos |
| 007 | Archivo de 11 MB rechazado en menos de 0,001 s sin abrirlo |
| 008 | `test_normalization_determinism.py`: valores distintos ≤ catálogo, con 5 semillas |

## Pruebas de mutación

Para comprobar que los tests de privacidad no son vacíos se rompió a propósito
`Pseudonymizer.pseudonym` (devolvía el usuario en claro): **11 tests fallaron**; al restaurar el
original (archivo idéntico) volvieron a pasar.

## Desviaciones y observaciones

1. **Tests que pasaron sin código nuevo:** los de normalización determinista (T038) y los de
   privacidad (T043–T045) pasaron en cuanto se escribieron, porque el normalizador y el
   seudonimizador de las fases anteriores ya cumplían esas propiedades. El requisito de "fallar
   primero" no se dio en esos casos; se compensó con la prueba de mutación anterior.
2. **Tests propios corregidos durante la implementación:** dos tests tenían una aserción sin
   sentido y un tercero (`test_custom_field_limit_applies`) fijaba un límite de 10 caracteres que
   también rechazaba campos legítimos como el `timestamp`; el código era correcto y se ajustó el
   test. Ninguna regla de la aplicación se relajó para que pasaran.
3. **Cobertura de formatos reales de `auth.log`:** los fixtures de Debian/Ubuntu y RHEL son
   sintéticos, escritos a partir del formato conocido; **no se han contrastado con logs reales de
   un servidor**. El recuento de líneas ignoradas sobre datos reales queda como comprobación
   pendiente (riesgo del plan).
4. **Marcador `change-me` en `PSEUDONYM_KEY`:** copiar `.env.example` sin cambiar la clave produce un
   `ConfigError` claro (a propósito). Compose no pasa esta variable a la API porque todavía no usa la
   ingesta.
5. **`max_events_per_dataset`:** solo lo aplica el generador sintético (decisión del plan); las
   funciones de ingesta aplican el máximo por lote.
6. **Entrada vacía:** un archivo o una lista vacíos devuelven 0 registros sin error, decisión
   registrada en la spec.
7. **Dos excepciones de Ruff:** `S311` en `tests/` (generador con semilla, sin uso criptográfico) y un
   `noqa: S108` en un test que solo comprueba que un fichero hostil **no** se crea.
8. **Aviso heredado:** `starlette.testclient` sigue avisando de que `httpx` está en desuso (incremento
   0); no afecta a estos tests.
9. **Límites conocidos:** un `auth.log` no cronológico en el cambio de año se interpreta mal;
   rotar `PSEUDONYM_KEY` rompe la idempotencia entre ingestas (la política se decide en el
   incremento 2).
