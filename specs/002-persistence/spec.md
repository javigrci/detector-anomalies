# Feature Specification: Persistencia de eventos

**Feature Branch**: `002-persistence` (se trabaja en `main`; la carpeta es independiente de la rama)

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "Incremento 2 (002-persistence): persistencia de eventos normalizados en PostgreSQL 16 con migraciones, sin API pública. Primera migración, guardado idempotente entre lotes y ejecuciones, consulta con filtros combinables y paginación estable, consulta por rango temporal para el incremento 3, índices, retención configurable con purga explícita, mínimos privilegios con roles distintos para migraciones y aplicación, ADR de rotación de PSEUDONYM_KEY y tests de integración contra PostgreSQL real."

## Clarifications

### Session 2026-11-20

- Q: ¿Desde cuándo se cuenta el periodo de retención? → A: Desde la fecha de ingesta de cada evento, no desde su timestamp; así los datos históricos o sintéticos no se purgan al cargarse.
- Q: ¿Se guarda una versión de la clave de seudonimización en cada evento? → A: No: se asume una única clave durante la vida de los datos; rotarla exige purgar antes los datos seudonimizados con la clave anterior (o aceptar explícitamente que el comportamiento por usuario queda partido), y el ADR documenta el procedimiento y su coste.
- Q: ¿Quién puede borrar eventos en la base de datos? → A: Tres roles: migraciones (propietario del esquema), aplicación (solo insertar y consultar) y mantenimiento (solo borrar eventos para la purga, con credenciales distintas que solo usa quien ejecuta la purga).
- Q: ¿Qué tipo de paginación usa la consulta de eventos? → A: Tamaño de página y desplazamiento con orden total determinista y total de resultados (SPEC §6.2); se documenta que las inserciones concurrentes pueden desplazar páginas, y las lecturas largas que necesitan exactitud usan la lectura por rango temporal.
- Q: ¿Se guarda un registro de cada guardado (lote) con su resumen? → A: No: solo el identificador de lote y la fecha de ingesta en cada evento insertado; el resumen lo recibe quien llama y no se almacena, así que un guardado que no inserta nada no deja rastro.

## User Scenarios & Testing *(mandatory)*

Los "usuarios" de este incremento son el **administrador técnico** (guarda lotes, aplica migraciones
y purga datos antiguos), el **operador** (configura los roles de la base de datos) y el
**desarrollador / ingeniero de ML** (consulta eventos para calcular características en el
incremento 3). Todavía no hay interfaz pública: la capacidad se entrega como lógica reutilizable
que la API del incremento 5 consumirá. Se parte del resultado de la ingesta del incremento 1
(eventos válidos, normalizados y con el usuario ya seudonimizado).

### User Story 1 - Guardar un lote ingerido sin duplicar nada (Priority: P1)

Un administrador guarda el resultado de una ingesta y recibe un resumen: cuántos eventos se
insertaron y cuántos ya existían. Guardar el mismo lote dos veces, o dos lotes que comparten
eventos, nunca produce duplicados, y un fallo a mitad de un lote no deja datos a medias.

**Why this priority**: es el valor central del incremento y cierra una deuda explícita del
incremento 1, que solo deduplica dentro de cada lote y delegó aquí la deduplicación entre lotes
(US-01 de SPEC §11).

**Independent Test**: guardar un lote, volver a guardarlo y guardar un segundo lote que solapa con
el primero; comparar los recuentos y el contenido almacenado.

**Acceptance Scenarios**:

1. **Given** una base de datos vacía, **When** se guarda un lote de eventos válidos, **Then** todos
   quedan almacenados y el resumen indica N insertados y 0 ya existentes.
2. **Given** un lote ya guardado, **When** se guarda otra vez, **Then** no se añade ninguna fila y
   el resumen indica 0 insertados y N ya existentes.
3. **Given** dos lotes que comparten parte de sus eventos, **When** se guardan, **Then** los
   eventos compartidos existen una sola vez y los resúmenes suman correctamente.
