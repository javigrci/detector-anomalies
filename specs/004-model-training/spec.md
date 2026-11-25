# Feature Specification: Entrenamiento del modelo

**Feature Branch**: `004-model-training` (se trabaja en `main`; la carpeta es independiente de la rama)

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Incremento 4 (004-model-training): entrenamiento, calibración, evaluación y versionado del modelo de detección, según SPEC §5 y §7, la constitución (Principios III y VII) y las decisiones D7 y D8. Entrada: eventos persistidos (incremento 2) y sus vectores de características versionados (incremento 3, con esquema y huella). Proceso: validar y cargar un dataset reproducible; ordenar por timestamp y separar temporalmente en entrenamiento, calibración y prueba; ajustar transformadores (numéricas y categóricas, categorías desconocidas toleradas, usuario e IP nunca codificados como ordinales) solo con entrenamiento; entrenar Isolation Forest con random_state=42 sin parámetro contamination; calibrar por percentil la distribución de raw_score = -score_samples(X) con el conjunto de calibración separado del test, de modo que anomaly_score sea un percentil en [0,1] y nunca una probabilidad de ataque; severidad low/medium/high con umbrales provisionales 0.80 y 0.95 configurables; evaluar (sin etiquetas: distribución de scores, estabilidad temporal, proporción de alertas; con etiquetas sintéticas: precision, recall, F1, PR-AUC y matriz de confusión; sin prometer precisión mínima) y documentar limitaciones; guardar cada modelo como artefacto versionado con versión, esquema de características (versión y huella), parámetros, fecha, métricas y hash del dataset, junto a registros de model_versions y training_runs en PostgreSQL mediante migración; activar manualmente una versión aprobada (autorización humana explícita, sin reentrenamiento ni activación automáticos); cargar artefactos solo desde ubicaciones internas de confianza, nunca desde archivos de usuarios; el entrenamiento corre como proceso aparte con concurrencia 1 y estado consultable (D7). Biblioteca reutilizable por la inferencia del incremento 5 con exactamente el mismo pipeline. Sin endpoints ni API (llegan en el incremento 5), sin puntuación por API, sin dashboard. Se necesita aprobar y registrar en un ADR la dependencia scikit-learn (y con ella numpy y joblib); ninguna otra sin aprobación. Puerta de aceptación del roadmap: modelo reproducible y evaluación documentada."

## Clarifications

### Session 2026-11-24

Sesión en modo automático: las preguntas se resolvieron con la opción recomendada por el asistente (indicación del usuario del 2026-11-24), y quedan aquí para su revisión.

- Q: ¿Cómo se reparten los datos en entrenamiento, calibración y prueba? → A: Por orden temporal estricto y en bloques contiguos: el 70 % más antiguo entrena, el 15 % siguiente calibra y el 15 % más reciente prueba; las fracciones son configurables y un empate de instante nunca parte un evento de otro con el mismo `timestamp`.
- Q: ¿Dónde se guarda el artefacto del modelo y cómo se protege su carga? → A: En un directorio interno de confianza configurado por el operador, con un archivo por versión; su huella SHA-256 se registra en `model_versions` y se verifica **antes** de cargarlo. Nunca se carga un archivo desde una ruta recibida de un usuario.
- Q: ¿Con qué credenciales de base de datos se registran entrenamientos y versiones? → A: Con el rol de aplicación existente, al que se le conceden permisos de lectura, inserción y actualización solo sobre las dos tablas nuevas (sin `DELETE` ni cambios en lo que puede hacer sobre `events`); no se crea un rol nuevo.
- Q: ¿Cómo lo ejecuta una persona sin API? → A: Con una línea de comandos mínima (`entrenar`, `estado`, `activar`); la concurrencia 1 la garantiza la base de datos y la activación exige una aprobación explícita en la propia orden.
- Q: ¿De dónde salen las etiquetas para evaluar? → A: Son opcionales y externas al modelo: un mapa `event_id → etiqueta` (por ejemplo, las etiquetas del generador sintético). Se usan solo para medir en el conjunto de prueba y nunca para entrenar ni calibrar.

## User Scenarios & Testing *(mandatory)*

