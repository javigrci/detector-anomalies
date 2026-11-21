# Implementation Plan: Persistencia de eventos

**Branch**: `002-persistence` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-persistence/spec.md`

## Summary

Capa de persistencia sobre PostgreSQL 16 para los eventos normalizados del incremento 1: primera
migración, guardado idempotente y atómico, consulta con filtros y paginación, lectura por rango
temporal para el incremento 3, retención con purga explícita y tres roles de base de datos (migrador,
aplicación y mantenimiento) con privilegios mínimos. Incluye el ADR de rotación de `PSEUDONYM_KEY`,
una CLI mínima de operación y los cambios de Compose y CI para aprovisionar los roles. Sin
endpoints, autenticación, características ni modelos. Decisiones y alternativas en
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: ninguna nueva. SQLAlchemy 2 (Core), Alembic y `psycopg` 3 (ya aprobados),
Pydantic v2 y biblioteca estándar (`argparse`, `uuid`, `concurrent.futures` en tests).

**Storage**: PostgreSQL 16 (tabla `events`); el esquema solo lo crea una migración de Alembic.

**Testing**: pytest. Unitarias sin servicios; integración contra PostgreSQL real (marcador
`integration`) con una base de datos efímera por sesión y roles aprovisionados al vuelo.

**Target Platform**: Linux (contenedor), mismo entorno que los incrementos anteriores.

**Project Type**: biblioteca dentro del proyecto único, más una CLI mínima de operación.

**Performance Goals**: guardar 10.000 eventos en menos de 10 s (SC-001); consulta por rango de un día
sobre 100.000 eventos en menos de 1 s (SC-004); guardado de un lote de 10.000 eventos en una sola
transacción.

**Constraints**: consultas siempre parametrizadas; errores sin credenciales ni valores; el rol de
aplicación no puede borrar ni alterar el esquema; la base de datos no se publica en el equipo; las
migraciones y la purga son explícitas, nunca automáticas.

**Scale/Scope**: ≈10 módulos fuente nuevos, ≈16 archivos de test, 1 migración, 1 ADR, hasta
100.000 eventos en las pruebas de rendimiento.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Evaluación | Estado |
|---|---|---|
| I. Spec como fuente de verdad | Trazable a FR-002-01…29; sin dependencias nuevas. Hay **tres componentes no pedidos expresamente** (CLI mínima, perfiles de Compose y variables de entorno nuevas) que se justifican en research R10 y se someten a tu aprobación | ✅ (con aprobación) |
| II. Honestidad en la detección | No hay puntuación; la documentación mantiene la advertencia sobre datos sintéticos | ✅ (N/A) |
| III. Integridad del ML | La lectura por rango es semiabierta y nunca devuelve eventos con `timestamp >= end`; el orden es determinista; no se persisten marcas relativas al lote | ✅ |
| IV. Seguridad y privacidad | Tres roles con mínimos privilegios; `CHECK` que obliga al formato `usr_…`; filtro por seudónimo (nunca por nombre real); consultas con parámetros; `StorageError` sin credenciales ni valores; logs solo con recuentos | ✅ |
| V. Test-first | Tests antes del código en cada historia; pruebas de privilegios y de fuga con PostgreSQL real | ✅ |
| VI. Reproducibilidad | Esquema solo por migración; aprovisionamiento idempotente con una única implementación; ADR de decisiones | ✅ |
| VII. Humano en el circuito | La purga es explícita y con credenciales propias, con modo simulación; el `downgrade` destructivo exige confirmación; el servicio no migra al arrancar | ✅ |

**Post-diseño:** sin cambios; sin violaciones, por lo que no hay entradas obligatorias en Complexity
Tracking, salvo la nota de los tres componentes no pedidos, que figura abajo.

## Project Structure

### Documentation (this feature)

```text
specs/002-persistence/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── storage-api.md          # API pública de la persistencia y sus errores
│   ├── operations.md           # roles, migraciones, CLI y Compose
│   └── environment.md          # variables de entorno nuevas
├── checklists/requirements.md
└── tasks.md                    # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
src/security_anomaly/
├── schemas/
│   └── storage.py              # EventFilter, StoredEvent, EventPage, SaveSummary, PurgeResult
├── storage/
│   ├── __init__.py             # API pública
│   ├── database.py             # (existente) motor y comprobación de conectividad
│   ├── schema.py               # Table `events`
│   ├── config.py               # StoragePolicy, MigrationSettings, MaintenanceSettings, AdminSettings
│   ├── errors.py               # StorageError
│   ├── events.py               # save_events, query_events, read_range
│   ├── retention.py            # purge_events
│   ├── roles.py                # nombres de rol y provision_roles
│   ├── __main__.py             # CLI: provision-roles, purge
│   └── migrations/
│       ├── env.py              # lee MIGRATION_DATABASE_URL
│       └── versions/0001_create_events.py
docs/decisions/0003-rotacion-pseudonym-key.md
compose.yaml · Dockerfile (sin cambios de fondo) · .env.example · .github/workflows/ci.yml
tests/
├── unit/storage/               # filtros, política, consultas, errores, comparación
└── integration/storage/        # guardado, consulta, rango, purga, privilegios, migración, rendimiento
```

**Structure Decision:** se mantiene el proyecto único y el paquete `storage` que ya fija la
constitución; `schemas/storage.py` guarda los modelos de datos que consumirán los incrementos 3 y 5.

## Fases de entrega (orden previsto para `/speckit-tasks`)

El orden vigente será el de `tasks.md`:

1. **Cimientos:** configuración y errores, modelos, tabla, ADR de rotación, roles y aprovisionamiento,
   fixtures de integración (base de datos efímera y roles).
2. **Migración:** `0001_create_events`, `env.py` con el rol migrador, `downgrade` protegido.
3. **US1:** guardado idempotente y atómico.
4. **US2:** consulta con filtros y paginación.
5. **US3:** lectura por rango temporal sin fuga de futuro.
6. **US4:** retención y purga explícita (con la CLI).
7. **US5:** privilegios de los tres roles y entorno Compose.
8. **US6:** pruebas del comportamiento del ADR de rotación.
9. **Cierre:** rendimiento, documentación, escaneo de fugas, evidencia y revisión.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Interbloqueos entre guardados concurrentes con claves solapadas | Insertar siempre ordenado por `(source, event_id)`; test con hilos |
| `docker compose up --wait` con servicios de un solo uso | Los servicios `db-setup` y `db-maintenance` van bajo perfiles y no participan en `up`; se prueba en la CI |
| La migración falla si faltan los roles | Mensaje claro que pide aprovisionar; el aprovisionamiento es idempotente y se ejecuta antes en tests, CI y Compose |
| `/ready` responde 503 hasta que se ejecuta `db-setup` | Es coherente con el arranque tolerante del incremento 0; se documenta en el README y el quickstart |
| Contraseñas con caracteres reservados en una URL de conexión | Se mantiene la regla de claves aptas para URL ya documentada; las contraseñas de rol se escriben como literales seguros con `psycopg.sql` |
| `CHECK` de catálogo desincronizado con el código | Un test compara los valores de la migración con los enums de `schemas/event.py` y falla si divergen |
| Fuga de datos por logs o mensajes de error del driver | Se descarta la excepción original; tests con cadenas centinela sobre errores y logs |
| Pruebas de rendimiento frágiles en la CI | Umbrales generosos (SC-001 y SC-004), medición registrada; se ajusta el umbral, no se quita la medición |
| Purga larga sobre muchos datos | Borrado por bloques de 5.000 con una transacción por bloque |

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

| Elemento | Por qué hace falta | Alternativa más simple descartada porque |
|---|---|---|
| CLI mínima `python -m security_anomaly.storage` | La purga debe ejecutarla una persona con las credenciales del rol de mantenimiento (FR-002-20) | Sin CLI solo se podría llamar desde código |
| Perfiles `setup` y `maintenance` en Compose | La spec exige que migrar y purgar sean explícitos y que la API no tenga credenciales de DDL ni de borrado | Ejecutarlos al arrancar contradice la spec; hacerlos a mano duplica comandos |
| Variables de entorno de URL por rol | Cada operación solo debe conocer sus credenciales (FR-002-22) | Una única URL mezclaría privilegios |
