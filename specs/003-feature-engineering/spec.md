# Feature Specification: Ingeniería de características

**Feature Branch**: `003-feature-engineering` (se trabaja en `main`; la carpeta es independiente de la rama)

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Incremento 3 (003-feature-engineering): características causales por evento y por ventana temporal de 5 minutos, sin fuga de futuro, según SPEC §4.4 y §4.5 y la constitución (Principio III). Entrada: eventos persistidos que se leen con read_range [desde, hasta) del incremento 2. Salida: vectores de características deterministas y reproducibles con esquema versionado. Por evento: características derivadas de sus campos (hora, acción, resultado, etc., según SPEC §4.5). Por ventana de 5 minutos: eventos por IP, fallos por IP, tasa de fallos por IP, usuarios distintos por IP e IPs distintas por usuario, cuando existan los campos. Los eventos fuera de orden se puntúan con lo conocido hasta su timestamp (decisión D5) y los agregados de ventanas pasadas no se recalculan. Biblioteca reutilizable por entrenamiento (incremento 4) e inferencia (incremento 5) con el mismo pipeline; sin endpoints, sin entrenamiento ni modelos, sin dependencias nuevas sin aprobación. Puerta de aceptación del roadmap: tests sin fuga temporal."

## Clarifications

### Session 2026-11-22

- Q: ¿Qué eventos cuentan como "conocidos" cuando dos tienen el mismo `timestamp`? → A: Orden total: la historia de un evento incluye solo los eventos que lo preceden en `(timestamp, source, event_id)` más él mismo; los empatados que van después en ese orden no cuentan. Es más estricto que "menor o igual" de SPEC §4.4 y garantiza que entrenamiento e inferencia ven lo mismo.
- Q: ¿Cómo se define la "ventana de 5 minutos"? → A: Deslizante y anclada en el evento puntuado: cuentan los eventos con `timestamp` posterior a "instante − 5 min" y hasta el propio evento (con el orden total de la respuesta anterior); no se usan cubos fijos alineados.
- Q: ¿Cómo se decide que el contexto de un evento está "completo"? → A: Lo declara quien llama (inicio de la historia disponible): el contexto es completo si "instante − 5 min" no es anterior a ese inicio, e incompleto en caso contrario; no se deduce de los datos de entrada.
- Q: ¿Qué valor toman las características cuando el evento no tiene IP o no tiene usuario? → A: Las agregadas que dependen de la entidad ausente valen 0 y el vector incluye los indicadores `has_ip` y `has_user`; la forma del vector no cambia y no se descartan eventos.
- Q: ¿Sobre qué conjunto de eventos se agrega una IP o un usuario? → A: Por fuente y sumando todos los hosts de esa fuente: las agregadas se calculan por `(source, IP)` y `(source, usuario)`; una misma IP en dos fuentes distintas cuenta por separado y `host` no forma parte de la clave. Cruzar fuentes exigiría un cambio de esquema.

## User Scenarios & Testing *(mandatory)*

Los "usuarios" de este incremento son el **ingeniero de ML** (que en el incremento 4 entrenará el
modelo con estas características) y el **analista** (que en el incremento 5 pedirá la puntuación de un
evento y necesita que se calcule exactamente igual que en el entrenamiento). Todavía no hay interfaz
pública: la capacidad se entrega como lógica reutilizable. Se parte de los eventos que guarda el
incremento 2 y que se leen por rango temporal.

### User Story 1 - Resumir la actividad reciente de cada IP y usuario sin ver el futuro (Priority: P1)

Para cada evento, el ingeniero de ML obtiene un resumen de lo ocurrido en los cinco minutos
anteriores a ese evento: cuántos eventos y cuántos fallos hubo desde la misma IP, qué proporción fueron
fallos, cuántos usuarios distintos probó esa IP y cuántas IPs distintas usó ese usuario. El resumen se
calcula **solo con lo que ya se conocía en ese instante**: nada posterior al evento influye en él.

**Why this priority**: es el valor central del incremento y la señal que usará el modelo para el caso
principal de SPEC §2 (un aumento de intentos fallidos desde una IP en cinco minutos). Es además el punto
más delicado: una fuga de futuro invalida todas las métricas del modelo (Principio III de la
constitución, NON-NEGOTIABLE).