Los "usuarios" de este incremento son el **administrador técnico** (entrena, evalúa y activa modelos) y el
**ingeniero de ML** (revisa métricas y limitaciones). Más adelante, la **inferencia** del incremento 5
reutilizará esta biblioteca para puntuar. Todavía no hay interfaz pública: la capacidad se entrega como lógica
reutilizable y una línea de comandos mínima. Se parte de los eventos que guarda el incremento 2 y de los
vectores de características del incremento 3.

### User Story 1 - Entrenar un modelo reproducible con datos históricos (Priority: P1)

El administrador entrena un modelo con un conjunto de eventos históricos. Los datos se ordenan en el tiempo y se
separan en entrenamiento, calibración y prueba; todo lo que se aprende (transformaciones y modelo) usa solo el
conjunto de entrenamiento. Repetir el entrenamiento con los mismos datos y parámetros da exactamente el mismo
modelo.

**Why this priority**: es el valor central del incremento y la puerta de aceptación del roadmap (modelo
reproducible). Un modelo que ve datos de calibración o prueba al ajustarse da métricas engañosas (Principio III).

**Independent Test**: entrenar dos veces con el mismo dataset sintético y comparar las puntuaciones de un
conjunto fijo; alterar los datos de calibración o de prueba y comprobar que el modelo entrenado no cambia.

**Acceptance Scenarios**:

1. **Given** un dataset ordenado en el tiempo, **When** se entrena, **Then** los tres conjuntos son bloques
   contiguos (entrenamiento el más antiguo, prueba el más reciente) y no se solapan.
2. **Given** el mismo dataset y los mismos parámetros, **When** se entrena dos veces, **Then** las puntuaciones
   del modelo coinciden exactamente.
3. **Given** un dataset, **When** se modifican, añaden o quitan eventos de los conjuntos de calibración o de
   prueba, **Then** las transformaciones y el modelo entrenado no cambian.
4. **Given** categorías que no estaban en el entrenamiento (por ejemplo, una fuente nueva), **When** se
   transforma un evento, **Then** no hay error y la categoría nueva no activa ninguna característica conocida.
5. **Given** un dataset demasiado pequeño para repartirlo, **When** se intenta entrenar, **Then** se rechaza con
   un error controlado que indica el mínimo necesario, sin entrenar nada.
6. **Given** vectores de características con una huella de esquema distinta de la esperada, **When** se intenta
   entrenar, **Then** se rechaza con un error controlado.

---

### User Story 2 - Puntuar de forma calibrada e interpretable (Priority: P1)

Un evento recibe una puntuación bruta (mayor valor = más anómalo) y una puntuación de anomalía en [0, 1] que es el
percentil de esa puntuación bruta frente a la distribución del conjunto de calibración, más una severidad
`low`, `medium` o `high` según umbrales configurables. La puntuación nunca se presenta como probabilidad de ataque.

**Why this priority**: es lo que consumirá el analista; sin calibración un número bruto no significa nada
comparable entre modelos (SPEC §5.3).

**Independent Test**: con un modelo entrenado y una distribución de calibración conocida, comprobar el percentil
de eventos con puntuaciones por debajo, dentro y por encima del rango de calibración y las severidades en los
bordes de los umbrales.

**Acceptance Scenarios**:

1. **Given** un modelo entrenado, **When** se puntúan eventos, **Then** la puntuación bruta es `-score_samples`
   (mayor valor, más anómalo) y la puntuación de anomalía está en [0, 1].
2. **Given** una puntuación bruta mayor que todas las de calibración, **When** se calibra, **Then** la puntuación
   de anomalía es 1; si es menor que todas, es 0.
3. **Given** puntuaciones de anomalía 0,79, 0,80, 0,94 y 0,95, **When** se asigna severidad con los umbrales por
   defecto, **Then** salen `low`, `medium`, `medium` y `high`.
4. **Given** umbrales configurados de otra forma, **When** se asigna severidad, **Then** se aplican los
   configurados y se rechazan los incoherentes (el de `high` no puede ser menor que el de `medium`, ni fuera de
   [0, 1]).
5. **Given** cualquier salida del sistema, **When** se revisa, **Then** la puntuación de anomalía no aparece
   nombrada ni documentada como probabilidad de ataque.
6. **Given** una puntuación de anomalía, **When** se compara con el umbral operativo (0,80 por defecto),
   **Then** `is_anomaly` es verdadero si la alcanza o la supera.

---

### User Story 3 - Evaluar el modelo y documentar sus límites (Priority: P1)

