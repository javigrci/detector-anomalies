# Quickstart: validar el incremento 3

Guía de validación; no contiene código de implementación. Contratos: [contracts/](contracts/).

## Requisitos previos
- Incrementos 0 a 2 instalados: `uv sync --frozen`.
- Para el escenario 6 (puente con el almacenamiento): una PostgreSQL temporal, como en `docs/handoff.md` §8,
  con `DATABASE_URL` apuntando a un administrador.

## Escenario 1 — Calidad y tests unitarios
1. `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run mypy tests`
2. `uv run pytest -m "not integration"`

**Esperado:** todo pasa sin servicios externos.

## Escenario 2 — Ráfaga de fallos (historia 1, SC-004)
1. Generar un dataset sintético con una ráfaga de 30 fallos desde una IP, ingerirlo y calcular las características.

**Esperado:** en el último evento de la ráfaga, `ip_failure_count` = 30 y `ip_failure_rate` = 1; en el tráfico de
fondo, a lo sumo 3 y una tasa menor.

## Escenario 3 — Cero fugas de futuro (historia 1, SC-001)
1. Calcular las características de un flujo; añadir, quitar y modificar eventos posteriores a un evento dado.
2. Recalcular y comparar.

**Esperado:** el vector de ese evento y los de todos los anteriores no cambian; en los empates de `timestamp`,
solo cuentan los eventos que preceden al evento en `(timestamp, source, event_id)`.

## Escenario 4 — Mismo cálculo en lotes e individual (historia 3, SC-002 y SC-003)
1. Calcular 5.000 eventos por lotes y evento a evento con su historia; repetir con la entrada barajada.

**Esperado:** vectores idénticos en todos los casos.

## Escenario 5 — Fuera de orden y contexto (historia 4)
1. Calcular un evento tardío y uno al inicio del rango con y sin `history_start` anterior a su ventana.

**Esperado:** el evento tardío solo ve lo conocido hasta su instante, los vectores ya calculados no cambian y
`context_complete` es falso solo cuando la ventana empieza antes de `history_start`.

## Escenario 6 — Puente con el almacenamiento (historia 3)
1. Guardar eventos con `save_events`, calcular `features_for_range` y compararlo con el cálculo en memoria.

**Esperado:** vectores idénticos; ningún evento con `timestamp ≥ end` interviene.

## Escenario 7 — Esquema y ausentes (historias 5 y 6)
1. Consultar `FEATURE_SCHEMA`; calcular eventos sin IP, sin usuario y sin ninguno; buscar centinelas.

**Esperado:** 14 características en el orden del contrato, versión y huella fijas; ausentes a 0 con
`has_ip`/`has_user` en 0; ningún identificador en los vectores ni en los logs.

## Escenario 8 — Rendimiento y memoria (SC-005 y SC-008)
1. Calcular 100.000 eventos y comparar la memoria máxima con 10.000 eventos de la misma actividad concurrente.

**Esperado:** menos de 60 s y misma memoria de orden de magnitud; registrar hardware, volumen y condiciones.