4. **Given** un evento ya almacenado y el mismo `(source, event_id)` con contenido distinto en un
   lote nuevo, **When** se guarda, **Then** se conserva el original, el evento cuenta como ya
   existente y el resumen indica que su contenido difería.
5. **Given** un fallo de la base de datos a mitad de un lote, **When** se intenta guardar,
   **Then** no queda almacenado ningún evento de ese lote y el error no revela credenciales ni
   valores.
6. **Given** dos guardados simultáneos del mismo evento, **When** terminan, **Then** el evento
   existe una sola vez y ninguno de los dos falla por ello.
7. **Given** eventos con usuario, **When** se guardan, **Then** solo se almacena el seudónimo; el
   nombre original no existe en ninguna parte de la base de datos.

---

### User Story 2 - Consultar eventos con filtros y paginación estable (Priority: P1)

Un desarrollador o analista consulta los eventos almacenados combinando filtros (fechas, fuente,
tipo, acción, resultado, IP y seudónimo de usuario) y recorre los resultados por páginas sin ver
repetidos ni perder ninguno.

**Why this priority**: sin consulta, lo guardado no sirve; es la base de las pantallas de
investigación y de la API del incremento 5 (US-04 de SPEC §11).

**Independent Test**: almacenar un conjunto conocido, aplicar combinaciones de filtros y recorrer
todas las páginas, comparando con el resultado esperado.

**Acceptance Scenarios**:

1. **Given** eventos almacenados, **When** se filtra por un rango de fechas, **Then** solo se
   devuelven los eventos dentro del rango.
2. **Given** eventos almacenados, **When** se combinan varios filtros, **Then** se devuelven solo
   los que cumplen **todos** (conjunción).
3. **Given** un conjunto de resultados mayor que una página y datos que no cambian durante el
   recorrido, **When** se recorren todas las páginas, **Then** cada evento aparece exactamente una
   vez, en un orden determinista.
   Si se insertan eventos mientras se recorren, las páginas pueden desplazarse; esto está
   documentado y la lectura por rango temporal (historia 3) es la que ofrece exactitud en ese caso.
4. **Given** una consulta, **When** se pide una página, **Then** la respuesta incluye el total de
   eventos que cumplen los filtros, el tamaño de página y la posición.
5. **Given** filtros inválidos (fecha final anterior a la inicial, tamaño de página fuera de
   rango, IP malformada), **When** se consulta, **Then** se rechazan con un motivo claro antes de
   consultar la base de datos.
6. **Given** una consulta sin resultados, **When** se ejecuta, **Then** devuelve una página vacía
   con total 0, sin error.
7. **Given** un filtro por seudónimo de usuario, **When** se consulta, **Then** se busca por el
   seudónimo; nunca se acepta ni se devuelve un nombre de usuario real.

---

### User Story 3 - Leer eventos por rango temporal sin fuga de futuro (Priority: P2)

El incremento 3 necesita leer los eventos de una ventana temporal en orden cronológico para
calcular características. La lectura nunca devuelve eventos posteriores al límite superior pedido y
funciona con rangos grandes sin cargarlo todo en memoria.

**Why this priority**: es el contrato del que depende la integridad del modelo (Principio III de la
constitución, NFR-04 de SPEC §10); no hace falta para guardar ni consultar, pero sí para el 3.

**Independent Test**: almacenar eventos distribuidos en el tiempo, leer ventanas distintas y
comprobar el orden, los límites y que ningún evento posterior al límite aparece.

**Acceptance Scenarios**:

1. **Given** eventos de varios días, **When** se lee un rango, **Then** se devuelven en orden
   cronológico ascendente con un desempate determinista.
2. **Given** un rango `[desde, hasta)`, **When** se lee, **Then** no se devuelve ningún evento con
   timestamp igual o posterior a `hasta` ni anterior a `desde`.