Tras entrenar, el administrador obtiene un informe con la distribución de puntuaciones, su estabilidad en el
tiempo y la proporción de alertas; si dispone de etiquetas, también precision, recall, F1, PR-AUC y matriz de
confusión sobre el conjunto de prueba. El informe incluye las limitaciones, y el sistema no promete una
precisión mínima.

**Why this priority**: sin evaluación no hay base para aprobar un modelo (Principio II); es la segunda mitad de la
puerta de aceptación del roadmap.

**Independent Test**: evaluar un modelo sobre un dataset sintético con ráfagas etiquetadas y sin etiquetas, y
comprobar que el informe contiene exactamente las medidas descritas y las limitaciones.

**Acceptance Scenarios**:

1. **Given** un modelo y un conjunto de prueba sin etiquetas, **When** se evalúa, **Then** el informe contiene la
   distribución de puntuaciones, su estabilidad temporal y la proporción de eventos por encima del umbral
   operativo, y no contiene métricas de clasificación.
2. **Given** etiquetas externas para el conjunto de prueba, **When** se evalúa, **Then** el informe añade
   precision, recall, F1, PR-AUC y la matriz de confusión.
3. **Given** un dataset sintético con ráfagas de fallos inyectadas, **When** se evalúa, **Then** los eventos de
   la ráfaga reciben una puntuación de anomalía media mayor que la del tráfico normal.
4. **Given** el informe, **When** se lee, **Then** incluye un apartado de limitaciones (datos sintéticos, no
   demuestra detección real, umbrales provisionales) y ninguna promesa de precisión mínima.
5. **Given** etiquetas, **When** se evalúa, **Then** solo se usan sobre el conjunto de prueba y no cambian el
   modelo ni la calibración.
6. **Given** un conjunto de prueba sin ningún evento etiquetado como anómalo, **When** se calculan las métricas,
   **Then** se informa de que no se pueden calcular, sin dividir por cero.

---

### User Story 4 - Versionar y registrar cada modelo (Priority: P2)

Cada modelo entrenado se guarda como un artefacto con una versión propia y queda registrado, junto con el
entrenamiento que lo produjo, con su esquema de características (versión y huella), parámetros, fecha, métricas
y la huella del dataset. Así cualquier modelo se puede auditar y reproducir.

**Why this priority**: trazabilidad (Principio VI y III); no hace falta para entrenar, pero sin ella un modelo no
se puede usar con garantías.

**Independent Test**: entrenar un modelo y comprobar que existen el artefacto, su versión y los registros con
todos los campos; entrenar de nuevo con los mismos datos y comprobar que la huella del dataset coincide.

**Acceptance Scenarios**:

1. **Given** un entrenamiento correcto, **When** termina, **Then** existen un registro de entrenamiento y un
   registro de versión de modelo con versión, esquema de características (versión y huella), parámetros, fecha,
   métricas, huella del dataset y huella del artefacto.
2. **Given** el mismo dataset, **When** se calcula su huella dos veces, **Then** coincide; con un solo evento
   distinto, cambia.
3. **Given** dos entrenamientos, **When** se registran, **Then** cada uno recibe una versión distinta y las
   versiones anteriores no se modifican.
4. **Given** un modelo registrado, **When** se inspecciona, **Then** su registro no contiene valores de eventos,
   IPs, usuarios ni hosts.
5. **Given** una migración nueva, **When** se aplica sobre la base de datos ya migrada y de nuevo, **Then** crea
   las tablas una vez y no falla al repetirse.
6. **Given** un fallo durante el entrenamiento, **When** termina, **Then** el registro del entrenamiento queda en
   estado de error, sin versión de modelo a medias ni artefacto huérfano.

---

### User Story 5 - Activar una versión solo con autorización humana (Priority: P2)

El administrador activa una versión de modelo concreta para que sea la que se use al puntuar. Solo hay una
versión activa a la vez, la activación exige una aprobación explícita y no existe ningún reentrenamiento ni
activación automáticos.

**Why this priority**: Principio VII (humano en el circuito); evita que un modelo sin revisar acabe en uso.

**Independent Test**: registrar dos versiones, activar una con y sin aprobación explícita y comprobar el estado.

**Acceptance Scenarios**:

1. **Given** una versión registrada, **When** se activa con aprobación explícita, **Then** pasa a ser la única
   versión activa y queda anotado cuándo.
