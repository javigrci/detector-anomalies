# Implementation Plan: Ingeniería de características

**Branch**: `003-feature-engineering` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-feature-engineering/spec.md`

## Summary

Biblioteca de características causales para el modelo: por evento (hora cíclica, día de la semana y
categorías) y por ventana deslizante de 5 minutos (eventos, fallos, tasa de fallos y usuarios distintos por
IP; IPs distintas por usuario), con un único motor de ventana que sirve igual al cálculo por lotes del
entrenamiento y al de un evento individual de la inferencia. La historia de cada evento sigue el orden total
`(timestamp, source, event_id)`; el esquema está versionado y tiene una huella determinista. Sin endpoints,
modelo, escalado, persistencia de características ni dependencias nuevas. Decisiones y alternativas en
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: ninguna nueva. Biblioteca estándar (`collections`, `datetime`, `hashlib`,
`json`, `math`) y Pydantic v2 (ya aprobado). Se consume `security_anomaly.storage.read_range` (incremento 2).

**Storage**: ninguno propio; las características se calculan bajo demanda y no se persisten (SPEC §7:
las predicciones llegan en el incremento 5).

**Testing**: pytest. Unitarias puras (sin servicios) con generadores semilla propios (sin `hypothesis`, que
sería una dependencia nueva); integración contra PostgreSQL real solo para el puente con `read_range`
(marcador `integration`).

**Target Platform**: Linux (contenedor), mismo entorno que los incrementos anteriores.

**Project Type**: biblioteca dentro del proyecto único.

**Performance Goals**: 100.000 eventos en menos de 60 s (SC-005); un evento individual con su historia de
5 minutos en menos de 100 ms (p95); memoria acotada por la ventana, no por el dataset (SC-008).

**Constraints**: causalidad estricta (Principio III); determinismo entre ejecuciones y órdenes de entrada;
sin identificadores (IP, usuario, host, `event_id`) como características; registros de actividad solo con
recuentos y duraciones; sin tocar `Settings` ni añadir variables de entorno.

**Scale/Scope**: ≈5 módulos fuente nuevos, ≈28 archivos de test (según `tasks.md`), 1 ADR (0004: semántica de la ventana y del orden causal),
hasta 100.000 eventos en las pruebas de rendimiento.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Spec como fuente de verdad | Trazable a FR-003-01…26. **Sin componentes no pedidos**: ni endpoints, ni variables de entorno, ni dependencias, ni CLI | ✅ |
| II. Honestidad en la detección | Las características describen comportamiento observable; la documentación mantiene que no demuestran un ataque y que los datos de prueba son sintéticos | ✅ |
| III. Integridad del ML (NON-NEGOTIABLE) | Historia = eventos que preceden al evento en el orden total más él mismo; ventana `(t−5 min, t]`; un único motor para lotes y evento individual (NFR-04); esquema versionado con huella; pruebas de fuga por mutación del futuro y por equivalencia lote/individual | ✅ |
| IV. Seguridad y privacidad | El vector no contiene IP, usuario, host ni `event_id` como característica; errores sin valores; logs solo con recuentos; el estado en memoria no se registra | ✅ |
| V. Test-first | Tests antes del código en cada historia; los de fuga son la puerta de aceptación del roadmap | ✅ |
| VI. Reproducibilidad | Sin aleatoriedad; sin dependencia del orden de iteración de colecciones; redondeo fijado en las funciones trigonométricas; huella del esquema fijada en un test | ✅ |
| VII. Humano en el circuito | N/A: no hay acciones sobre el entorno ni entrenamiento | ✅ (N/A) |

**Post-diseño:** sin cambios; sin violaciones, por lo que Complexity Tracking queda vacío.

## Project Structure

### Documentation (this feature)

```text
specs/003-feature-engineering/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── features-api.md         # API pública de la biblioteca y sus errores
│   └── feature-schema.md       # esquema v1: características, tipos, definiciones
├── checklists/requirements.md
└── tasks.md                    # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
src/security_anomaly/
├── schemas/
│   └── features.py             # FeatureDefinition, FeatureSchema, FeatureVector
└── features/
    ├── __init__.py             # API pública
    ├── errors.py               # FeatureError (códigos fijos, sin valores)
    ├── schema.py               # FEATURE_SCHEMA (v1), ventana, huella
    ├── engine.py               # clave de orden total y FeatureEngine (ventana deslizante)
    └── pipeline.py             # compute_features, compute_event_features, features_for_range
docs/data-contract.md           # sección «Características» (esquema v1)
tests/
├── feature_factory.py          # (ayudas: flujos de eventos reproducibles)
├── unit/features/              # esquema, engine, fuga, equivalencia, determinismo, ausentes, privacidad
└── integration/features/       # puente con read_range sobre PostgreSQL real
```

**Structure Decision:** se usa el paquete `features` que ya fija la constitución y `schemas/features.py` para
los modelos de datos que consumirán los incrementos 4 y 5.

## Fases de entrega (orden previsto para `/speckit-tasks`)

1. **Cimientos:** `FeatureError`, modelos, esquema v1 con huella, la clave de orden total y el ADR 0004.
2. **US1 (P1):** motor de ventana deslizante y agregadas por IP y usuario, sin fuga de futuro.
3. **US2 (P1):** características por evento (hora cíclica, día, categorías).
4. **US3 (P1):** cálculo por lotes, de un evento individual y por rango leído en bloques; equivalencia.
5. **US4 (P2):** eventos fuera de orden y `context_complete`.
6. **US5 (P2):** esquema versionado, huella fijada y reproducibilidad.
7. **US6 (P3):** valores ausentes, indicadores y ausencia de identificadores.
8. **Cierre:** rendimiento y memoria, documentación, escaneo de fugas, evidencia y revisión.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Una fuga de futuro invisible (por ejemplo, un empate de `timestamp` mal ordenado) | Pruebas por mutación del futuro con flujos generados con muchos empates y un test de borde exacto de la ventana |
| Divergencia entre el cálculo por lotes y el individual | Un único `FeatureEngine`; un test de equivalencia sobre ≥ 5.000 eventos |
| Memoria que crece con el dataset | El estado se poda al avanzar el reloj; test con `tracemalloc` a 10.000 y 100.000 eventos |
| El orden de entrada altera el resultado | Modo ordenado por clave que verifica el orden y modo por defecto que ordena; test con entradas barajadas |
| Cambiar una característica sin subir la versión | Huella del esquema fijada junto a la versión en un test: cualquier cambio lo rompe hasta actualizar ambas |
| Diferencias de `sin`/`cos` entre plataformas | Redondeo a 12 decimales y solo 24 valores posibles (hora entera) |
| Pruebas de rendimiento frágiles en la CI | Umbrales generosos (SC-005), medición registrada; se ajusta el umbral, no se quita la medición |

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

Sin entradas: no hay componentes no pedidos ni violaciones.
