# ADR 0001 — Decisiones iniciales de alcance y diseño

- **Estado:** Aceptada
- **Fecha:** 2026-11-13

## Contexto
La propuesta original, `SPEC.md` y Spec Kit presentaban contradicciones y decisiones abiertas
(§19 de la spec). Se resuelven aquí antes de redactar las especificaciones de cada incremento.

## Decisiones

| # | Tema | Decisión |
|---|---|---|
| D1 | MVP | Ingesta, Isolation Forest, API REST y persistencia. **El dashboard queda fuera del MVP** (fase 2 del roadmap). |
| D2 | Estructura de specs | Carpetas de Spec Kit: `specs/NNN-nombre/{spec,plan,tasks}.md`. Sustituye a los archivos planos del §3.2 de la spec. |
| D3 | Orden de incrementos | 0 base · 1 ingesta · 2 persistencia · 3 features · 4 entrenamiento · 5 inferencia/API con autenticación y roles · 6 dashboard · 7 despliegue y E2E. |
| D4 | Formato de log | Primer adaptador: **Linux auth**. Windows Security Event: estudio de viabilidad a largo plazo (roadmap). |
| D5 | Eventos fuera de orden | Se aceptan y se puntúan con los eventos conocidos de timestamp menor o igual; no se recalculan agregados pasados; se marca contexto incompleto cuando proceda. |
| D6 | Errores parciales en batch | Se persisten los válidos, los duplicados se omiten y la respuesta lista los rechazados con índice y motivo. |
| D7 | Entrenamiento administrativo | La API crea un `training_run` y lanza un proceso aparte con concurrencia 1; el estado se consulta por GET. Sin Celery ni Redis. |
| D8 | Privacidad | `username` como HMAC con clave en entorno; la IP se conserva. Retención por defecto 90 días, configurable, con purga. |

## Resoluciones editoriales (se aplicarán al reescribir `SPEC.md`)
- `contamination` se elimina: con calibración por percentil no se usa.
- Se definirá la severidad por debajo del primer umbral y la relación entre `is_anomaly` y el umbral operativo.
- `/health` y `/ready` quedan fuera del prefijo `/api/v1` (sondas de infraestructura); se documenta.
- Nombre del repositorio: `detector-anomalies`; paquete Python `security_anomaly`.
- Autenticación por API key con roles `reader`/`admin` entra en el incremento 5.
- SQLite descartado; DBSCAN fuera del MVP (roadmap).

## Pendiente
Dataset y tamaño máximo del MVP para los benchmarks.