2. **Given** otra versión ya activa, **When** se activa una nueva, **Then** la anterior deja de estar activa y
   nunca hay dos activas a la vez, ni siquiera con activaciones simultáneas.
3. **Given** una orden de activación sin aprobación explícita, **When** se ejecuta, **Then** se rechaza y no
   cambia nada.
4. **Given** una versión inexistente, o cuyo artefacto no pasa la verificación de integridad, **When** se
   intenta activar, **Then** se rechaza con un error controlado.
5. **Given** que termina un entrenamiento, **When** se registra el modelo, **Then** no queda activo: ningún
   entrenamiento activa su resultado por sí solo.
6. **Given** cualquier momento, **When** pasa el tiempo, **Then** no se entrena ni se activa nada de forma
   automática.

---

### User Story 6 - Entrenar como proceso aparte, uno a la vez, y consultar su estado (Priority: P2)

El entrenamiento se ejecuta como un proceso independiente que no bloquea al servicio. Solo puede haber un
entrenamiento en curso; mientras tanto se puede consultar su estado (en cola, en curso, terminado o con error).

**Why this priority**: decisión D7; entrenar es costoso y no debe interferir con el servicio ni solaparse.

**Independent Test**: lanzar un entrenamiento, intentar lanzar otro mientras corre y consultar el estado en cada
fase.

**Acceptance Scenarios**:

1. **Given** un entrenamiento lanzado, **When** se consulta su estado, **Then** indica la fase (en curso,
   terminado o error) y, al terminar, la versión resultante.
2. **Given** un entrenamiento en curso, **When** se lanza otro, **Then** se rechaza con un error controlado que
   indica que ya hay uno en curso, sin crear un segundo.
3. **Given** dos intentos simultáneos de lanzar un entrenamiento, **When** se resuelven, **Then** como máximo uno
   se ejecuta.
4. **Given** un entrenamiento interrumpido (el proceso muere), **When** se consulta, **Then** no queda marcado
   como en curso para siempre: se puede detectar y marcar como fallido para poder lanzar otro.
5. **Given** el servicio web, **When** hay un entrenamiento en curso, **Then** el servicio no se ve afectado (el
   entrenamiento es un proceso distinto).

---

### User Story 7 - Cargar modelos solo de ubicaciones de confianza y reutilizarlos para puntuar (Priority: P3)

La inferencia del incremento 5 cargará el modelo activo con la misma biblioteca y obtendrá exactamente el mismo
resultado que el entrenamiento para el mismo evento. Un artefacto solo se carga desde el directorio interno de
confianza y después de verificar su integridad.

**Why this priority**: seguridad (Principio IV, SPEC §7) y consistencia entre entrenamiento e inferencia
(Principio III); no bloquea entrenar, pero debe quedar fijado antes de que exista la API.

**Independent Test**: guardar y cargar un modelo, comparar las puntuaciones; manipular el artefacto o pedir una
ruta externa y comprobar que se rechaza antes de cargar nada.

**Acceptance Scenarios**:

1. **Given** un modelo guardado, **When** se carga y se puntúan los mismos eventos, **Then** las puntuaciones son
   idénticas a las del modelo recién entrenado.
2. **Given** un artefacto cuya huella no coincide con la registrada, **When** se intenta cargar, **Then** se
   rechaza con un error controlado sin ejecutarlo ni deserializarlo.
3. **Given** una ruta fuera del directorio de confianza, un enlace simbólico que escapa de él o un nombre con
   componentes de ruta, **When** se intenta cargar, **Then** se rechaza.
4. **Given** un modelo y vectores calculados con un esquema de características distinto del suyo, **When** se
   puntúa, **Then** se rechaza con un error controlado.
5. **Given** que no hay ninguna versión activa, **When** se pide el modelo activo, **Then** se informa de que no
   hay ninguno, con un error controlado.

---

### Edge Cases

