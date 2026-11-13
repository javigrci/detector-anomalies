# SPEC.md — Detector de anomalías en logs de auditoría de seguridad

> **Estado:** Especificación v1.1 (corrige v1.0 según [ADR 0001](docs/decisions/0001-decisiones-iniciales.md))
> **Metodología:** Spec-Driven Development (SDD) con Spec Kit
> **Autoridad:** `.specify/memory/constitution.md` > este documento > `specs/NNN-*/`
> **Producto:** Prototipo de apoyo al análisis de seguridad (SOC), no sustituto de un SIEM ni de la revisión humana.

## 1. Visión del producto

Sistema reproducible que ingiere logs de auditoría, los normaliza, genera características por evento y por ventana temporal, entrena un detector no supervisado basado en **Isolation Forest**, puntúa eventos y expone los resultados mediante una API REST. La detección identifica comportamientos inusuales, **no demuestra que exista un ataque**.

### 1.1 Alcance por fases

| Fase | Contenido |
|---|---|
| **MVP** | Ingesta JSON/CSV (adaptador Linux auth), persistencia, features, Isolation Forest, API REST con autenticación y roles, Docker Compose, tests y CI. |
| **Fase 2** | Dashboard Streamlit. |
| **Fase 3+** | DBSCAN/LOF para comparación, explicabilidad, feedback del analista, streaming, SIEM; estudio de viabilidad de Windows Security Event (largo plazo). Detalle en `docs/roadmap.md`. |

### 1.2 Objetivos del MVP

1. Ingerir y validar logs JSON y CSV de un esquema documentado.
2. Transformarlos en características reproducibles y causales.
3. Entrenar, versionar y evaluar un modelo Isolation Forest.
4. Puntuar eventos y producir un nivel de sospecha configurable.
5. Exponer ingesta, consulta, entrenamiento y puntuación en una API REST.
6. Guardar eventos, predicciones, modelos y metadatos para auditoría.
7. Entregar código probado, documentado y ejecutable con Docker Compose.

### 1.3 No objetivos

- Bloqueo automático de IPs, cuentas o conexiones.
- Detección garantizada de intrusiones o atribución de atacantes.
- Integración productiva con SIEM o EDR.
- Ingesta en streaming o alta disponibilidad.
- Reentrenamiento automático sin revisión.
- Entrenamiento con datos privados o secretos reales.
- Dashboard (fuera del MVP, fase 2).
- Uso de LLMs para decidir si un evento es malicioso: **los agentes de IA desarrollan el software; el motor de detección es ML clásico**.

### 1.4 Usuarios y casos de uso

- **Analista SOC:** consulta eventos sospechosos, puntuaciones y contexto (vía API en el MVP, vía dashboard en fase 2).
- **Administrador técnico:** carga datasets, entrena y activa modelos, revisa métricas.
- **Desarrollador:** prueba la API, reproduce experimentos y despliega el sistema.

Caso principal: un aumento de intentos fallidos de inicio de sesión desde una IP en una ventana de cinco minutos recibe una puntuación de anomalía alta y queda disponible para revisión humana.

## 2. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| API | FastAPI, Pydantic v2, Uvicorn |
| Procesamiento | pandas, NumPy |
| ML | scikit-learn (IsolationForest, ColumnTransformer) |
| Persistencia | PostgreSQL 16, SQLAlchemy 2, Alembic |
| Pruebas | pytest, httpx |
| Calidad | Ruff, mypy |
| Infraestructura | Docker, Docker Compose |
| CI | GitHub Actions |
| Dependencias | uv (`uv.lock`) |
| Dashboard (fase 2) | Streamlit |

SQLite descartado. Fuera del MVP: DBSCAN, Redis/Kafka, Wazuh/Elastic.

## 3. Arquitectura lógica

```mermaid
flowchart TD
    A[Archivos JSON/CSV] --> B[Ingesta y validación FastAPI]
    B --> C[Normalización]
    C --> G[(PostgreSQL)]
    G --> D[Extracción de características]
    D --> E[Pipeline Isolation Forest]
    E --> F[Score y severidad]
    F --> G
    G --> H[API de consulta]
    H --> J[Analista SOC]
    H -.fase 2.-> I[Dashboard Streamlit]
    K[Dataset de entrenamiento] --> D
    E --> L[Registro de versiones de modelo]
```

