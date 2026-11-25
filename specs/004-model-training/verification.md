# Verificación del incremento 4 — Entrenamiento del modelo

**Fecha:** 2026-11-24 · **Estado:** implementación completa y verificada en local; **sin commitear**. Commit,
push y CI de GitHub pendientes de la confirmación del usuario (T060 y T061). Todos los resultados de este
documento son salidas reales. El ciclo (specify → clarify → plan → tasks → analyze → implement) se ejecutó en
modo automático, siguiendo las recomendaciones del asistente.

## 1. Puertas de calidad (T057)

| Comprobación | Resultado |
|---|---|
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `295 files already formatted` |
| `uv run mypy` (estricto, `src`) | `Success: no issues found in 59 source files` |
| `uv run mypy tests` | `Success: no issues found in 157 source files` |
| `uv run pytest -q -m "not integration"` | **1006 passed**, 165 deselected |
| `uv run pytest -q -m integration` (PostgreSQL 16 real) | **165 passed**, 1006 deselected |

Total: **1.171 tests** (908 al cerrar el incremento 3). Un aviso heredado (`starlette.testclient` con `httpx`)
sigue igual. Entorno de las mediciones: Linux 6.6.87.2 (WSL2), 12 CPU, Python 3.12.15, scikit-learn 1.9.1,
numpy 2.5.5, scipy 1.18.1, PostgreSQL 16 en un contenedor local. No son garantías de rendimiento.

## 2. Criterios de éxito

| SC | Resultado | Evidencia |
|---|---|---|
| SC-001 | ✅ Dos entrenamientos con el mismo dataset: puntuaciones, calibración y resumen del modelo idénticos; también en procesos con `PYTHONHASHSEED` 0, 1, 4242 y aleatorio; otro dataset da otro modelo | `test_reproducibility.py` |
| SC-002 | ✅ 7 semillas × (cambiar, quitar y añadir) eventos de calibración y de prueba: transformaciones y bosque idénticos; la prueba tampoco cambia la calibración; cambiar el entrenamiento sí cambia el ajuste (control) | `test_no_leak_into_training.py` |
| SC-003 | ✅ Con ráfagas de fallos inyectadas (3 semillas), la puntuación media de las ráfagas supera la del tráfico normal y más de la mitad de los eventos de ráfaga supera el umbral operativo | `test_burst_detection.py` |
| SC-004 | ✅ 100.000 eventos (separar + entrenar + calibrar + evaluar con etiquetas): **0,88 s** (umbral 300 s) | `test_perf_training.py` |
| SC-005 | ✅ Puntuar un evento individual: p95 **9,98 ms**, máximo 22,80 ms (umbral 50 ms, p95) | `test_perf_training.py` |
| SC-006 | ✅ Artefacto con un byte cambiado, nombre con componentes de ruta, ruta externa, enlace simbólico (dentro y fuera) y archivo ausente se rechazan antes de deserializar nada (`joblib.load` no se llega a llamar) | `test_artifacts.py`, `test_load_model.py` |
| SC-007 | ✅ 8 hilos intentando abrir un entrenamiento: exactamente 1 `running`; 8 hilos × 16 activaciones: nunca más de una versión activa | `test_training_concurrency.py`, `test_activation.py` |
| SC-008 | ✅ 0 apariciones de usuario, IP, host, identificador, contraseña o ruta en el artefacto, los registros, los informes, los errores, la salida de la CLI y los logs | `test_no_identifiers_stored.py`, `test_no_leaks_ml.py` |
| SC-009 | ✅ La palabra «probabilidad» solo aparece en frases que la niegan, y ningún identificador se llama como tal | `test_no_probability_wording.py` |

El entrenamiento es tan rápido porque Isolation Forest submuestrea 256 filas por árbol (`max_samples="auto"`):
no es un error de medida. La separación y la evaluación sobre 100.000 eventos sí recorren todo el dataset.

## 3. Escenarios de `quickstart.md`