- Dataset con menos eventos que el mínimo necesario para repartirse en tres conjuntos no vacíos.
- Muchos eventos con el mismo `timestamp` en la frontera entre dos conjuntos.
- Un conjunto de calibración con todas las puntuaciones iguales.
- Un conjunto de prueba sin eventos anómalos etiquetados, o con todos anómalos.
- Un dataset con una sola fuente o con una fuente nueva que no estaba en el entrenamiento.
- Eventos sin IP o sin usuario (ausentes a 0 con indicadores, según el incremento 3).
- Vectores con `context_complete` falso: se informa de cuántos hay en cada conjunto.
- Dos entrenamientos lanzados a la vez; un proceso de entrenamiento que muere a mitad.
- Un artefacto borrado o modificado del directorio de modelos; el directorio sin permisos o inexistente.
- Intentar activar una versión mientras otra activación está en curso.
- Parámetros inválidos (número de árboles menor que 1, fracciones que no suman 1, umbrales incoherentes).
- Reentrenar con los mismos datos tras un cambio de versión del esquema de características.
- Valores centinela (usuario, IP, host) en los datos de entrada: no deben aparecer en el artefacto, el registro ni
  los informes.

## Requirements *(mandatory)*

### Functional Requirements

**Dataset y separación temporal**

- **FR-004-01**: El sistema MUST construir el dataset de entrenamiento a partir de los vectores de
  características de un rango de eventos persistidos, con el esquema de características (versión y huella) que
  esperan los llamadores, y rechazar con un error controlado un dataset con otro esquema.
- **FR-004-02**: El sistema MUST ordenar el dataset por `(timestamp, source, event_id)` y separarlo en tres
  bloques contiguos: entrenamiento (el más antiguo, 70 % por defecto), calibración (15 %) y prueba (el más
  reciente, 15 %), con fracciones configurables. Los conjuntos MUST NOT solaparse y un evento nunca MUST caer en
  dos de ellos.
- **FR-004-03**: Los eventos con el mismo `timestamp` MUST quedar en el mismo conjunto; la frontera se desplaza al
  siguiente instante distinto.
- **FR-004-04**: El sistema MUST rechazar, con un error controlado que indique el mínimo, un dataset en el que
  alguno de los conjuntos quede por debajo del tamaño mínimo configurable.
- **FR-004-05**: El sistema MUST calcular una huella determinista del dataset (identidad y valores de sus
  vectores, en orden) y MUST NOT incluir identificadores personales en ningún registro derivado de ella.

**Entrenamiento**

- **FR-004-06**: Las transformaciones (numéricas y categóricas) MUST ajustarse únicamente con el conjunto de
  entrenamiento y tolerar categorías desconocidas sin error y sin activar ninguna característica conocida.
- **FR-004-07**: El sistema MUST NOT codificar usuario, IP, host ni identificador de evento como valores ordinales
  ni como categorías: su comportamiento solo entra por los agregados del incremento 3.
- **FR-004-08**: El modelo MUST ser un Isolation Forest entrenado con semilla fija 42, con el número de árboles y
  el tamaño de la muestra configurables, y MUST NOT usar el parámetro de contaminación.
- **FR-004-09**: Con los mismos datos, parámetros, esquema y versiones de dependencias fijadas por el archivo de
  bloqueo, dos entrenamientos MUST dar puntuaciones idénticas.
- **FR-004-10**: Modificar, añadir o quitar eventos de los conjuntos de calibración o de prueba MUST NOT cambiar
  las transformaciones ajustadas ni el modelo.

**Calibración y puntuación**

- **FR-004-11**: La puntuación bruta MUST ser `-score_samples(X)`: mayor valor implica mayor anomalía.
- **FR-004-12**: La puntuación de anomalía MUST ser el percentil de la puntuación bruta frente a la distribución
  de calibración (fracción de puntuaciones de calibración menores o iguales), en [0, 1], monótona con la bruta.
  Si es mayor que todas las de calibración vale 1; si es menor que todas, 0.
- **FR-004-13**: La calibración MUST ajustarse solo con el conjunto de calibración, separado del de entrenamiento
  y del de prueba.
- **FR-004-14**: La severidad MUST ser `low` por debajo de 0,80, `medium` desde 0,80 y por debajo de 0,95, y
  `high` desde 0,95; ambos umbrales MUST ser configurables y coherentes (0 < medium ≤ high ≤ 1).
- **FR-004-15**: `is_anomaly` MUST ser verdadero cuando la puntuación de anomalía alcanza el umbral operativo
  (0,80 por defecto, configurable).
- **FR-004-16**: La puntuación de anomalía MUST NOT presentarse, documentarse ni nombrarse como probabilidad de
  ataque en ninguna salida, informe ni documento (Principio II).