### 3.1 Componentes

- `ingestion`: lectura, validación, rechazo de registros inválidos, deduplicación y adaptador Linux auth.
- `normalization`: fechas a UTC, nombres de campos y categorías canónicas (dentro de `ingestion`).
- `features`: transformación determinista y agregaciones causales por ventana.
- `ml`: entrenamiento, serialización, carga, inferencia y evaluación.
- `scoring`: puntuación cruda → `anomaly_score` → severidad.
- `storage`: modelos SQLAlchemy, repositorios y migraciones.
- `api`: endpoints, autenticación, validación, errores y documentación.
- `core`: configuración, logging estructurado y utilidades.

### 3.2 Estructura de repositorio

```text
detector-anomalies/
├── AGENTS.md / CLAUDE.md
├── SPEC.md
├── README.md
├── pyproject.toml / uv.lock
├── .env.example / .gitignore
├── Dockerfile / compose.yaml
├── .github/workflows/ci.yml
├── .specify/                  # Spec Kit (constitución, plantillas, scripts)
├── docs/
│   ├── architecture.md · api.md · data-contract.md
│   ├── model-card.md · runbook.md · roadmap.md
│   └── decisions/             # ADRs
├── specs/
│   └── NNN-nombre/            # spec.md · plan.md · tasks.md (generados por Spec Kit)
├── src/security_anomaly/
│   ├── api/ · core/ · ingestion/ · features/
│   └── ml/ · scoring/ · storage/ · schemas/
├── dashboard/                 # fase 2
├── tests/ (unit/ · integration/ · fixtures/)
├── scripts/
└── data/synthetic/
```

Nunca se almacenan en Git modelos entrenados, credenciales ni datasets reales. Los artefactos de modelo viven en un volumen dedicado.

## 4. Contrato de datos

### 4.1 Evento de entrada (v1)