3. **Given** un rango con muchos eventos, **When** se lee por bloques, **Then** se obtienen todos
   sin duplicados ni saltos y sin cargar el rango completo en memoria.
4. **Given** eventos que se guardaron fuera de orden o en lotes distintos, **When** se leen por
   rango, **Then** salen ordenados por su timestamp, no por el orden de inserción.
5. **Given** eventos con el mismo timestamp, **When** se leen, **Then** el orden entre ellos es
   siempre el mismo.

---

### User Story 4 - Retener datos solo el tiempo necesario (Priority: P2)

Un administrador define cuánto tiempo se conservan los eventos y ejecuta de forma explícita una
purga que borra los más antiguos. Antes de borrar puede ver cuántos se borrarían.

**Why this priority**: privacidad y minimización de datos (Principio IV, decisión D8); necesaria
antes de usar datos reales, pero no bloquea el guardado ni la consulta.

**Independent Test**: almacenar eventos con antigüedades conocidas, simular y ejecutar la purga y
comprobar qué queda.

**Acceptance Scenarios**:

1. **Given** eventos que llevan distinto tiempo almacenados y un periodo de retención, **When** se
   ejecuta la purga, **Then** se borran solo los que llevan almacenados más tiempo que el periodo
   (contado desde su ingesta) y el resumen indica cuántos.
2. **Given** una purga en modo simulación, **When** se ejecuta, **Then** informa cuántos eventos se
   borrarían y no borra ninguno.
3. **Given** que no se ha ejecutado ninguna purga, **When** pasa el tiempo, **Then** no se borra
   nada de forma automática.
4. **Given** una purga ya ejecutada, **When** se repite, **Then** no falla y borra 0 eventos.
5. **Given** un periodo no válido (cero o negativo), **When** se intenta purgar, **Then** se
   rechaza sin borrar nada.
6. **Given** que no se configura el periodo, **When** se ejecuta la purga, **Then** se usa el valor
   por defecto de 90 días.
7. **Given** eventos con timestamps muy antiguos que se acaban de ingerir, **When** se ejecuta la
   purga, **Then** no se borran, porque el periodo se mide desde su ingesta y no desde su timestamp.
8. **Given** un evento ya almacenado que se vuelve a guardar, **When** se repite el guardado,
   **Then** su fecha de ingesta no cambia, así que reingerirlo no reinicia su periodo de retención.

---

### User Story 5 - Separar quién migra, quién usa y quién purga los datos (Priority: P2)

Un operador configura tres roles en la base de datos: uno que crea y modifica el esquema
(migraciones), otro con los mínimos privilegios que usa la aplicación para guardar y consultar
eventos, y un tercero de mantenimiento que solo puede borrar eventos y que únicamente usa quien
ejecuta la purga. Así, una aplicación comprometida ni puede alterar el esquema ni borrar datos.

**Why this priority**: mínimos privilegios exigidos por SPEC §9 y el Principio IV; limita el daño
si la aplicación se compromete.

**Independent Test**: conectar con cada rol e intentar las operaciones permitidas y las prohibidas.

**Acceptance Scenarios**:

1. **Given** el rol de aplicación, **When** guarda y consulta eventos, **Then** todo funciona.
2. **Given** el rol de aplicación, **When** intenta crear, alterar o borrar tablas, vaciar una
   tabla entera o borrar eventos, **Then** la base de datos lo deniega.
3. **Given** el rol de mantenimiento, **When** ejecuta la purga, **Then** borra los eventos
   correspondientes; y cuando intenta insertar eventos o alterar el esquema, la base de datos lo
   deniega.
4. **Given** el rol de migraciones, **When** aplica las migraciones sobre una base de datos vacía,
   **Then** crea el esquema y concede a los otros dos roles solo los permisos necesarios.
5. **Given** las migraciones ya aplicadas, **When** se vuelven a aplicar, **Then** no hacen nada y
   no fallan.