| Escenario | Resultado |
|---|---|
| 1. Calidad y unitarios | ✅ sección 1 |
| 2. Reproducibilidad | ✅ `test_reproducibility.py` |
| 3. Sin fugas | ✅ `test_no_leak_into_training.py` |
| 4. Calibración y severidad | ✅ `test_percentile.py`, `test_severity.py` (0,79 / 0,80 / 0,94 / 0,95 → `low` / `medium` / `medium` / `high`) |
| 5. Evaluación | ✅ `test_evaluation_*.py`, `test_burst_detection.py` |
| 6. Registro y versiones | ✅ `test_migration_ml.py` (dos aplicaciones sin error), `test_registry.py` (`v0001`, `v0002` sin tocar la primera) |
| 7. Activación | ✅ `test_activation.py`, `test_activation_approval.py` |
| 8. Proceso aparte y concurrencia | ✅ `test_training_concurrency.py`, `test_cli_end_to_end.py` (procesos reales con `subprocess`; el servicio responde en menos de 2 s durante el entrenamiento) |
| 9. Carga segura | ✅ `test_load_model.py` |
| 10. Rendimiento | ✅ sección 2 (SC-004 y SC-005) |

## 4. Matriz de requisitos

| Requisitos | Tareas | Tests principales |
|---|---|---|
| FR-004-01 | T020, T021, T026 | `test_dataset_schema.py`, `test_build_dataset.py` |
| FR-004-02…05 | T018, T019, T026 | `test_split_temporal.py`, `test_dataset_fingerprint.py` |
| FR-004-06, 07 | T022, T027 | `test_transformations.py` |
| FR-004-08…10, 13 | T006, T023–T025, T027 | `test_model_parameters.py`, `test_reproducibility.py`, `test_no_leak_into_training.py` |
| FR-004-11, 12 | T014, T017, T027 | `test_percentile.py` |
| FR-004-14, 15 | T006, T007, T015, T017 | `test_severity.py`, `test_ml_models.py`, `test_config.py` |
| FR-004-16 | T016 | `test_no_probability_wording.py` |
| FR-004-17…20 | T028–T032 | `test_evaluation_*.py` |
| FR-004-21…23, 25 | T035–T041 | `test_artifacts.py`, `test_registry.py`, `test_no_identifiers_stored.py` |
| FR-004-24 | T033, T034, T038 | `test_migration_ml.py`, `test_privileges_ml.py` |
| FR-004-26 | T036, T042–T044 | `test_activation.py`, `test_activation_approval.py` |
| FR-004-27, 28 | T045–T049 | `test_training_concurrency.py`, `test_cli.py`, `test_cli_end_to_end.py` |
| FR-004-29, 30 | T035, T050, T052 | `test_artifacts.py`, `test_load_model.py` |
| FR-004-31 | T005, T046, T054 | `test_errors.py`, `test_cli.py`, `test_no_leaks_ml.py` |
| FR-004-32 | T002, T003, T059 | ADR 0005; sin endpoints; una sola dependencia directa nueva (ver §6) |

## 5. Pruebas de mutación

Los tests de las puertas de aceptación se comprobaron rompiendo el código a propósito (restaurado y verificado
con `diff` después de cada una, con `PYTHONDONTWRITEBYTECODE=1` y `__pycache__` limpio):

| Mutación | Resultado |
|---|---|
| Transformaciones ajustadas con entrenamiento **y prueba** | 7 tests fallan (`test_no_leak_into_training.py`, `test_transformations.py`) |
| Calibración calculada con el conjunto de **prueba** | 15 tests fallan (`test_no_leak_into_training.py`, `test_model_parameters.py`) |
| Cargar un artefacto **sin verificar la huella** | **la primera versión del test NO la detectó** (8 pasaban): el doble de `joblib.load` lanzaba una excepción que el código convertía en `artifact_integrity`, así que el test pasaba igualmente. Se reforzó para comprobar que `joblib.load` no se llama nunca; ahora la mutación hace fallar 1 test |
| Activar **sin desactivar la anterior** (dos versiones activas) | 2 tests fallan (`test_activation.py`) |
| Activar **sin exigir aprobación** | 6 tests fallan (`test_activation_approval.py`) |

