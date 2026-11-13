# Feature Specification: Base del repositorio

**Feature Branch**: `000-base` (se trabaja en `main`; la carpeta es independiente de la rama)

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Incremento 0 (000-base): esqueleto del proyecto con gestión de dependencias reproducible, estructura de módulos, configuración por entorno, logging estructurado con request_id, endpoints de salud y disponibilidad, entorno contenerizado (API + base de datos), CI con lint, tipos y tests, y tests mínimos de arranque. Sin lógica de negocio, ingesta, ML ni autenticación."

## Clarifications

### Session 2026-11-13

- Q: ¿Qué hace el servicio si la base de datos no responde al arrancar? → A: Arranca igualmente; `/health` responde con éxito y `/ready` indica no disponible hasta que la base de datos responda.
- Q: ¿Qué debe comprobar la verificación automática (CI)? → A: Lint, formato, tipos y tests unitarios, más los tests contra una PostgreSQL 16 real y una prueba de humo que levanta el entorno completo y consulta `/health` y `/ready`.
- Q: ¿Incluye el incremento 0 la herramienta de migraciones de base de datos? → A: Sí, configurada y conectada a la base de datos, sin ninguna migración de negocio.

## User Scenarios & Testing *(mandatory)*

Los "usuarios" de este incremento son **desarrolladores** (quien clona el repositorio y trabaja en los
incrementos siguientes) y **operadores** (quien levanta y supervisa el servicio). No hay usuarios
finales ni funcionalidad de negocio todavía.

### User Story 1 - Levantar el entorno completo desde cero (Priority: P1)

Un desarrollador clona el repositorio en una máquina limpia, copia el archivo de ejemplo de
configuración y ejecuta un único comando para arrancar el servicio y su base de datos.

**Why this priority**: sin un entorno reproducible no se puede desarrollar ni verificar ningún
incremento posterior (Principio VI de la constitución, NFR-01).

**Independent Test**: en un entorno limpio con solo Docker disponible, ejecutar el comando de
arranque documentado y comprobar que el servicio responde a las sondas de salud sin pasos manuales
adicionales.

**Acceptance Scenarios**:

1. **Given** un clon limpio con la configuración de ejemplo copiada, **When** se ejecuta el comando
   de arranque con construcción, **Then** el servicio y la base de datos quedan en ejecución y el
   servicio responde a la sonda de salud.
2. **Given** el entorno en ejecución, **When** se detiene y se vuelve a arrancar, **Then** el servicio
   vuelve a estar disponible sin intervención manual.
3. **Given** el entorno en ejecución y la herramienta de migraciones configurada, **When** se ejecuta
   el comando de migraciones documentado, **Then** conecta con la base de datos, termina con éxito y
   no crea ninguna tabla de negocio.
4. **Given** una configuración obligatoria ausente o inválida, **When** arranca el servicio, **Then**
   falla de inmediato con un mensaje que indica qué variable falta, sin revelar valores secretos.

---

### User Story 2 - Comprobar el estado del servicio (Priority: P1)

Un operador o un orquestador consulta si el proceso está vivo y si el servicio está listo para
recibir tráfico (base de datos accesible).

**Why this priority**: es el contrato mínimo de operación (NFR-09) y la base sobre la que se añadirá
la comprobación del modelo activo en incrementos posteriores.

**Independent Test**: consultar las dos sondas con la base de datos disponible y con la base de datos
detenida, y comparar las respuestas.

**Acceptance Scenarios**:

1. **Given** el proceso en ejecución, **When** se consulta la sonda de salud, **Then** responde con
   éxito sin depender de la base de datos.
2. **Given** la base de datos accesible, **When** se consulta la sonda de disponibilidad, **Then**
   responde con éxito e indica el estado de la base de datos.
3. **Given** la base de datos no accesible, **When** se consulta la sonda de disponibilidad, **Then**
   responde con un estado de servicio no disponible y un error controlado, sin detalles internos.
