# Verificación del incremento 3 — Ingeniería de características

**Fecha:** 2026-11-24 · **Estado:** cerrado. Implementación verificada en local y **CI de GitHub en verde**
(run #10, commit `72e1412`; los tres jobs en verde según el usuario, que lo comprobó en la interfaz de GitHub porque
el repositorio es privado y no pude consultarlo). Todos los resultados de este documento son salidas reales. El ciclo (specify → clarify → plan → tasks → analyze → implement) se ejecutó en
modo automático, siguiendo las recomendaciones del asistente.

## 1. Puertas de calidad (T047)

| Comprobación | Resultado |
|---|---|
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `232 files already formatted` |
| `uv run mypy` (estricto, `src`) | `Success: no issues found in 46 source files` |
| `uv run mypy tests` | `Success: no issues found in 120 source files` |
| `uv run pytest -q -m "not integration"` | **794 passed**, 114 deselected |
| `uv run pytest -q -m integration` (PostgreSQL 16 real) | **114 passed**, 794 deselected |

Total: **908 tests** (599 al cerrar el incremento 2). Un aviso heredado (`starlette.testclient` con `httpx`)
sigue igual. Sin dependencias nuevas.

Entorno de las mediciones: Linux 6.6.87.2 (WSL2), 12 CPU, Python 3.12.15, PostgreSQL 16 en un contenedor local
con configuración por defecto. No son garantías de rendimiento.

## 2. Criterios de éxito

| SC | Resultado | Evidencia |
|---|---|---|
| SC-001 | ✅ Cero fugas de futuro: con 50 semillas × 4 eventos × 4 mutaciones (quitar, añadir, modificar el futuro y quitar la mitad), ningún vector cambia | `test_no_future_leak.py` (200 casos × 4 mutaciones = 800 comprobaciones), `test_features_for_range.py` |
| SC-002 | ✅ 5.000 eventos por lotes y uno a uno (con historia que incluye eventos posteriores a propósito): vectores idénticos en el 100 % | `test_batch_vs_individual.py` |
| SC-003 | ✅ Entradas barajadas, invertidas y repetidas, y procesos con `PYTHONHASHSEED` 0, 1, 4242 y aleatorio: mismos vectores | `test_input_order.py`, `test_determinism.py` |
| SC-004 | ✅ Ráfaga de 30 fallos del generador sintético: el último evento tiene `ip_failure_count` = 30, `ip_failure_rate` = 1; el tráfico de fondo, a lo sumo 3 | `test_burst_synthetic.py` |
| SC-005 | ✅ 100.000 eventos en **1,62 s** y **1,77 s** (dos ejecuciones; umbral 60 s). Evento individual con 1.623 eventos de historia: p95 **15,99 ms** y **12,49 ms** (umbral 100 ms); el máximo llegó a 126,89 ms en una ejecución, pero el criterio es el p95 | `test_perf_features.py` |
| SC-006 | ✅ 0 apariciones de IP, seudónimo, host o centinelas en vectores, esquema, errores y registros | `test_no_identifier_leak.py`, `test_features_logging.py` |
| SC-007 | ✅ Cambiar cualquier campo de cualquiera de las 14 características, intercambiar vecinas, cambiar ventana, versión o membresía cambia la huella (≈ 70 casos); el par `(versión, huella)` está fijado | `test_schema_sensitivity.py`, `test_schema_golden.py` |
| SC-008 | ✅ Pico de memoria 417 KiB con 10.000 eventos y 115 KiB con 100.000 (relación 0,28; el criterio es que no crezca): no depende del tamaño del dataset | `test_memory_bounded.py` |

La relación de memoria menor que 1 se debe a que la primera pasada paga la construcción de cachés de la
biblioteca; no hay crecimiento con el volumen. Con un evento por segundo, la ventana contiene unos 300 eventos
y el estado queda vacío tras un hueco largo (`state_size == 1`).

## 3. Escenarios de `quickstart.md`

| Escenario | Resultado |
|---|---|
| 1. Calidad y unitarios | ✅ sección 1 |
| 2. Ráfaga de fallos | ✅ `test_burst_synthetic.py` |
| 3. Cero fugas de futuro | ✅ `test_no_future_leak.py`, `test_ties_order.py` |
| 4. Lotes e individual | ✅ `test_batch_vs_individual.py`, `test_input_order.py` |
| 5. Fuera de orden y contexto | ✅ `test_out_of_order.py`, `test_context_complete.py`, `test_history_start_errors.py` |
| 6. Puente con el almacenamiento | ✅ `test_features_for_range.py` (PostgreSQL real, bloques de 37 eventos) |
| 7. Esquema y ausentes | ✅ `test_schema_contract.py`, `test_missing_fields.py`, `test_no_identifier_leak.py` |
| 8. Rendimiento y memoria | ✅ sección 2 (SC-005 y SC-008) |

## 4. Matriz de requisitos