6. **Given** el entorno local con Compose, **When** se levanta desde cero, **Then** los tres roles
   existen, con contraseñas distintas tomadas del entorno y nunca del repositorio, y la base de
   datos sigue sin publicarse en el equipo.

---

### User Story 6 - Decidir qué pasa al rotar la clave de seudonimización (Priority: P3)

El equipo dispone de una decisión escrita sobre la rotación de `PSEUDONYM_KEY`: qué ocurre con los
seudónimos y los identificadores ya almacenados cuando se cambia la clave, y qué debe hacer un
operador.

**Why this priority**: es una decisión pendiente del incremento 1; hay que tomarla antes de que
existan datos reales almacenados, pero no bloquea el código.

**Independent Test**: revisar que existe un registro de decisión que cubre los casos y que las
pruebas reflejan el comportamiento decidido.

**Acceptance Scenarios**:

1. **Given** el registro de decisión, **When** se revisa, **Then** explica el efecto de rotar la
   clave sobre los seudónimos, los identificadores del adaptador de Linux auth y la idempotencia al
   reingerir.
2. **Given** datos ya almacenados con la clave anterior, **When** se lee la decisión, **Then**
   indica que se purgan antes de rotar la clave (o que se acepta explícitamente que el
   comportamiento por usuario queda partido) y por qué, teniendo en cuenta que el nombre original
   nunca se guarda y por tanto no se puede reseudonimizar.
3. **Given** un evento almacenado, **When** se inspecciona, **Then** no contiene ninguna versión ni
   identificador de la clave con la que se seudonimizó (se asume una única clave durante la vida de
   los datos).
4. **Given** la política decidida, **When** se revisan las pruebas, **Then** hay pruebas que
   reflejan su comportamiento observable.

---

### Edge Cases

- Reingesta del mismo archivo tras rotar `PSEUDONYM_KEY`: los identificadores derivados cambian y
  los eventos del adaptador de Linux auth ya no se reconocen como existentes.
- Un lote con 10.000 eventos (el máximo) en una sola transacción.
- Dos guardados concurrentes con eventos solapados.
- Base de datos no disponible o con la conexión caída a mitad del guardado.
- Eventos con el mismo timestamp exacto y orden de lectura estable entre ejecuciones.
- Eventos sin usuario, sin IP o sin host (valores nulos) en filtros y ordenación.
- Direcciones IPv6 en equivalentes distintos (abreviada o completa) al filtrar por IP.
- Filtros por IP o seudónimo con caracteres inesperados: se tratan como datos, nunca como parte de
  una consulta construida.
- Tamaño de página mayor que el máximo permitido o desplazamiento negativo.
- Datos añadidos entre la lectura de dos páginas consecutivas de una misma consulta: las páginas
  pueden desplazarse (limitación documentada de la paginación por desplazamiento).
- Purga con millones de filas candidatas: debe completarse sin bloquear la base de datos de forma
  prolongada.
- Purga con un periodo mayor que la antigüedad de todos los datos (no borra nada).
- Datasets históricos o sintéticos con timestamps muy antiguos recién ingeridos: no se purgan.
- Aplicar las migraciones dos veces, o con un rol que no es propietario del esquema.
- Ejecutar la purga con las credenciales del rol de aplicación: se deniega y no se borra nada.
- Intento de revertir la migración con datos almacenados: es destructivo y requiere autorización
  explícita.
- Contraseñas de la base de datos con caracteres reservados en una URL de conexión.
- Eventos fuera de orden, guardados en un lote posterior a eventos más recientes.
- Un guardado en el que todos los eventos ya existían: devuelve su resumen pero no deja ningún
  rastro almacenado.

## Requirements *(mandatory)*

### Functional Requirements

**Almacenamiento**

- **FR-002-01**: El sistema MUST almacenar los eventos normalizados del incremento 1 con sus campos
  (`event_id`, `timestamp`, `source`, `event_type`, `action`, `outcome`, `user_pseudonym`,
  `source_ip`, `host`) más la fecha de ingesta y el identificador del lote.