4. **Given** la base de datos no disponible en el momento de arrancar, **When** arranca el servicio,
   **Then** el proceso arranca igualmente, la sonda de salud responde con éxito y la de
   disponibilidad indica no disponible hasta que la base de datos responda.
5. **Given** cualquiera de las sondas, **When** se consulta sin credenciales, **Then** responde (son
   públicas por diseño, SPEC §6).

---

### User Story 3 - Verificar calidad automáticamente (Priority: P2)

Un desarrollador abre un cambio y el repositorio ejecuta automáticamente el lint, la comprobación de
tipos y los tests, y bloquea la integración si alguno falla. Las mismas comprobaciones pueden
ejecutarse en local con comandos documentados.

**Why this priority**: es la puerta de calidad de la constitución (Principio V, NFR-02); se necesita
antes de añadir código real, pero no impide arrancar el entorno.

**Independent Test**: introducir deliberadamente un error de estilo, de tipos y un test fallido y
comprobar que cada uno hace fallar la verificación; con el código correcto, comprobar que pasa.

**Acceptance Scenarios**:

1. **Given** un cambio sin errores, **When** se ejecuta la verificación automática, **Then** lint,
   formato, tipos, tests unitarios, tests con base de datos real y la prueba de humo del entorno
   completo pasan y se informa del resultado real.
2. **Given** un cambio con un error de lint, de tipos o un test fallido, **When** se ejecuta la
   verificación, **Then** falla e identifica la comprobación y el archivo afectados.
3. **Given** un clon limpio, **When** se instalan las dependencias con el comando documentado,
   **Then** el entorno resultante es idéntico al fijado en el archivo de bloqueo.

---

### User Story 4 - Trazar cada petición en los logs (Priority: P2)

Un operador necesita relacionar una respuesta con sus líneas de log. Cada petición recibe un
identificador de correlación y todos los registros de la aplicación son estructurados.

**Why this priority**: trazabilidad y observabilidad (NFR-09, Principio IV) que los incrementos
posteriores reutilizan en sus errores y auditoría.

**Independent Test**: enviar peticiones con y sin identificador de correlación y comprobar los logs y
las cabeceras de respuesta.

**Acceptance Scenarios**:

1. **Given** una petición sin identificador de correlación, **When** se procesa, **Then** el sistema
   genera uno, lo devuelve en la respuesta y lo incluye en los registros de esa petición.
2. **Given** una petición con identificador de correlación válido, **When** se procesa, **Then** el
   sistema lo conserva y lo propaga a la respuesta y a los logs.
3. **Given** una petición con un identificador malformado o excesivamente largo, **When** se procesa,
   **Then** se descarta y se genera uno nuevo.
4. **Given** cualquier registro de la aplicación, **When** se emite, **Then** es legible por máquina
   y no contiene secretos ni datos personales.

---

### User Story 5 - Orientarse en la estructura del proyecto (Priority: P3)

Un desarrollador encuentra la estructura de módulos acordada, vacía de lógica de negocio, y un
README que explica cómo arrancar, verificar y contribuir.

**Why this priority**: reduce fricción en los incrementos 1–5, pero no bloquea el arranque ni la
calidad.

**Independent Test**: seguir el README en un clon limpio y comprobar que cada comando documentado
funciona.

**Acceptance Scenarios**:

1. **Given** el repositorio recién clonado, **When** se revisa su estructura, **Then** existen los
   módulos acordados (`api`, `core`, `ingestion`, `features`, `ml`, `scoring`, `storage`, `schemas`)
   como paquetes importables.
2. **Given** el README, **When** se siguen sus pasos, **Then** se consigue arrancar, verificar y
   detener el entorno sin información adicional.

---

### Edge Cases

