# Roadmap

> Versión 1.0 · 2026-11-13 · Complementa a [SPEC.md](../SPEC.md) (§1.1 y §12) y al
> [ADR 0001](decisions/0001-decisiones-iniciales.md). Las fechas son estimaciones para una persona
> y no compromisos; cada fase se cierra por sus puertas de aceptación, no por calendario.

## Resumen

| Fase | Objetivo | Incrementos | Estimación |
|---|---|---|---|
| **MVP** | API que ingiere logs Linux auth, puntúa con Isolation Forest y guarda resultados | 0–5 y 7 | 8–10 semanas |
| **Fase 2** | Dashboard de investigación | 6 | 2–3 semanas |
| **Fase 3** | Calidad del modelo y feedback del analista | por especificar | por estimar |
| **Fase 4** | Integración y escala | por especificar | por estimar |
| **Largo plazo** | Estudio de nuevos formatos de log (Windows Security Event) | estudio | por estimar |

## MVP

**Resultado:** un sistema desplegable con `docker compose up --build` que ingiere eventos
sintéticos estilo Linux auth, entrena y activa un modelo, y devuelve puntuaciones y anomalías por
API, con autenticación por roles, tests y CI.

| Inc. | Spec | Contenido | Puerta de aceptación |
|---|---|---|---|
| 0 | `000-base` | Proyecto, `pyproject.toml` con uv, CI, Docker, configuración | Tests mínimos pasan y el servicio arranca |
| 1 | `001-ingestion` | Esquemas, parser JSON/CSV, normalización, adaptador Linux auth | Fixtures válidos e inválidos |
| 2 | `002-persistence` | PostgreSQL, migraciones, repositorios, seudonimización y retención | Integración con DB |
| 3 | `003-feature-engineering` | Features por evento y ventana de 5 min, causales | Tests sin fuga temporal |
| 4 | `004-model-training` | Entrenamiento, calibración, versiones, `training_runs` | Modelo reproducible y evaluación documentada |
| 5 | `005-inference-api` | Puntuación, consulta de anomalías, API key con roles | Tests de contrato y seguridad |
| 7 | `007-deployment` | Compose completo, runbook, model card y E2E | Demo completa desde cero |

El generador de datos sintéticos se construye de forma incremental: el esquema mínimo en el
incremento 1 y los perfiles de anomalías inyectadas antes del 4.

### Hitos del MVP

- **H1 — Ingesta funcionando** (fin de inc. 1–2): eventos válidos persistidos; inválidos rechazados con motivo.
- **H2 — Primer modelo** (fin de inc. 4): modelo versionado, evaluación y tasa de alertas medidas.
- **H3 — API completa** (fin de inc. 5): flujo ingesta → puntuación → consulta bajo autenticación.
- **H4 — MVP cerrado** (fin de inc. 7): E2E reproducible desde cero y documentación completa.

### Decisiones que se cierran dentro del MVP

- Hardware de referencia y volumen de los benchmarks (specs 004 y 007).
- Validación de los umbrales 0.80 y 0.95 con la tasa de alertas observada (spec 004).
- Patrones concretos de Linux auth soportados (spec 001).

## Fase 2 — Dashboard

**Spec:** `006-dashboard` · **Tecnología:** Streamlit.

- Resumen: eventos analizados, anomalías, proporción de alertas y evolución temporal.
- Listado paginado con filtros por fecha, fuente, tipo de evento, IP, usuario y severidad.
- Detalle del evento: datos normalizados, características, versión de modelo y contexto temporal.
- Pantalla de modelo: versión activa, fecha, configuración y métricas.
- **Puerta:** flujo de consulta verificable. El dashboard no presenta `anomaly_score` como probabilidad.

## Fase 3 — Calidad del modelo y feedback

Candidatas, por priorizar y especificar cada una antes de empezar:

- **Comparación de modelos:** DBSCAN y Local Outlier Factor frente a Isolation Forest, con la misma evaluación temporal.
- **Explicabilidad:** variables que más contribuyen a una puntuación, sin atribuir causalidad.
- **Feedback del analista:** registro de falsos positivos y eventos confirmados.
- **Dataset público:** evaluación con un dataset de autenticación con licencia y etiquetas revisadas.
- **Monitorización de drift:** seguimiento de la distribución de scores y de la tasa de alertas.
- **Reentrenamiento asistido:** propuesta de reentrenamiento que siempre requiere aprobación humana.

## Fase 4 — Integración y escala

Candidatas, sujetas a una nueva decisión de alcance y a una enmienda de la constitución cuando
afecten a sus límites (por ejemplo, el stack o los no objetivos):

- Ingesta en tiempo real con Redis Streams o Kafka.
- Exportación de alertas a SIEM (Wazuh, Elastic Security).
- Ingesta de más fuentes de log de aplicación.
- Alta disponibilidad y observabilidad ampliada.

## Largo plazo — Windows Security Event

**Tipo:** estudio de viabilidad, no compromiso de desarrollo.

- Valorar los eventos de autenticación 4624 y 4625 en JSON o CSV.
- Comparar su esquema con el contrato v1 y decidir si basta un adaptador o hay que ampliar el contrato.
- Evaluar si los agregados por ventana del modelo siguen siendo válidos con esa fuente.
- **Salida:** un ADR con la decisión y, si procede, una spec nueva.

## Fuera de alcance en todas las fases

Bloqueo automático de IPs o cuentas, respuesta automática a incidentes y uso de LLMs para decidir
si un evento es malicioso (constitución, Principios II y VII).

## Riesgos del plan

| Riesgo | Mitigación |
|---|---|
| El MVP crece por tentación de adelantar el dashboard | Fase 2 solo empieza con el H4 cerrado |
| Los datos sintéticos dan una falsa sensación de rendimiento | Documentar la limitación en el model card y evaluar con dataset público en fase 3 |
| Umbrales provisionales generan demasiadas alertas | Validarlos en el incremento 4 antes de fijar defaults |
| Estimaciones optimistas | Cerrar cada incremento por su puerta de aceptación y reestimar al final de cada uno |