- **FR-002-02**: El nombre de usuario original MUST NOT almacenarse en ninguna parte; solo el
  seudónimo, que es nulo si el evento no tenía usuario.
- **FR-002-03**: Los timestamps MUST almacenarse con zona horaria y devolverse siempre en UTC.
- **FR-002-04**: La unicidad de `(source, event_id)` MUST garantizarla el propio almacenamiento, no
  solo la aplicación.
- **FR-002-05**: El esquema MUST crearse exclusivamente mediante migraciones versionadas; aplicar
  las migraciones sobre una base de datos vacía crea el esquema y volver a aplicarlas no cambia
  nada.
- **FR-002-06**: La marca de fuera de orden y la posición de un evento, que son relativas a su lote
  de origen, MUST NOT almacenarse.

**Guardado**

- **FR-002-07**: El sistema MUST guardar el resultado de una ingesta devolviendo cuántos eventos se
  insertaron y cuántos ya existían, y de estos últimos cuántos tenían un contenido distinto.
- **FR-002-08**: El guardado MUST ser idempotente por `(source, event_id)` entre lotes y entre
  ejecuciones, y MUST resolverse correctamente cuando dos guardados concurrentes incluyen el mismo
  evento (sin error ni duplicado).
- **FR-002-09**: Si ya existe un evento con la misma clave y contenido distinto, el sistema MUST
  conservar el original y contabilizarlo, sin sobrescribirlo.
- **FR-002-10**: Cada guardado MUST ser atómico por lote: si falla, no queda almacenado ningún
  evento de ese lote.
- **FR-002-11**: Cada guardado MUST asignar un identificador de lote único, almacenado en los
  eventos que inserta, junto con la fecha de ingesta. El lote no tiene almacenamiento propio: su
  resumen se devuelve a quien llama y no se almacena, y un guardado que no inserta nada no deja
  rastro.
- **FR-002-12**: Solo se guardan los eventos válidos; los registros rechazados del incremento 1
  siguen en el informe de ingesta y no se almacenan.

**Consulta**

- **FR-002-13**: El sistema MUST permitir consultar eventos con filtros combinables (conjunción) por
  rango de fechas, `source`, `event_type`, `action`, `outcome`, IP y `user_pseudonym`.
- **FR-002-14**: Los resultados MUST devolverse con un orden total determinista y paginados con
  tamaño de página y desplazamiento (SPEC §6.2), e incluir el total de eventos que cumplen los
  filtros. La paginación MUST documentar que las inserciones concurrentes pueden desplazar páginas.
- **FR-002-15**: El tamaño de página MUST tener un valor por defecto (100) y un máximo configurable
  (1.000); los parámetros fuera de rango y las fechas incoherentes MUST rechazarse antes de
  consultar la base de datos.
- **FR-002-16**: El sistema MUST ofrecer una lectura por rango temporal semiabierto `[desde, hasta)`
  en orden cronológico ascendente con desempate determinista, por bloques de tamaño acotado, que
  MUST NOT devolver nunca un evento con timestamp igual o posterior a `hasta` ni anterior a `desde`.
- **FR-002-17**: Las consultas por IP MUST tratar como equivalentes las formas distintas de una misma
  dirección y los filtros MUST tratarse siempre como datos, nunca como parte de una consulta
  construida.

**Índices**

- **FR-002-18**: El almacenamiento MUST incluir índices que sirvan a las consultas anteriores:
  `timestamp`, `source`, IP y los demás campos filtrables, y la unicidad de `(source, event_id)`.

**Retención**

- **FR-002-19**: El sistema MUST tener un periodo de retención configurable, con 90 días por defecto
  (decisión D8). El periodo MUST contarse desde la fecha de ingesta de cada evento, no desde su
  timestamp, para que los datos históricos o sintéticos no se purguen al cargarse; guardar de nuevo
  un evento ya existente MUST NOT modificar su fecha de ingesta.