- El puerto de la API o de la base de datos ya está ocupado en la máquina del desarrollador.
- La base de datos tarda en estar lista al arrancar: el servicio arranca igualmente, no se declara
  disponible (`/ready`) hasta que la base de datos responde y no requiere reinicio manual.
- La base de datos se detiene con el servicio ya en ejecución: la sonda de disponibilidad debe
  reflejarlo en la siguiente consulta, sin reiniciar.
- Variables de entorno con valores vacíos, mal formados o con espacios.
- Se intenta versionar un archivo de configuración con secretos reales: debe quedar excluido del
  repositorio.
- Un identificador de correlación con caracteres de control o inyección de saltos de línea.
- El archivo de bloqueo de dependencias no coincide con la definición de dependencias.
- Un secreto aparece en una variable de entorno: no debe imprimirse en logs ni en errores.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-000-01**: El repositorio MUST poder instalarse en un entorno limpio con un único comando
  documentado, que reproduzca exactamente las dependencias fijadas en un archivo de bloqueo versionado.
- **FR-000-02**: El repositorio MUST incluir la estructura de paquetes acordada en SPEC §3.2
  (`api`, `core`, `ingestion`, `features`, `ml`, `scoring`, `storage`, `schemas`) sin lógica de
  negocio, ingesta, ML ni autenticación.
- **FR-000-03**: La configuración MUST leerse de variables de entorno, con valores por defecto
  seguros para desarrollo, validación al arrancar y mensajes de error que nombren la variable
  incorrecta sin mostrar su valor.
- **FR-000-04**: El repositorio MUST incluir un archivo de ejemplo de configuración con todas las
  variables, sin secretos reales, y MUST excluir de Git los archivos de configuración reales.
- **FR-000-05**: Todos los registros de la aplicación MUST ser estructurados y legibles por máquina, e
  incluir marca de tiempo, nivel, mensaje y el identificador de petición cuando exista.
- **FR-000-06**: Cada petición MUST tener un identificador de correlación: se acepta el recibido si es
  válido (formato y longitud acotados), si no se genera uno; se devuelve en la respuesta y se
  incluye en los registros de la petición.
- **FR-000-07**: El servicio MUST exponer una sonda de salud (`/health`) que indique que el proceso
  está vivo sin depender de ningún componente externo.
- **FR-000-08**: El servicio MUST exponer una sonda de disponibilidad (`/ready`) que compruebe la
  accesibilidad de la base de datos y responda con estado de no disponible y un error controlado
  si no lo está. La comprobación del modelo activo queda para el incremento 5. El servicio MUST
  arrancar aunque la base de datos no esté accesible, sin terminar con error por ese motivo.
- **FR-000-09**: Las sondas `/health` y `/ready` MUST ser públicas y estar fuera del prefijo
  `/api/v1` (SPEC §6).
- **FR-000-10**: Los errores MUST seguir el formato consistente de SPEC §6.2 (`code`, `message`,
  `request_id`, `details` seguros), incluidos los de rutas inexistentes y los de fallo interno.
- **FR-000-11**: El repositorio MUST permitir arrancar el servicio y una base de datos PostgreSQL 16
  con un único comando, a partir de la configuración de ejemplo.
- **FR-000-12**: El entorno contenerizado MUST ejecutar el servicio sin privilegios de administrador
  y sin incluir secretos en la imagen.
- **FR-000-13**: El repositorio MUST ofrecer comandos documentados que ejecuten en local lint,
  formato, comprobación de tipos y tests, y que fallen si cualquiera falla. La verificación
  automática equivalente y su alcance se definen en FR-000-18.
- **FR-000-14**: El repositorio MUST incluir tests mínimos que verifiquen: arranque del servicio,
  respuestas de las dos sondas (con y sin base de datos), validación de configuración, generación y
  propagación del identificador de correlación y formato de los errores.
- **FR-000-15**: Los tests MUST ejecutarse sin necesidad de servicios externos para la parte
  unitaria, y la comprobación contra la base de datos real MUST estar claramente separada.