**Independent Test**: construir un flujo de eventos con una ráfaga de fallos desde una IP, calcular las
características y comprobar que (a) suben a lo largo de la ráfaga y (b) no cambian si se añaden, quitan o
modifican eventos posteriores a cada evento.

**Acceptance Scenarios**:

1. **Given** una IP que genera varios intentos fallidos seguidos en menos de cinco minutos, **When** se
   calculan las características, **Then** cada evento sucesivo refleja un recuento de eventos y de fallos
   mayor que el anterior, y una tasa de fallos coherente con ellos.
2. **Given** un flujo de eventos, **When** se añaden, eliminan o modifican eventos posteriores al instante
   de un evento concreto, **Then** las características de ese evento y de todos los anteriores a ese
   instante no cambian.
3. **Given** un evento y otro de la misma IP ocurrido hace más de cinco minutos, **When** se calculan las
   características del primero, **Then** el evento antiguo no cuenta en su ventana.
4. **Given** una IP que prueba varios usuarios distintos, **When** se calculan las características,
   **Then** el número de usuarios distintos de esa IP en la ventana es el de seudónimos diferentes
   observados, sin contar dos veces al mismo.
5. **Given** un usuario que se conecta desde varias IPs, **When** se calculan las características,
   **Then** el número de IPs distintas de ese usuario en la ventana es el de IPs diferentes observadas.
6. **Given** dos eventos de la misma IP con el mismo `timestamp`, **When** se calculan las
   características, **Then** el que va después en `(timestamp, source, event_id)` cuenta al otro en su
   historia y el que va antes no cuenta al posterior, con el mismo resultado en cualquier ejecución.

---

### User Story 2 - Describir cada evento por sí mismo (Priority: P1)

Para cada evento, el ingeniero de ML obtiene las características que dependen solo de ese evento: la
hora del día en UTC (en una representación en la que las 23:59 y las 00:00 quedan próximas), el día de la
semana, el tipo de evento, la acción, el resultado y la fuente.

**Why this priority**: son las características básicas de SPEC §4.5 y no requieren historia; sin ellas el
vector está incompleto.

**Independent Test**: calcular las características de eventos con horas, días y categorías conocidas y
comparar con los valores esperados.

**Acceptance Scenarios**:

1. **Given** eventos a las 23:59 y a las 00:01 UTC, **When** se calculan las características, **Then** su
   representación cíclica de la hora es casi idéntica y la de las 12:00 queda opuesta a la de las 00:00.
2. **Given** un evento con `timestamp` en una zona horaria distinta de UTC, **When** se calculan las
   características, **Then** la hora y el día de la semana se obtienen siempre en UTC.
3. **Given** un evento, **When** se calculan las características, **Then** el tipo de evento, la acción, el
   resultado y la fuente se conservan tal como están en el catálogo del incremento 1, sin transformar a
   números arbitrarios.
4. **Given** una fuente que el modelo no vio nunca, **When** se calculan las características, **Then**
   se conserva su valor sin error (la tolerancia a categorías desconocidas es del incremento 4).

---

### User Story 3 - Calcular las características igual en entrenamiento y en inferencia (Priority: P1)

El ingeniero de ML puede calcular las características de un conjunto grande de eventos de una sola vez
(entrenamiento) y el analista puede calcular las de **un solo evento** con la historia previa necesaria
(inferencia). Ambos caminos usan exactamente la misma lógica y dan exactamente el mismo resultado para el
mismo evento y la misma historia.

**Why this priority**: es la consistencia entre entrenamiento e inferencia que exigen el Principio III y
NFR-04; si divergen, el modelo se entrena con una cosa y se usa con otra.

**Independent Test**: calcular las características de un conjunto de eventos por lotes y, después, evento
a evento con su historia previa, y comparar ambos resultados.

**Acceptance Scenarios**:

1. **Given** un conjunto de eventos, **When** se calculan por lotes y luego uno a uno con su historia
   conocida, **Then** los vectores son idénticos en todos los eventos.
2. **Given** el mismo conjunto en dos órdenes de llegada distintos, **When** se calculan por lotes,
   **Then** los vectores de cada evento son idénticos.
3. **Given** un rango de eventos grande, **When** se calculan las características, **Then** se puede
   procesar leyéndolos por bloques sin cargar todo el rango en memoria.
4. **Given** el cálculo de un único evento, **When** el llamador aporta la historia de los cinco minutos
   previos, **Then** no necesita ningún dato posterior al evento.

