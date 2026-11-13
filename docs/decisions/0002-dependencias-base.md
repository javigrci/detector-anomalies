# ADR 0002 — Dependencias y herramientas del incremento 0

- **Estado:** Aceptada
- **Fecha:** 2026-11-13
- **Contexto:** `specs/000-base` (research R1, R2, R4, R11). La constitución (Principio I) exige aprobar
  toda dependencia no listada en SPEC §2.

## Decisiones

| Elemento | Decisión | Motivo |
|---|---|---|
| Driver PostgreSQL | `psycopg` v3 (binario) | SQLAlchemy 2 necesita un driver; SPEC §2 fija PostgreSQL pero no lo nombra. Es el recomendado por SQLAlchemy 2. |
| Configuración | **No** usar `pydantic-settings`; carga propia sobre Pydantic v2 | El paquete no está en SPEC §2; la carga manual son pocas líneas y permite sanear los errores (no mostrar valores secretos). |
| Backend de construcción | `uv_build` (solo herramienta de construcción, no se instala en runtime) | Necesario para el layout `src/` con uv; mantiene todo dentro del ecosistema uv ya fijado. |
| Acciones de CI | `actions/checkout` y `astral-sh/setup-uv` | Acciones estándar para clonar y para instalar uv en GitHub Actions. Se fijan por versión. |

## Alternativas descartadas
- `pydantic-settings`, `python-dotenv`, `structlog`: dependencias adicionales sin necesidad.
- `asyncpg`/`psycopg2`: otro modelo de acceso o driver heredado.
- Backend `hatchling`/`setuptools`: añaden una herramienta ajena a uv.

## Consecuencias
Cualquier otra dependencia nueva requiere un ADR o una enmienda a este.