- **FR-002-20**: La purga MUST ser una operación explícita (nunca automática), MUST informar cuántos
  eventos borró, MUST poder ejecutarse en modo simulación que informa sin borrar, MUST ser
  repetible sin error (una purga ya hecha borra 0) y MUST ejecutarse con las credenciales del rol
  de mantenimiento, nunca con las del rol de aplicación.
- **FR-002-21**: La purga MUST rechazar periodos nulos o negativos sin borrar nada y MUST evitar
  bloquear la base de datos de forma prolongada.

**Privilegios y entorno**

- **FR-002-22**: El sistema MUST usar tres roles distintos en la base de datos: uno propietario del
  esquema para las migraciones; otro de aplicación que solo puede insertar y consultar eventos; y
  otro de mantenimiento que solo puede borrar eventos (y leer lo necesario para contar), con
  credenciales distintas. Ni el de aplicación ni el de mantenimiento pueden crear, alterar o borrar
  objetos ni vaciar tablas, y el de aplicación no puede borrar eventos.
- **FR-002-23**: El entorno local con Compose MUST crear los tres roles desde cero a partir de
  variables de entorno, con contraseñas distintas, sin contraseñas en el repositorio ni en la
  imagen, y la base de datos MUST seguir sin publicarse en el equipo.

**Seguridad y observabilidad**

- **FR-002-24**: Todas las consultas MUST ser parametrizadas; ninguna MUST construirse con datos de
  entrada.
- **FR-002-25**: Los errores de la base de datos MUST convertirse en errores controlados que no
  incluyan credenciales, valores de datos ni sentencias con parámetros.
- **FR-002-26**: El registro de actividad del guardado, la consulta y la purga MUST contener solo
  recuentos, duraciones e identificadores de lote, nunca valores de eventos ni usuarios.

**Rotación de clave**

- **FR-002-27**: El proyecto MUST contar con un registro de decisión (ADR) que fije la política de
  rotación de `PSEUDONYM_KEY` y su efecto sobre los seudónimos, los identificadores derivados y la
  idempotencia, indicando qué se hace con los datos ya almacenados. Los eventos MUST NOT almacenar
  una versión de clave: se asume una única clave durante la vida de los datos, y la política MUST
  exigir purgar los datos seudonimizados con la clave anterior antes de rotarla (o aceptar
  explícitamente que el comportamiento por usuario queda partido), describiendo el procedimiento y
  su coste.

**Pruebas y alcance**

- **FR-002-28**: Los tests contra PostgreSQL real MUST ejecutarse en el job de integración de la CI
  existente y la lógica pura MUST probarse sin servicios externos.
- **FR-002-29**: Este incremento MUST NOT introducir endpoints, autenticación con API key y roles de
  aplicación, características por ventana, entrenamiento, modelos, ni las tablas de predicciones,
  versiones de modelo y ejecuciones de entrenamiento, ni dependencias no aprobadas.

### Key Entities

- **Evento almacenado**: un evento normalizado persistido, único por `(source, event_id)`, con el
  seudónimo en lugar del usuario, la fecha de ingesta y el identificador del lote que lo insertó.
- **Lote de ingesta**: un guardado, identificado por un identificador único; ese identificador y la
  fecha de ingesta se almacenan en los eventos que inserta, y su resumen no se almacena.
- **Resumen de guardado**: recuentos de eventos insertados, ya existentes y ya existentes con
  contenido distinto.
- **Filtro de consulta**: conjunto de condiciones combinables (fechas, fuente, tipo, acción,
  resultado, IP, seudónimo) más tamaño de página y desplazamiento.
- **Página de resultados**: eventos de una página con el total, el tamaño de página y la posición.
- **Política de retención**: periodo en días (90 por defecto), medido desde la fecha de ingesta de
  cada evento.