---

### User Story 4 - Tratar los eventos fuera de orden y avisar cuando falta contexto (Priority: P2)

Un evento que llega tarde (con un `timestamp` anterior a otros ya conocidos) se puntúa con lo que se
sabía hasta su propio instante, sin recalcular las características de los eventos anteriores. Cuando la
historia disponible no cubre la ventana completa, el vector lo indica para que quien lo consuma no
confunda "poca actividad" con "no hay datos".

**Why this priority**: decisión D5 y SPEC §4.4; no hace falta para el caso feliz, pero evita falsos
"comportamiento normal" al empezar un dataset o tras un hueco en los datos.

**Independent Test**: calcular las características de un evento tardío y de uno situado al inicio del
rango y comprobar sus valores y su indicador de contexto.

**Acceptance Scenarios**:

1. **Given** un evento que llega después de otros con `timestamp` mayor, **When** se calculan sus
   características, **Then** solo cuentan los eventos conocidos con un instante menor o igual al suyo.
2. **Given** características ya calculadas para eventos anteriores, **When** llega un evento tardío,
   **Then** las características ya calculadas no se modifican.
3. **Given** un evento cuya ventana de cinco minutos empieza antes del inicio de la historia disponible,
   **When** se calculan sus características, **Then** el vector marca el contexto como incompleto.
4. **Given** un evento cuya ventana está completamente cubierta por historia disponible, **When** se
   calculan sus características, **Then** el vector marca el contexto como completo, aunque la ventana
   no contenga otros eventos.

---

### User Story 5 - Identificar y reproducir el esquema de características (Priority: P2)

El ingeniero de ML dispone de un esquema de características con un identificador de versión: qué
características hay, en qué orden, de qué tipo y con qué definición. El esquema se guardará junto al modelo
en el incremento 4, y las mismas entradas con el mismo esquema producen siempre exactamente las mismas
características.

**Why this priority**: sin un esquema versionado no se puede garantizar que entrenamiento e inferencia
usen el mismo pipeline (Principio III) ni auditar un modelo.

**Independent Test**: calcular dos veces las características con las mismas entradas y comparar; cambiar la
definición de una característica y comprobar que la versión o la huella del esquema cambia.

**Acceptance Scenarios**:

1. **Given** las mismas entradas, **When** se calculan las características dos veces, **Then** los
   resultados son idénticos.
2. **Given** el esquema, **When** se consulta, **Then** lista cada característica con su nombre, su tipo y
   su posición, e incluye la versión del esquema y una huella determinista de su contenido.
3. **Given** un cambio en la definición de una característica, **When** se compara con el esquema
   anterior, **Then** la huella cambia, de modo que un modelo no puede usarse con un esquema distinto sin
   detectarlo.
4. **Given** un vector de características, **When** se inspecciona, **Then** incluye la versión del
   esquema con el que se calculó.

---

### User Story 6 - Manejar datos ausentes y no exponer identificadores (Priority: P3)

Cuando un evento no tiene IP o usuario, las características que dependen de ellos toman un valor definido
y determinista, y el vector lo indica. Los vectores nunca contienen el nombre de usuario, la IP, el host
ni el identificador del evento como característica del modelo: el comportamiento por IP y por usuario se
representa solo con agregados.

**Why this priority**: privacidad por diseño (Principio IV) y SPEC §5.1 (usuario e IP no se codifican como
valores ordinales arbitrarios); no bloquea el cálculo, pero condiciona el contrato del vector.

**Independent Test**: calcular características de eventos sin IP, sin usuario y sin ambos, y buscar
valores centinela en los vectores.

**Acceptance Scenarios**:

1. **Given** un evento sin IP, **When** se calculan las características, **Then** las agregadas por IP
   toman el valor definido para "ausente" y el vector indica que no había IP.
2. **Given** un evento sin usuario, **When** se calculan las características, **Then** las agregadas por
   usuario toman el valor definido para "ausente" y el vector indica que no había usuario.
3. **Given** eventos con valores centinela en IP, seudónimo, host e identificador, **When** se calculan las
   características, **Then** ninguno de esos valores aparece en los vectores ni en los registros de
   actividad.
4. **Given** eventos con la IP y el seudónimo presentes, **When** se inspecciona el esquema, **Then**
   ninguna característica contiene la IP ni el seudónimo como tal, solo recuentos y tasas.

