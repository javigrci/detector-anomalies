# ADR 0006 — Confianza de los artefactos, calibración y concurrencia del entrenamiento

- **Estado:** Aceptada
- **Fecha:** 2026-11-24
- **Contexto:** `specs/004-model-training` (research R3, R6, R8, R9, R11, R12; FR-004-21, 26, 27, 29). El
  incremento 4 guarda modelos serializados, los registra y los activa. Esas decisiones afectan a la seguridad
  (Principio IV), a la integridad del ML (III) y al control humano (VII), y la constitución exige registrarlas
  antes de implementar. Las cinco decisiones de la clarificación se tomaron en modo automático con la opción
  recomendada por el asistente (indicación del usuario del 2026-11-24) y se recogen aquí para su revisión.

## Decisiones

| Tema | Decisión | Motivo |
|---|---|---|
| Separación de datos | Tres bloques contiguos por orden temporal: 70 % entrenamiento, 15 % calibración, 15 % prueba, configurables; los eventos con el mismo `timestamp` quedan juntos (la frontera se desplaza al siguiente instante). | SPEC §5.2 exige separación temporal; partir un instante entre conjuntos haría depender un conjunto de otro. |
| Calibración | Percentil empírico: fracción de puntuaciones de calibración menores o iguales a la bruta, en [0, 1]; la bruta es `-score_samples`. Nunca se presenta como probabilidad. | SPEC §5.3; no depende de la forma de la distribución. |
| Dónde viven los artefactos | Un archivo por versión (`model-<version>.joblib`) en un directorio interno de confianza (`MODEL_DIR`); el nombre se deriva de la versión registrada, nunca de la entrada del usuario. | SPEC §7: artefactos solo de ubicaciones internas de confianza. |
| Confianza al cargar | La huella SHA-256 del archivo se registra en `model_versions` y se **verifica antes** de abrirlo (`joblib` usa `pickle`); además se valida la ruta real (dentro de `MODEL_DIR`, archivo regular, sin enlaces que escapen) y que las versiones de scikit-learn, numpy y scipy coinciden con las registradas. | Convierte el riesgo de ejecución de código por deserialización en un riesgo de integridad que la base de datos detecta. |
| Credenciales de BD | Se reutiliza el rol `anomaly_app`; se le conceden `SELECT`, `INSERT` y `UPDATE` **solo por columna** sobre `training_runs` y `model_versions` (sin `DELETE`). | Mínimos privilegios sin un rol nuevo; la inmutabilidad de versiones pasa a ser una garantía de la base de datos. |
| Concurrencia 1 | Índice único parcial: a lo sumo un entrenamiento `running`; latido y marcado de los caducados como `failed`. | D7 sin Celery ni Redis; sobrevive a un proceso muerto. |
| Una sola versión activa | Índice único parcial sobre `active` y un candado de asesoramiento al activar. | Evita dos versiones activas con activaciones simultáneas. |
| Activación | Solo con aprobación explícita; ningún entrenamiento activa su resultado; no hay reentrenamiento ni activación automáticos. | Principio VII. |
| Operación sin API | CLI mínima `python -m security_anomaly.ml` (`train`, `status`, `list`, `activate --approve`). | La API llega en el incremento 5; la persona necesita una forma de lanzarlo. |
| Etiquetas de evaluación | Opcionales y externas (`event_id → etiqueta`); solo se usan sobre el conjunto de prueba. | Las etiquetas nunca deben influir en el ajuste ni en la calibración. |

## Alternativas descartadas

- Partición aleatoria (fuga temporal); fronteras por índice exacto (parten empates).
- Cargar sin verificar la huella o aceptar rutas recibidas (ejecución de código arbitrario).
- Un rol de BD nuevo para entrenar (más aprovisionamiento sin ganancia clara); permiso de tabla completo (permitiría
  editar métricas o huellas).
- Un candado de archivo para la concurrencia (no sirve entre contenedores) o una cola de trabajos (no aprobada).

## Consecuencias

- Cambiar cualquiera de estas decisiones exige un nuevo ADR; cambiar la separación, la calibración o el esquema
  invalida los modelos registrados.
- El incremento 5 consumirá `load_active_model` y no podrá cargar nada fuera de `MODEL_DIR`.
- La CLI y las variables de entorno nuevas se señalan para la revisión del usuario (modo automático).