| Requisitos | Tareas | Tests principales |
|---|---|---|
| FR-003-01…03 | T019, T020 | `test_event_features.py` |
| FR-003-04…06, 08…10 | T012, T016, T017, T018 | `test_window_counts.py`, `test_window_vs_reference.py`, `test_burst_synthetic.py` |
| FR-003-07 | T013, T016, T018 | `test_window_boundary.py` |
| FR-003-11, 12 | T004, T010, T014, T015, T022 | `test_order_key.py`, `test_ties_order.py`, `test_no_future_leak.py`, `test_input_order.py` |
| FR-003-13 | T032 | `test_out_of_order.py` |
| FR-003-14 | T033, T035 | `test_context_complete.py` |
| FR-003-15…17 | T021–T024, T026, T028–T030 | `test_batch_vs_individual.py`, `test_presorted_streaming.py`, `test_compute_event_features.py`, `test_features_for_range.py` |
| FR-003-18, 19 | T003, T005, T008, T009, T038 | `test_features_models.py`, `test_schema_contract.py`, `test_determinism.py` |
| FR-003-20, 21 | T036, T037, T038 | `test_schema_golden.py`, `test_schema_sensitivity.py`, `test_determinism.py` |
| FR-003-22 | T040, T042 | `test_missing_fields.py` |
| FR-003-23 | T005, T041 | `test_no_identifier_leak.py` |
| FR-003-24 | T025, T031, T041 | `test_features_logging.py` |
| FR-003-25 | T002, T007, T023, T034, T035 | `test_errors.py`, `test_history_start_errors.py`, `test_presorted_streaming.py` |
| FR-003-26 | T049 | sin dependencias, endpoints ni variables de entorno (ver §6) |

## 5. Pruebas de mutación

Los tests que pasaban sin código nuevo o que protegen la causalidad se comprobaron rompiendo el código a
propósito (restaurado y verificado con `diff` después de cada una):

| Mutación | Tests que fallan |
|---|---|
| Borde de la ventana inclusivo (`<=` → `<`) | 19 (`test_window_boundary.py`, `test_window_vs_reference.py`) |
| La historia de un evento individual incluye eventos posteriores | 4 (`test_compute_event_features.py`, `test_batch_vs_individual.py`) |
| La clave de orden solo mira el instante (los empates posteriores cuentan) | 1 (`test_ties_order.py`) |
| Cambiar el texto de una definición del esquema | `test_schema_golden.py` |

## 6. Alcance (T049)

- `git diff -- pyproject.toml uv.lock`: vacío → **sin dependencias nuevas**.
- Sin `APIRouter` ni endpoints; sin `os.environ` ni variables de entorno nuevas en `features`; sin persistencia de
  características ni CLI.
- Sin secretos en el diff; `.env` no existe.

## 7. Decisiones tomadas en modo automático

Recomendaciones del asistente, aceptadas sin pausas por indicación del usuario:

1. **Clarificaciones (5):** orden total `(timestamp, source, event_id)`, ventana deslizante, contexto declarado
   por quien llama, ausentes a 0 con indicadores y agregación por `(source, IP)` y `(source, usuario)`.
2. **Análisis (5 hallazgos):** se añadió el ADR 0004 (T011) porque la lectura del orden es más estricta que SPEC
   §4.4; un `conftest.py` propio para la integración de características; el protocolo `EventLike`; un mapeo de solo
   lectura en `FeatureVector.features`; y se corrigió la cifra de archivos de test en el plan.

## 8. Desviaciones y limitaciones (dichas tal como son)

1. **`chunk_size` en `features_for_range`:** se añadió como argumento opcional (por defecto 5.000) para poder
   probar la lectura por bloques; el contrato (`features-api.md`) se actualizó.
2. **`features_for_range` y `history_start`:** los eventos anteriores a `history_start` no se leen y no provocan error
   (no están en la historia declarada); el error `event_before_history` aplica a `compute_features` y
   `compute_event_features`.
3. **Memoria:** el pico es menor con 100.000 eventos que con 10.000 por el coste de la primera pasada (cachés). Lo que
   se comprueba es que no crece con el volumen.
4. **Eventos tardíos:** la biblioteca es una función pura del conjunto de eventos que se le pasa. «No recalcular los
   agregados pasados» (D5) significa que los vectores ya devueltos son inmutables y que calcular un evento tardío no
   los toca; si un llamador recalcula todo el conjunto desde cero, los eventos posteriores al tardío sí lo verán. Lo
   que persista los vectores (incremento 5) decide cuándo recalcular.
5. **Eventos con claves repetidas en el modo `presorted`:** solo se detectan los de clave idéntica consecutivos; el modo
   por defecto detecta cualquier `(source, event_id)` repetido.
6. **CI:** antes del push, los tests de integración se ejecutaron contra un PostgreSQL 16 temporal con autenticación
   `trust`, como en el incremento 2; después, en GitHub: run #10 con los tres jobs en verde.

## 9. Riesgos y decisiones pendientes

- Los tests de rendimiento tienen umbrales generosos y pasaron en la CI (run #10); aun así, un runner lento podría
  acercarse al de 100 ms del evento individual (p95 medido en local: 12–16 ms).
- `day_of_week` se entrega como entero 0–6; su codificación (cíclica u otra) la decide el incremento 4.
- Proponer una aclaración de SPEC §4.4/§4.5 para recoger las precisiones del ADR 0004 (no se ha editado SPEC.md).

## 10. Commits

`72e1412` (T050), subido a `main` con autorización explícita del usuario (T051).