- **Roles de base de datos**: el rol propietario del esquema (migraciones), el rol de aplicación
  (solo insertar y consultar) y el rol de mantenimiento (solo borrar eventos, para la purga).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un lote de 10.000 eventos se guarda y se informa en menos de 10 segundos en una máquina
  de desarrollo convencional.
- **SC-002**: Volver a guardar un lote ya guardado deja 0 filas nuevas y el resumen indica 0
  insertados y todos existentes, en el 100 % de los casos, incluidos los guardados concurrentes.
- **SC-003**: Recorrer 5.000 eventos con páginas de 100, sin cambios en los datos durante el
  recorrido, devuelve cada evento exactamente una vez y en el mismo orden en ejecuciones repetidas,
  en el 100 % de los casos.
- **SC-004**: Una consulta por rango de un día sobre 100.000 eventos almacenados responde en menos de
  1 segundo.
- **SC-005**: Tras una purga, 0 eventos llevan almacenados más tiempo que el periodo y el 100 % de los
  eventos dentro del periodo permanece intacto, aunque sus timestamps sean antiguos; el modo
  simulación no borra ninguno.
- **SC-006**: 0 nombres de usuario en claro en los datos almacenados, en los errores, en los
  registros de actividad y en los resultados de las consultas.
- **SC-007**: El 100 % de los intentos de crear, alterar o borrar objetos, o de vaciar tablas, con el
  rol de aplicación o el de mantenimiento, y de borrar eventos con el rol de aplicación, son
  denegados por la base de datos.
- **SC-008**: Las migraciones se aplican sobre una base de datos vacía y de nuevo sobre la ya migrada
  sin errores, y el ADR de rotación de clave existe y cubre los tres efectos descritos.

## Assumptions

- Los usuarios son el administrador técnico, el operador y el desarrollador / ingeniero de ML; no hay
  usuarios finales ni interfaz pública en este incremento (la API llega en el incremento 5).
- Las entradas del guardado son los eventos válidos que produce la ingesta del incremento 1; los
  registros rechazados no se almacenan.
- La unicidad se evalúa sobre los valores ya normalizados de `(source, event_id)`.
- El guardado es atómico por lote: si algo falla, no se guarda nada de ese lote (política coherente
  con la decisión D6, que aplica a la validación y no al almacenamiento).
- La paginación usa tamaño de página y desplazamiento, como indica SPEC §6.2, con un orden total
  determinista; los datos añadidos entre dos páginas pueden desplazar los resultados, y las lecturas
  por rango temporal usan bloques sobre un rango cerrado por `hasta` para no verse afectadas.
- Las tablas de predicciones, versiones de modelo y ejecuciones de entrenamiento de SPEC §7 se crean
  en los incrementos 4 y 5; pueden añadirse sin romper este esquema.
- La retención se mide desde la fecha de ingesta de cada evento y se asume una única clave de
  seudonimización durante la vida de los datos (sin versión de clave por evento); pasar a varias
  claves exigiría una migración y un cambio de contrato.
- La purga la ejecuta una persona de forma explícita con las credenciales del rol de mantenimiento; el
  servicio de aplicación no tiene esas credenciales y no puede borrar eventos.
- No hay una tabla de lotes: la trazabilidad de cada evento es su identificador de lote y su fecha
  de ingesta; auditar cargas completas (incluidas las que no insertan nada) exigiría añadir una
  tabla con una migración posterior.
- Las migraciones las ejecuta el operador de forma explícita; el servicio no migra la base de datos
  al arrancar.
- Revertir una migración con datos es una operación destructiva: requiere autorización explícita
  (Principio VII) y queda documentada.
- Dependencias: incremento 0 (Alembic conectado, Compose, CI) e incremento 1 (eventos normalizados y
  seudonimizados); no se aprueban dependencias nuevas sin un ADR.
- Las metas de tiempo de los criterios de éxito son orientativas y se miden en una máquina de
  desarrollo convencional, registrando sus condiciones.