**Evaluación**

- **FR-004-17**: La evaluación MUST producir, sin etiquetas: la distribución de puntuaciones, su estabilidad en el
  tiempo y la proporción de alertas sobre el umbral operativo; y con etiquetas externas, además precision,
  recall, F1, PR-AUC y matriz de confusión, solo sobre el conjunto de prueba.
- **FR-004-18**: Las etiquetas MUST NOT usarse para entrenar ni calibrar. Cuando una métrica no pueda calcularse
  (sin positivos o sin negativos), MUST informarse sin dividir por cero.
- **FR-004-19**: El informe MUST incluir las limitaciones (datos sintéticos, umbrales provisionales, no demuestra
  detección real) y MUST NOT prometer una precisión mínima.
- **FR-004-20**: El informe MUST indicar cuántos vectores de cada conjunto tienen el contexto incompleto.

**Versionado y registro**

- **FR-004-21**: Cada entrenamiento correcto MUST guardar un artefacto versionado en el directorio interno de
  confianza y registrar, en la base de datos, una versión de modelo con: versión, esquema de características
  (versión y huella), parámetros, fecha, métricas, huella del dataset, huella del artefacto y el entrenamiento que
  la produjo.
- **FR-004-22**: Cada entrenamiento MUST dejar un registro de entrenamiento con su estado (en curso, terminado o
  error), fechas y, si procede, la versión producida o un código de error sin valores de datos.
- **FR-004-23**: Las versiones MUST ser únicas y nunca modificarse tras registrarse (salvo el indicador de
  activa); los registros MUST NOT contener valores de eventos, IPs, usuarios, hosts ni identificadores.
- **FR-004-24**: Las tablas de versiones y entrenamientos MUST crearse solo mediante una migración versionada,
  repetible sin error, con permisos mínimos para los roles existentes.
- **FR-004-25**: Un fallo durante el entrenamiento MUST dejar el registro en error y MUST NOT dejar ni una
  versión a medias ni un artefacto huérfano.

**Activación y operación**

- **FR-004-26**: La activación de una versión MUST exigir una aprobación explícita, MUST dejar una sola versión
  activa a la vez (incluso con activaciones simultáneas) y MUST NOT ocurrir nunca como efecto de un
  entrenamiento. No existe reentrenamiento ni activación automáticos (Principio VII).
- **FR-004-27**: El entrenamiento MUST ejecutarse en un proceso aparte, con concurrencia 1 garantizada por la base
  de datos, y su estado MUST poder consultarse; un entrenamiento interrumpido MUST poder detectarse y marcarse
  como fallido.
- **FR-004-28**: El sistema MUST ofrecer una línea de comandos mínima para entrenar, consultar el estado y
  activar, con una línea JSON de salida con recuentos y códigos, nunca valores de datos ni credenciales.

**Carga segura e inferencia**

- **FR-004-29**: Un artefacto MUST cargarse solo desde el directorio interno de confianza y solo después de
  verificar que su huella coincide con la registrada; MUST rechazarse una ruta fuera de ese directorio, un
  nombre con componentes de ruta o un enlace simbólico que escape de él. Nunca se deserializa un archivo
  recibido de un usuario.
- **FR-004-30**: Entrenamiento e inferencia MUST usar exactamente el mismo pipeline: puntuar un evento con el
  modelo cargado MUST dar el mismo resultado que con el modelo recién entrenado, y puntuar con un esquema de
  características distinto del del modelo MUST rechazarse con un error controlado.

**Seguridad y observabilidad**

- **FR-004-31**: Los errores MUST ser controlados y MUST NOT incluir valores de datos, rutas internas ni
  credenciales; el registro de actividad MUST contener solo recuentos, duraciones, versiones y códigos.
- **FR-004-32**: Este incremento MUST NOT introducir endpoints, autenticación con API key, puntuación por API ni
  dashboard, y MUST NOT añadir dependencias distintas de scikit-learn (con numpy y joblib) tras su ADR.

### Key Entities