- **FR-000-18**: La verificación automática MUST ejecutar, además de lint, formato, tipos y tests
  unitarios, los tests contra una base de datos PostgreSQL 16 real y una prueba de humo que levante
  el entorno completo con el comando de arranque y compruebe que `/health` y `/ready` responden con
  éxito; el fallo de cualquiera de ellas MUST bloquear la integración.
- **FR-000-16**: El README MUST documentar cómo instalar, configurar, arrancar, verificar y detener
  el entorno, y cómo funcionan las sondas.
- **FR-000-17**: Este incremento MUST NOT introducir endpoints de negocio, modelos de datos,
  migraciones con tablas de negocio, ni dependencias no listadas en SPEC §2.
- **FR-000-19**: El repositorio MUST incluir la herramienta de migraciones configurada y conectada a
  la base de datos del entorno, con un comando documentado que se ejecute con éxito sin ninguna
  migración de negocio. Las tablas y migraciones de negocio llegan en el incremento 2.

### Key Entities

- **Configuración**: conjunto de ajustes del servicio (entorno de ejecución, nivel de log, conexión
  a la base de datos, puertos). Se valida al arrancar; los valores sensibles nunca se muestran.
- **Identificador de petición**: valor de correlación asociado a cada petición, visible en
  respuesta y logs.
- **Estado de sonda**: resultado de las comprobaciones de salud y disponibilidad (vivo, listo,
  componentes y su estado).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un desarrollador con solo el gestor de contenedores instalado consigue un servicio
  operativo siguiendo exclusivamente el README, con un único comando de arranque tras copiar la
  configuración, en menos de 10 minutos desde el clon (sin contar la descarga inicial de imágenes).
- **SC-002**: Tras el arranque, la sonda de salud responde con éxito en menos de 30 segundos y la de
  disponibilidad en menos de 60 segundos, sin pasos manuales.
- **SC-003**: El 100 % de los tests mínimos y de las comprobaciones de lint, formato y tipos pasan en
  el entorno de verificación automática, y cualquier fallo provocado deliberadamente bloquea la
  integración.
- **SC-004**: El 100 % de las respuestas de la API incluyen el identificador de petición y el 100 %
  de los registros de una petición lo contienen.
- **SC-005**: Con la base de datos detenida, la sonda de disponibilidad refleja el fallo en la
  siguiente consulta (menos de 5 segundos) y vuelve a indicar éxito en menos de 30 segundos tras
  recuperarla, sin reiniciar el servicio.
- **SC-006**: Una revisión del repositorio y del historial no encuentra secretos ni valores reales
  de configuración versionados.
- **SC-007**: Dos instalaciones en máquinas distintas a partir del mismo commit producen el mismo
  conjunto de dependencias.

## Assumptions

- Los usuarios de este incremento son desarrolladores y operadores; no hay usuarios finales.
- El stack y la estructura son los fijados por la constitución y SPEC §2 y §3.2; este incremento no
  los modifica.
- Existe un único entorno de ejecución objetivo para el MVP: local mediante contenedores; el
  despliegue completo, el runbook y el E2E son del incremento 7.
- Los valores por defecto de desarrollo (puertos, nivel de log) son seguros y los secretos de la base
  de datos solo se definen en el archivo de configuración local, no versionado.
- La base de datos arranca vacía: la herramienta de migraciones se entrega configurada en este
  incremento, pero las tablas y migraciones de negocio llegan en el incremento 2.
- La autenticación con API key y roles entra en el incremento 5; las sondas son públicas.
- Las metas de tiempo de SC-001 y SC-002 son orientativas y se miden en una máquina de desarrollo
  convencional, registrando sus condiciones.
- La verificación automática se ejecuta en GitHub Actions, ya adoptado en la constitución.
- Dependencias: Docker con Compose en la máquina del desarrollador; acceso a las imágenes y
  paquetes públicos necesarios.