---

### Edge Cases

- Primer evento de un rango o de un dataset: historia vacía, contexto incompleto.
- Ráfaga muy grande desde una sola IP (miles de eventos en cinco minutos): el recuento sigue siendo exacto.
- Muchas IPs distintas activas a la vez: el uso de memoria queda acotado por la ventana, no por el tamaño total del dataset.
- Eventos con exactamente el mismo `timestamp`, incluidos los de IPs distintas y los de la misma IP.
- Evento en el borde exacto de la ventana (hace exactamente cinco minutos): comportamiento definido y probado.
- Eventos fuera de orden con diferencias de segundos o de días.
- Un hueco en los datos de más de cinco minutos: las ventanas posteriores no arrastran actividad anterior al hueco, pero el contexto se evalúa con la historia disponible.
- Eventos sin IP, sin usuario o sin ninguno de los dos.
- IPv6 en formas equivalentes (abreviada o completa): cuentan como la misma IP.
- Un mismo seudónimo desde varias IPs y una misma IP con varios seudónimos a la vez.
- La misma IP en dos fuentes distintas, o contra dos hosts de la misma fuente: en el primer caso se cuenta por separado; en el segundo, junta.
- Zonas horarias distintas de UTC, cambio de día y cambio de año.
- Una fuente nunca vista antes.
- Entrada vacía: devuelve cero vectores sin error.
- Cambiar el orden de llegada de los eventos de entrada no cambia ningún vector.
- Un evento con `timestamp` posterior a todos los demás de su ventana y un evento tardío con `timestamp` anterior a ellos.

## Requirements *(mandatory)*

### Functional Requirements

**Características por evento**

- **FR-003-01**: El sistema MUST calcular, para cada evento, la hora del día en UTC en una representación
  cíclica (de modo que las 23:59 y las 00:00 resulten próximas), el día de la semana en UTC, y conservar el
  tipo de evento, la acción, el resultado y la fuente como categorías.
- **FR-003-02**: Las características por evento MUST depender únicamente de los campos de ese evento y no de
  ningún otro.
- **FR-003-03**: La hora y el día MUST calcularse siempre en UTC, con independencia de la zona horaria con
  la que llegó el `timestamp`.

**Características por ventana**

- **FR-003-04**: El sistema MUST calcular, para cada evento con IP, sobre una ventana de cinco minutos que
  termina en el propio evento: el número de eventos de esa IP, el número de fallos de esa IP, la tasa de
  fallos de esa IP y el número de usuarios distintos de esa IP.
- **FR-003-05**: El sistema MUST calcular, para cada evento con usuario, el número de IPs distintas de ese
  usuario en esa misma ventana.
- **FR-003-06**: Un fallo MUST ser un evento con resultado `failure`; la tasa de fallos MUST ser el
  cociente entre fallos y eventos de la ventana (el evento puntuado cuenta como parte de ella), con valor 0
  cuando no hay eventos.
- **FR-003-07**: La ventana MUST ser deslizante y estar anclada en el instante del evento puntuado: incluye
  los eventos con `timestamp` posterior a "instante − 5 minutos" y hasta el del propio evento.
- **FR-003-08**: Las IPs MUST compararse por valor: las formas distintas de una misma dirección cuentan como
  la misma.
- **FR-003-09**: Las agregadas MUST calcularse por `(source, IP)` y por `(source, usuario)`: una misma IP o
  seudónimo en fuentes distintas cuenta por separado, los hosts de una misma fuente se suman y `host` no
  forma parte de la clave.
- **FR-003-10**: Los usuarios MUST contarse por seudónimo; nunca se trabaja con el nombre original.

**Causalidad y orden**

- **FR-003-11**: Las características agregadas MUST calcularse solo con eventos conocidos hasta el instante
  del evento puntuado. Ningún evento posterior MUST influir en ellas (Principio III).
- **FR-003-12**: El sistema MUST usar el orden total `(timestamp, source, event_id)` para decidir qué
  eventos forman la historia de cada evento: la historia de un evento incluye solo los eventos que lo
  preceden en ese orden más el propio evento. Un evento con el mismo `timestamp` pero posterior en el orden
  MUST NOT entrar en ella. El resultado no depende del orden de llegada ni del de entrada.