- **Dataset de entrenamiento**: vectores de características ordenados, con su esquema y su huella.
- **Partición temporal**: los tres bloques contiguos (entrenamiento, calibración, prueba) con sus límites.
- **Modelo entrenado**: transformaciones ajustadas + Isolation Forest + distribución de calibración.
- **Puntuación**: puntuación bruta, puntuación de anomalía en [0, 1], severidad y bandera de anomalía.
- **Informe de evaluación**: medidas, proporción de alertas, contexto incompleto y limitaciones.
- **Versión de modelo**: registro de un artefacto, con su esquema, parámetros, métricas, huellas y estado activo.
- **Entrenamiento (training run)**: registro de una ejecución, con estado, fechas y resultado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Dos entrenamientos con el mismo dataset sintético y los mismos parámetros dan puntuaciones
  idénticas en el 100 % de los eventos de un conjunto fijo.
- **SC-002**: En el 100 % de los casos de una batería de datasets, alterar los conjuntos de calibración o de
  prueba no cambia las transformaciones ni el modelo: cero fugas hacia el entrenamiento.
- **SC-003**: En un dataset sintético con ráfagas de fallos inyectadas, la puntuación de anomalía media de los
  eventos de las ráfagas es mayor que la del tráfico normal, y la mayoría de los eventos de ráfaga supera el
  umbral operativo.
- **SC-004**: La evaluación produce el informe completo (con y sin etiquetas) para un dataset de 100.000 eventos
  en menos de 5 minutos, y el entrenamiento correspondiente termina en menos de 5 minutos, en una máquina de
  desarrollo convencional, registrando hardware, volumen y condiciones (orientativo).
- **SC-005**: Puntuar un evento individual con un modelo cargado tarda menos de 50 milisegundos en el percentil
  95 (parte del presupuesto de 500 ms de NFR-06), en una máquina de desarrollo convencional.
- **SC-006**: Un artefacto manipulado, un nombre con componentes de ruta o una ruta externa se rechazan en el
  100 % de los casos probados, antes de deserializar nada.
- **SC-007**: Con dos intentos simultáneos de entrenar, como máximo uno se ejecuta; con activaciones
  simultáneas, nunca hay más de una versión activa, en el 100 % de las pruebas.
- **SC-008**: 0 valores de usuario, IP, host o identificador de evento en artefactos, registros, informes,
  errores y registros de actividad, en el 100 % de los casos de prueba.
- **SC-009**: Ninguna salida, informe ni documento del incremento llama probabilidad de ataque a la puntuación de
  anomalía.

## Assumptions

- Los usuarios son el administrador técnico y el ingeniero de ML; la inferencia (incremento 5) reutiliza esta
  biblioteca. No hay interfaz pública ni API en este incremento.
- Los vectores de características los calcula el incremento 3 con su esquema v1; si cambia de versión o de huella,
  los modelos anteriores dejan de ser válidos para ese esquema.
- Las etiquetas para evaluar son opcionales y externas (por ejemplo, las del generador sintético del incremento 1);
  los datos de prueba son sintéticos y no demuestran capacidad real de detección (Principio II).
- Los hiperparámetros por defecto (por ejemplo, 100 árboles y tamaño de muestra automático) son razonables y se
  ajustan al medir; sus valores finales los fija el plan.
- Las transformaciones: las características numéricas pasan tal cual y las categóricas se codifican con tolerancia
  a categorías desconocidas; no hace falta escalar para un modelo de árboles.
- El directorio de modelos lo configura el operador por variable de entorno y es un lugar interno de confianza;
  se decide en el plan su nombre y sus permisos.
- Las tablas de versiones y entrenamientos usan el rol de aplicación existente con permisos de lectura, inserción
  y actualización solo sobre ellas; el rol de mantenimiento y el de migraciones no cambian.
- No se purgan modelos ni entrenamientos en este incremento (la retención de eventos del incremento 2 no los
  afecta).
- El entrenamiento y la activación los lanza una persona con una línea de comandos mínima; la API de los
  incrementos 5 hará lo mismo con autenticación de administrador. Ese componente y las variables de entorno
  nuevas se justifican en el plan (Complexity Tracking).
- La dependencia de scikit-learn, con numpy y joblib, se aprueba y registra en un ADR antes de usarla; ninguna
  otra se añade sin aprobación.
- Las metas de tiempo se miden en una máquina de desarrollo convencional y se registran con su hardware, volumen y
  condiciones.
- Dependencias: incremento 1 (eventos y etiquetas sintéticas), incremento 2 (eventos persistidos, roles de base de
  datos y migraciones) e incremento 3 (vectores de características, esquema y huella).
