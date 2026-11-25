# Quickstart: validar el incremento 4

Guía de validación; no contiene código de implementación. Contratos: [contracts/](contracts/).

## Requisitos previos
- Incrementos 0 a 3 instalados: `uv sync --frozen` (instala también `scikit-learn`).
- Para los escenarios 5 a 9: una PostgreSQL temporal, como en `docs/handoff.md` §8, con `DATABASE_URL` apuntando
  a un administrador, y un directorio temporal para `MODEL_DIR`.

## Escenario 1 — Calidad y tests unitarios
1. `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`
2. `uv run pytest -m "not integration"`

**Esperado:** todo pasa sin servicios externos.

## Escenario 2 — Reproducibilidad (historia 1, SC-001)
1. Generar un dataset sintético, calcular sus características y entrenar dos veces con los mismos parámetros.

**Esperado:** puntuaciones idénticas en el 100 % de los eventos; la huella del dataset coincide.

## Escenario 3 — Sin fugas (historia 1, SC-002)
1. Entrenar; alterar, añadir y quitar eventos de calibración y de prueba; volver a entrenar.

**Esperado:** transformaciones y modelo idénticos.

## Escenario 4 — Calibración y severidad (historia 2)
1. Puntuar eventos por debajo, dentro y por encima del rango de calibración y en los bordes de los umbrales.

**Esperado:** percentil en [0, 1] (0 y 1 en los extremos); `low`/`medium`/`high` en 0,79 / 0,80 / 0,94 / 0,95.

## Escenario 5 — Evaluación (historia 3, SC-003)
1. Evaluar con y sin etiquetas de un dataset sintético con ráfagas inyectadas.

**Esperado:** informe con las medidas descritas y limitaciones; la ráfaga puntúa más alto que el tráfico normal.

## Escenario 6 — Registro y versiones (historia 4)
1. `alembic upgrade head` (dos veces) y entrenar.

**Esperado:** tablas creadas una vez; versión `v0001` con todos los campos; el artefacto en `MODEL_DIR`; una
segunda ejecución crea `v0002` sin tocar `v0001`.

## Escenario 7 — Activación (historia 5, SC-007)
1. `activate v0001` sin y con `--approve`; activar `v0002`; repetirlo con hilos.

**Esperado:** sin aprobación se rechaza; siempre una sola versión activa; entrenar nunca activa.

## Escenario 8 — Proceso aparte y concurrencia (historia 6)
1. Lanzar un entrenamiento y otro a la vez; consultar `status`; simular un entrenamiento muerto.

**Esperado:** como máximo uno corre; el huérfano se marca `failed` y se puede lanzar otro.

## Escenario 9 — Carga segura (historia 7, SC-006)
1. Cargar y puntuar; manipular el artefacto; pedir una ruta externa y un enlace simbólico.

**Esperado:** el cargado puntúa igual que el recién entrenado; lo demás se rechaza antes de deserializar.

## Escenario 10 — Rendimiento (SC-004 y SC-005)
1. Entrenar y evaluar 100.000 eventos; medir la puntuación de un evento individual.

**Esperado:** menos de 5 minutos y p95 menor de 50 ms; registrar hardware, volumen y condiciones.