- **FR-003-13**: Un evento fuera de orden MUST puntuarse con los eventos conocidos de instante menor o igual
  al suyo (decisión D5); el cálculo de un evento MUST NOT modificar las características ya calculadas de
  otros eventos.
- **FR-003-14**: Cada vector MUST indicar si su contexto está completo: es completo cuando la ventana
  completa del evento queda dentro del periodo de historia disponible que declara quien llama (el instante
  "evento − 5 minutos" no es anterior al inicio declarado), e incompleto en caso contrario (SPEC §4.4). No se
  deduce de los datos de entrada.

**Mismo cálculo en entrenamiento e inferencia**

- **FR-003-15**: El sistema MUST ofrecer un único cálculo de características para dos usos: un conjunto de
  eventos de una vez y un evento individual con su historia previa. Ambos MUST dar el mismo vector para el
  mismo evento y la misma historia (NFR-04).
- **FR-003-16**: El cálculo por conjuntos MUST poder consumir eventos por bloques con memoria acotada por
  el tamaño de la ventana y no por el del dataset.
- **FR-003-17**: El cálculo de un evento individual MUST necesitar solo la historia de la ventana previa a
  ese evento y MUST NOT requerir ningún dato posterior.

**Esquema, determinismo y valores ausentes**

- **FR-003-18**: El sistema MUST publicar un esquema de características: nombre, tipo, posición y definición
  de cada una, una versión del esquema y una huella determinista de su contenido.
- **FR-003-19**: Cada vector MUST incluir la versión del esquema con el que se calculó y el identificador
  `(source, event_id)` del evento al que pertenece.
- **FR-003-20**: Con las mismas entradas y el mismo esquema, las características MUST ser idénticas entre
  ejecuciones, entornos con el mismo lockfile y órdenes de entrada.
- **FR-003-21**: Cualquier cambio en la definición, el orden o el tipo de una característica MUST cambiar la
  huella del esquema y MUST exigir subir su versión.
- **FR-003-22**: Los valores ausentes MUST tratarse de forma determinista: las agregadas que dependen de
  una IP o de un usuario ausente toman un valor definido (0) y el vector incluye un indicador de presencia
  de IP y de usuario.

**Privacidad, seguridad y observabilidad**

- **FR-003-23**: Los vectores MUST NOT contener el nombre de usuario, el seudónimo, la IP, el host ni el
  identificador del evento como característica del modelo; solo agregados, tasas, indicadores y categorías
  del catálogo (SPEC §5.1; Principio IV).
- **FR-003-24**: El registro de actividad del cálculo MUST contener solo recuentos, duraciones y la versión
  del esquema, nunca valores de eventos, IPs ni usuarios.
- **FR-003-25**: Las entradas inválidas (por ejemplo, un periodo de historia sin zona horaria o un evento
  anterior al inicio declarado de la historia) MUST producir errores controlados que no incluyan valores de
  los datos.

**Alcance**

- **FR-003-26**: Este incremento MUST NOT introducir endpoints, entrenamiento, modelos, escalado ni
  codificación de categorías, separación entrenamiento/calibración/prueba, persistencia de características
  ni de predicciones, ni dependencias no aprobadas.

### Key Entities

- **Esquema de características**: lista ordenada y versionada de las características (nombre, tipo,
  definición), con una huella determinista de su contenido.
- **Vector de características**: resultado de un evento; incluye el identificador `(source, event_id)` y el
  `timestamp` del evento, el valor de cada característica, el indicador de contexto completo, los
  indicadores de presencia de IP y de usuario y la versión del esquema.
- **Ventana de actividad**: los cinco minutos anteriores al evento (hasta el propio evento) sobre los que se
  agregan los eventos de la misma IP y del mismo usuario.
- **Historia de un evento**: eventos conocidos de instante menor o igual al suyo (según el orden total) que
  entran en su ventana.
- **Periodo de historia disponible**: el intervalo que quien llama declara como completo; sirve para decidir
  si el contexto de un evento es completo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En el 100 % de los casos de una batería de flujos generados (incluida una ráfaga de fallos),
  modificar, añadir o quitar eventos posteriores al instante de un evento no cambia ni un valor de su
  vector ni de los de los eventos anteriores: **cero fugas de futuro**.
- **SC-002**: Calcular un conjunto de al menos 5.000 eventos por lotes y evento a evento, con la historia
  previa de cada uno, da vectores idénticos en el 100 % de los eventos.