## 6. Alcance (T059)

- `git diff -- pyproject.toml`: **una dependencia directa nueva, `scikit-learn>=1.9,<2`** (aprobada en el ADR 0005),
  más la configuración de mypy para `sklearn`, `joblib` y `scipy`. Transitivas fijadas en `uv.lock`: numpy 2.5.5,
  scipy 1.18.1, joblib 1.6.0, threadpoolctl 3.8.0, cloudpickle 3.1.3 y narwhals 2.29.0. Sin `pandas`.
- Sin `APIRouter` ni endpoints; sin dashboard; sin puntuación por API.
- Imagen de Docker: **263 MB antes → 618 MB después** (`docker build`); se importa `sklearn` y la CLI arranca dentro
  de la imagen.
- Sin secretos en el diff; `.env` no existe en el árbol.

## 7. Decisiones tomadas en modo automático (para tu revisión)

Opciones recomendadas por el asistente, aceptadas sin pausas por indicación del usuario. Constan en el spec
(Clarifications) y en el ADR 0006:

1. **Separación:** 70/15/15 por orden temporal, con los empates de instante juntos.
2. **Artefactos:** un archivo por versión en `MODEL_DIR`, con SHA-256 registrado y verificado antes de cargar.
3. **Credenciales de BD:** el rol `anomaly_app` existente, con permisos por columna sobre las dos tablas nuevas
   (sin rol nuevo).
4. **Operación sin API:** una CLI mínima `python -m security_anomaly.ml` (`train`, `status`, `list`,
   `activate --approve`) y variables de entorno nuevas. **No estaban pedidas expresamente**: están en Complexity
   Tracking del plan.
5. **Etiquetas de evaluación:** opcionales y externas; solo se usan sobre la prueba.
6. **Dependencia nueva:** `scikit-learn` (ADR 0005), que el usuario indicó que debía aprobarse y registrarse.
7. **Análisis (hallazgo importante):** faltaba un ADR de diseño (Constitución VI); se añadió el 0006 antes de
   implementar.

## 8. Desviaciones y limitaciones (dichas tal como son)

1. **Test débil detectado y corregido** por mutación (ver §5, la carga sin verificar la huella).
2. **Tests del incremento 2 actualizados:** `tests/integration/test_alembic.py` (ahora esperan las tablas nuevas) y
   `tests/unit/storage/test_schema.py` (el metadato ya no contiene solo `events` si el paquete `ml` está importado).
   No cambia ningún comportamiento del incremento 2.
3. **La carga exige las mismas versiones de scikit-learn, numpy y scipy** que se usaron al entrenar (igualdad
   estricta): es conservador, y subir una versión obliga a reentrenar (ADR 0005).
4. **Un evento de prueba sin etiqueta** no entra en las métricas de clasificación, y una etiqueta de un evento que
   no está en la prueba se ignora (documentado en `evaluate`).
5. **El latido** solo se actualiza entre fases del entrenamiento (no durante el ajuste del bosque, que dura
   milisegundos a segundos); el límite por defecto de 60 minutos es amplio.
6. **Los tests de la CLI** (unitarios) sustituyen la biblioteca por dobles; el flujo real de procesos separados lo
   cubre `test_cli_end_to_end.py` contra PostgreSQL real.
7. **Sin CI todavía:** nada de este incremento se ha ejecutado en GitHub; el job `integration` instalará
   scikit-learn con `uv sync --frozen`.
8. Los datos son sintéticos: las métricas validan el software, no demuestran detección real.

## 9. Riesgos y decisiones pendientes

- Confirmar la CI tras el push (instalación de scikit-learn y la migración 0002 en el job `integration`).
- Revisar la CLI, las variables de entorno nuevas y los permisos por columna decididos en modo automático.
- Valores finales de benchmarks, de umbrales (0,80 y 0,95) y de hiperparámetros: dependen de datos reales y del
  incremento 7.
- La imagen de Docker pesa 355 MB más; si importa, separar una imagen de entrenamiento (ADR 0005).

## 10. Commits

Pendientes de la confirmación explícita del usuario (T060 y T061).