```json
{
  "event_id": "evt-000001",
  "timestamp": "2026-11-12T10:30:00Z",
  "source": "linux-auth",
  "event_type": "authentication",
  "action": "login",
  "outcome": "failure",
  "username": "demo-user",
  "source_ip": "192.0.2.45",
  "host": "srv-demo-01"
}
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `event_id` | string | Sí | Único por fuente |
| `timestamp` | ISO 8601 | Sí | Con zona horaria; se normaliza a UTC |
| `source` | string | Sí | Origen del log |
| `event_type` | string | Sí | Categoría de evento |
| `action` | string | Sí | Acción observada |
| `outcome` | enum | Sí | `success`, `failure`, `unknown` |
| `username` | string/null | No | Se almacena seudonimizado (HMAC) |
| `source_ip` | IPv4/IPv6/null | No | Validación de formato |
| `host` | string/null | No | Identificador del sistema |

Los campos no definidos se rechazan o se conservan en `metadata` bajo política explícita, y nunca entran al vector de características.

### 4.2 Adaptador Linux auth

El primer adaptador convierte entradas de `auth.log`/journald (SSH y sudo: login correcto, login fallido, usuario inválido, `sudo`) al evento v1. El detalle de patrones y eventos soportados se define en `specs/001-ingestion/`. Otros formatos (Windows Security Event) quedan para el roadmap.

### 4.3 Política de calidad y límites

- Rechazar timestamps inválidos y registros sin campos obligatorios.
- Registrar el motivo del rechazo sin exponer datos sensibles.
- Deduplicar por `(source, event_id)`.
- Tratar los valores ausentes de forma determinista.
- Acotar la cardinalidad de categorías (categorías desconocidas → `other`).
- Límites configurables (valores iniciales): archivo 10 MB, 10.000 eventos por lote, 100.000 eventos por dataset de MVP, 256 caracteres por campo de texto.

### 4.4 Eventos fuera de orden y contexto incompleto

- Los eventos fuera de orden se aceptan y persisten.
- Se puntúan con los eventos conocidos de timestamp menor o igual al suyo; los agregados de ventanas pasadas **no se recalculan**.
- Si el contexto histórico es insuficiente, la predicción se marca con `context_complete = false`.

### 4.5 Características del modelo

**Por evento:** hora UTC (representación cíclica), día de la semana, tipo de evento, acción, resultado y fuente.

**Por ventana de 5 minutos:** eventos por IP, fallos por IP, tasa de fallos por IP, usuarios distintos por IP e IPs distintas por usuario, cuando existan los campos.

Las agregadas se calculan **solo con eventos conocidos hasta el instante del evento puntuado**, con orden temporal definido y sin fuga de información futura. Entrenamiento e inferencia usan exactamente el mismo pipeline versionado.

## 5. Motor de Machine Learning

### 5.1 Algoritmo

- `IsolationForest` de scikit-learn con `random_state=42`.
- `n_estimators` y `max_samples` configurables. No se usa `contamination`: la calibración por percentil lo sustituye.
- `ColumnTransformer` para variables numéricas y categóricas; categorías desconocidas toleradas.
- Usuario e IP no se codifican como ordinales arbitrarios; su comportamiento se representa con agregados.

### 5.2 Entrenamiento

1. Validar y cargar un dataset reproducible.
2. Ordenar por timestamp y separar temporalmente en entrenamiento, calibración y prueba.
3. Ajustar transformadores solo con el conjunto de entrenamiento.
4. Entrenar el Isolation Forest.
5. Calibrar la distribución de `raw_score` con el conjunto de calibración, separado del test.
6. Evaluar y documentar limitaciones.
7. Guardar artefacto, versión, esquema de features, parámetros, fecha, métricas y hash del dataset.
8. Activar manualmente la versión aprobada.

### 5.3 Puntuación y severidad

- `raw_score = -model.score_samples(X)`: mayor valor implica mayor anomalía.
- `anomaly_score`: percentil de `raw_score` frente a la distribución de calibración guardada, en [0, 1]. **No es probabilidad de ataque.**
- `severity` (umbrales provisionales, configurables y por validar):

| `anomaly_score` | `severity` |
|---|---|
| < 0.80 | `low` |
| ≥ 0.80 y < 0.95 | `medium` |
| ≥ 0.95 | `high` |

- `is_anomaly`: verdadero si `anomaly_score` ≥ umbral operativo (por defecto 0.80, configurable); es decir, por defecto `medium` y `high`.
- Con calibración por percentil, un umbral de 0.95 implica ≈5 % de eventos `high` sobre datos como los de calibración. La tasa real de alertas debe medirse y ajustarse.
- La respuesta incluye `model_version`, `scored_at` y `context_complete`. No se atribuyen explicaciones causales: se muestran las características observadas y su desviación respecto al histórico.

### 5.4 Evaluación

Con etiquetas fiables: precision, recall, F1, PR-AUC y matriz de confusión. Sin etiquetas: distribución de scores, estabilidad temporal, proporción de alertas y revisión manual de muestras. Medir también latencia de inferencia y rendimiento de ingesta.

**Criterio clave:** no prometer una precisión mínima sin un dataset etiquetado y una definición de evaluación válida.

## 6. API REST v1

Rutas de negocio bajo `/api/v1`; `/health` y `/ready` quedan fuera del prefijo (sondas de infraestructura). Respuestas JSON; documentación en `/docs` y `/openapi.json`.

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| `GET` | `/health` | público | Estado del proceso |
| `GET` | `/ready` | público | Disponibilidad de DB y modelo activo |
| `POST` | `/api/v1/events` | admin | Ingesta de un evento |
| `POST` | `/api/v1/events/batch` | admin | Ingesta por lotes |
| `POST` | `/api/v1/score` | reader | Puntuación de un evento válido |
| `GET` | `/api/v1/events` | reader | Lista paginada con filtros |
| `GET` | `/api/v1/anomalies` | reader | Anomalías por severidad y fecha |
| `GET` | `/api/v1/anomalies/{event_id}` | reader | Detalle de anomalía |
| `GET` | `/api/v1/models/active` | reader | Metadatos del modelo activo |
| `POST` | `/api/v1/models/train` | admin | Lanza un entrenamiento |
| `GET` | `/api/v1/models/train/{run_id}` | admin | Estado de un entrenamiento |
| `POST` | `/api/v1/models/{version}/activate` | admin | Activación de una versión |

`admin` incluye los permisos de `reader`. La autenticación es por API key (entra en el incremento 5).

### 6.1 Ejemplo de puntuación

`POST /api/v1/score` recibe un evento con el esquema de §4.1. Respuesta ilustrativa:

```json
{
  "event_id": "evt-000001",
  "model_version": "iforest-v1",
  "raw_score": 0.71,
  "anomaly_score": 0.97,
  "is_anomaly": true,
  "severity": "high",
  "context_complete": true,
  "scored_at": "2026-11-12T10:30:02Z"
}
```

Los valores son ficticios y no representan una predicción real.

### 6.2 Semántica y errores

- `201` creación, `200` consulta/puntuación, `202` entrenamiento iniciado, `400/422` entrada inválida, `401/403` acceso no autorizado, `409` conflicto de duplicado o modelo, `413` payload excesivo, `503` modelo no disponible.
- Formato de error: `code`, `message`, `request_id`, `details` seguros.
- Listados con `limit`, `offset`, `total` y filtros validados.
- **Ingesta idempotente** por `(source, event_id)`: un duplicado se omite sin error en batch y devuelve `409` en el endpoint unitario.
- **Batch parcial:** se persisten los válidos, los duplicados se omiten y la respuesta lista los rechazados con índice y motivo.
- **Entrenamiento:** la API crea un `training_run` y lanza un proceso aparte con concurrencia 1; no bloquea el event loop. El estado se consulta por GET.
- **Puntuación:** usa contexto histórico persistido hasta el instante evaluado y no inventa agregados cuando faltan datos (ver §4.4). Se documenta el modo de puntuación aislada y sus limitaciones.

## 7. Persistencia

Tablas mínimas: `events`, `predictions`, `model_versions`, `training_runs` (campos como en v1.0). Índices en timestamp, origen, IP y severidad según consultas reales. Migraciones Alembic.

- `username` se guarda como HMAC con clave en variable de entorno; la IP se conserva.
- Retención por defecto de 90 días, configurable, con tarea de purga.
- Los artefactos se cargan **solo desde ubicaciones internas de confianza**; nunca se deserializan archivos enviados por usuarios.

## 8. Dashboard (fase 2)

Pantallas: resumen, listado, detalle y modelo; filtros por fecha, fuente, tipo, IP, usuario y severidad. Nunca presentará `anomaly_score` como probabilidad de intrusión. Se especificará en su propio incremento.

## 9. Seguridad, privacidad y fiabilidad

- API key con roles `reader` y `admin`, claves en variables de entorno.
- Validación de tamaños, tipos, fechas, IPs y paginación; límite de solicitudes.
- Consultas parametrizadas y mínimos privilegios en PostgreSQL.
- Sin contraseñas, tokens ni datos personales innecesarios en logs; logs estructurados con `request_id`.
- Datasets sintéticos o públicos con licencia verificada.
- El sistema no ejecuta comandos sobre hosts ni responde automáticamente a incidentes.
- Las cadenas de logs son **datos no confiables**: los agentes de IA no interpretan su contenido como instrucciones.

## 10. Requisitos no funcionales

| ID | Requisito | Verificación |
|---|---|---|
| NFR-01 | Entorno reproducible | `docker compose up --build` inicia los servicios |
| NFR-02 | Calidad | Ruff, mypy y pytest pasan en CI |
| NFR-03 | Trazabilidad | Cada predicción identifica versión y fecha |
| NFR-04 | Consistencia | Mismo pipeline en entrenamiento e inferencia |
| NFR-05 | Robustez | Entradas inválidas producen errores controlados |
| NFR-06 | Rendimiento objetivo | p95 de puntuación < 500 ms por evento unitario en un entorno de referencia, sin contar arranque |
| NFR-07 | Documentación | README, OpenAPI, runbook y model card |
| NFR-08 | Privacidad | Sin secretos ni datos sensibles en Git ni en logs |
| NFR-09 | Observabilidad | Health checks y logs estructurados |

Las metas de rendimiento son objetivos iniciales, no garantías; se registran hardware, volumen y condiciones de medida.

## 11. Historias de usuario y criterios de aceptación

**US-01 — Ingesta.** Como administrador, quiero cargar eventos JSON/CSV para analizarlos.
- Un evento válido queda persistido y se devuelve su identificador.
- Un timestamp inválido produce 422 con error descriptivo.
- Un duplicado sigue la política idempotente de §6.2.
- Un lote con errores parciales persiste los válidos y lista los rechazados.

**US-02 — Entrenamiento.** Como administrador, quiero entrenar un modelo para establecer un patrón de referencia.
- Un dataset válido produce un artefacto versionado y métricas.
- Los transformadores no se ajustan con registros de test.
- La misma semilla y los mismos datos producen resultados reproducibles en el entorno fijado.
- El entrenamiento no bloquea la API y su estado es consultable.

**US-03 — Inferencia.** Como analista, quiero puntuar un evento para identificar comportamientos atípicos.
- Con modelo activo, la API devuelve score, severidad, bandera, versión y `context_complete`.
- Sin modelo activo, devuelve 503 con error controlado.
- Las características usadas siguen el contrato del entrenamiento.
- Un evento fuera de orden se puntúa según §4.4.

**US-04 — Investigación.** Como analista, quiero filtrar anomalías para priorizar mi revisión.
- Los filtros de fecha, severidad y fuente funcionan y son combinables.
- La paginación es estable y sin duplicados.
- El detalle muestra los datos y el modelo asociados a la predicción.

**US-05 — Operación.** Como desarrollador, quiero desplegar el sistema de forma reproducible para probarlo localmente.
- Los servicios se levantan con Compose y las migraciones se ejecutan correctamente.
- Una prueba end-to-end ingiere eventos sintéticos, entrena y activa un modelo y consulta una predicción.

**US-06 — Acceso.** Como administrador, quiero separar permisos de consulta y de administración.
- Sin API key válida, 401; con rol `reader` sobre un endpoint `admin`, 403.

## 12. Plan SDD por incrementos

| Inc. | Spec (carpeta en `specs/`) | Entregable | Puerta de aceptación |
|---|---|---|---|
| 0 | `000-base` | Proyecto, CI, Docker, configuración | Tests mínimos y arranque |
| 1 | `001-ingestion` | Esquemas, parser, normalización, adaptador Linux auth | Fixtures válidos e inválidos |
| 2 | `002-persistence` | PostgreSQL, migraciones, repositorios, seudonimización | Integración con DB |
| 3 | `003-feature-engineering` | Features y ventanas temporales | Tests sin fuga temporal |
| 4 | `004-model-training` | Entrenamiento, calibración, versiones, training runs | Modelo reproducible y evaluación |
| 5 | `005-inference-api` | API de puntuación y consulta, autenticación y roles | Tests de contrato y seguridad |
| 6 | `006-dashboard` | Dashboard Streamlit (fase 2) | Flujo de consulta verificable |
| 7 | `007-deployment` | Compose completo, documentación y E2E | Demo completa desde cero |

El **MVP** se completa tras los incrementos 0–5 y el despliegue/E2E del 7; el dashboard (6) es fase 2. Las carpetas las numera Spec Kit al crear cada feature. Estimación: 8–10 semanas para una persona, ajustable. No se inicia un incremento sin aceptar su especificación.

### 12.1 Ciclo obligatorio por incremento

Specify → Clarify → Plan → Tasks → Implement → Verify → Review → Commit, con una tarea cada vez y sin ampliar el alcance. Se corresponde con `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement` y `/speckit-analyze`.

## 13. Roles de agentes

| Rol | Responsabilidad | Límite |
|---|---|---|
| Especificador | Convertir requisitos en specs verificables | No codifica sin aprobación |
| Arquitecto | Diseño, contratos y ADRs | No cambia el alcance unilateralmente |
| Backend | API, persistencia y validaciones | Respeta contratos aprobados |
| ML | Features, entrenamiento y evaluación | Previene fugas y métricas engañosas |
| QA/Seguridad | Tests, revisión y amenazas | No marca tests como ejecutados sin evidencia |
| Integrador | CI, Docker, documentación y E2E | No despliega a producción sin autorización |

Las reglas operativas están en `AGENTS.md`. Con agentes paralelos, cada uno trabaja en módulos distintos y se exige revisión de integración antes de fusionar.

## 14. Estrategia de pruebas

- **Unitarias:** parseo, normalización, ventanas, scoring, umbrales, serialización.
- **Integración:** API + DB, migraciones, artefactos de modelo, permisos.
- **Contratos:** Pydantic/OpenAPI, errores, paginación, idempotencia.
- **ML:** sin leakage, split temporal, determinismo, categorías desconocidas, ausencia de modelo.
- **Seguridad:** payload excesivo, acceso no autorizado, entradas malformadas, secretos en logs.
- **E2E:** dataset sintético → ingesta → entrenamiento → activación → puntuación → consulta.

Fixtures mínimos: actividad normal, ráfaga de fallos, horario atípico, IP ausente, timestamp inválido, duplicados, eventos fuera de orden y categorías nuevas. Los escenarios sintéticos validan el software, **no demuestran capacidad real de detección**.

## 15. Dataset y validación experimental

Primera fase: generador propio de eventos sintéticos reproducibles estilo Linux auth, con perfiles normales y anomalías inyectadas (tamaño máximo del MVP: 100.000 eventos). Segunda fase opcional: dataset público con licencia, esquema, representatividad y etiquetas revisadas. Se documentan procedencia, volumen, periodo, sesgos y transformaciones.

Separación temporal de los datos. Se registra la tasa de alertas por día y por 1.000 eventos y se revisan casos representativos. Las etiquetas sintéticas no son la única evidencia de rendimiento real.

## 16. Definition of Done

- [ ] Especificación aprobada con criterios verificables.
- [ ] Código conforme a contratos y arquitectura.
- [ ] Pruebas positivas, negativas y de borde.
- [ ] pytest, Ruff y mypy en verde, o bloqueo documentado sin declararla terminada.
- [ ] Sin secretos, datos sensibles ni riesgos críticos conocidos.
- [ ] Documentación y decisiones actualizadas.
- [ ] Resultados de pruebas registrados.
- [ ] Criterios de aceptación revisados uno a uno.

## 17. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Falsos positivos elevados | Umbrales calibrados, contexto y revisión humana |
| Fuga de datos futuros | Agregaciones causales y tests temporales |
| Datos insuficientes | Dataset sintético y evaluación honesta |
| Drift del comportamiento | Monitorizar scores y revisión manual del reentrenamiento |
| Entrenamiento e inferencia inconsistentes | Pipeline único y artefactos versionados |
| Datos sensibles en logs | Minimización, seudonimización y retención |
| Código fuera de alcance | SDD, revisión de diffs y gates de aceptación |
| Modelos serializados no confiables | Cargar solo artefactos internos verificados |
| Contexto incompleto por eventos fuera de orden | Marcar `context_complete` y medir su frecuencia |

## 18. Entregables del MVP

1. Repositorio con código y dependencias fijadas.
2. Constitución, `SPEC.md`, `AGENTS.md` y specs de cada incremento.
3. API REST documentada con OpenAPI.
4. Pipeline de preparación, entrenamiento, evaluación y puntuación.
5. Persistencia y migraciones.
6. Tests automatizados y CI.
7. Despliegue local con Docker Compose.
8. Dataset sintético y demostración reproducible.
9. README, runbook y model card con limitaciones.

## 19. Decisiones

Registradas en [ADR 0001](docs/decisions/0001-decisiones-iniciales.md). Pendiente: valores finales de benchmarks (hardware de referencia y volumen), a fijar en `specs/004-model-training/` y `specs/007-deployment/`.