- **SC-003**: Calcular dos veces las mismas entradas, o con el orden de entrada alterado, da vectores
  idénticos en el 100 % de los eventos y ejecuciones.
- **SC-004**: En un conjunto sintético con una ráfaga de 30 fallos desde una IP en cinco minutos, el último
  evento de la ráfaga tiene un recuento de fallos de esa IP de 30 y una tasa de fallos de 1, frente a un
  recuento de a lo sumo 3 y una tasa menor en el tráfico de fondo.
- **SC-005**: Calcular las características de 100.000 eventos termina en menos de 60 segundos y calcular
  las de un evento individual con su historia previa, en menos de 100 milisegundos en el percentil 95 en una
  máquina de desarrollo convencional, registrando sus condiciones (orientativo; NFR-06 fija 500 ms para toda
  la puntuación).
- **SC-006**: 0 valores de usuario, seudónimo, IP, host o identificador de evento en los vectores, en los
  esquemas y en los registros de actividad, en el 100 % de los casos de prueba.
- **SC-007**: Modificar la definición de cualquier característica cambia la huella del esquema en el 100 %
  de los casos probados, y cada vector indica la versión del esquema con el que se calculó.
- **SC-008**: El uso de memoria al procesar un rango grande por bloques no crece con el tamaño del dataset:
  procesar 100.000 eventos y 10.000 eventos con la misma actividad concurrente usa memoria del mismo orden.

## Assumptions

- Los eventos de entrada son los que guarda el incremento 2 (válidos, normalizados, con el usuario ya
  seudonimizado) y llegan por lectura de rango temporal en orden cronológico; esta capacidad no los guarda
  ni los modifica.
- La ventana es **deslizante** y está anclada en el evento puntuado (clarificado): incluye los eventos
  posteriores a "instante − 5 minutos" y hasta el propio evento. La longitud de cinco minutos forma parte del esquema v1:
  cambiarla es un cambio de esquema.
- Para decidir qué entra en la historia se usa el orden total `(timestamp, source, event_id)`, el mismo de la
  lectura por rango del incremento 2 (clarificado). Un evento con el mismo instante pero posterior en ese
  orden **no** entra en la historia de otro, de modo que entrenamiento e inferencia ven lo mismo. Es una
  lectura más estricta que "instante menor o igual" de SPEC §4.4; ese texto se aclara en consecuencia.
- Las características por evento categóricas (tipo, acción, resultado, fuente) se entregan como categorías
  del catálogo; su codificación numérica, escalado y la tolerancia a categorías desconocidas pertenecen al
  incremento 4.
- El día de la semana se entrega como número (lunes = 0 … domingo = 6) y la hora cíclica como seno y coseno
  de la hora del día; su forma exacta se fija en el plan.
- El periodo de historia disponible lo declara quien llama (clarificado; por ejemplo, el inicio del rango
  cargado); el incremento 5 lo derivará de lo almacenado. Nunca se deduce de los propios eventos de entrada.
- Un valor ausente de IP o usuario se representa con 0 y un indicador de presencia, en lugar de omitir la
  característica, para mantener una forma fija del vector.
- No se persisten las características: se calculan bajo demanda a partir de los eventos. La persistencia de
  predicciones llega en el incremento 5.
- Sin dependencias nuevas: solo lo ya aprobado (biblioteca estándar y Pydantic). Si el plan concluyera que
  hace falta otra, se pediría aprobación y un ADR.
- La clave `(source, event_id)` identifica al evento; las agregadas se calculan **por fuente y por
  entidad** (clarificado): `(source, IP)` y `(source, usuario)`, sumando todos los hosts de la fuente. No se
  mezclan IPs ni usuarios de fuentes distintas, y `host` no forma parte de la clave de agregación.
- Los datos de pruebas son sintéticos (incluido el generador con ráfagas de fallos del incremento 1); las
  características describen comportamiento, no demuestran que haya un ataque (Principio II).
- Las metas de tiempo y memoria son orientativas y se miden en una máquina de desarrollo convencional,
  registrando hardware, volumen y condiciones.
- Dependencias: incremento 1 (eventos normalizados y datos sintéticos) e incremento 2 (lectura por rango
  temporal sin fuga de futuro); no se aprueban dependencias nuevas sin un ADR.
