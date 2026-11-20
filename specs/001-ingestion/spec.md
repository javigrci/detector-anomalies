# Feature Specification: Ingesta y normalización de logs

**Feature Branch**: `001-ingestion` (se trabaja en `main`; la carpeta es independiente de la rama)

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Incremento 1 (001-ingestion): ingesta y normalización de logs de auditoría, como lógica reutilizable y probada con fixtures, sin persistencia. Esquema de evento v1, lectura de JSON y CSV, adaptador Linux auth, normalización determinista, política de calidad y límites, resultado de ingesta por lote (válidos, rechazados, duplicados), generador de eventos sintéticos reproducibles y seudonimización del usuario. Sin base de datos, sin endpoints, sin autenticación, sin ML ni features por ventana."

## Clarifications

### Session 2026-11-13

- Q: ¿Qué política se aplica a los campos no definidos en el esquema? → A: Rechazar el registro, con un motivo que nombra el campo desconocido; no hay campo `metadata` en este incremento.
- Q: ¿Qué formatos de origen de Linux auth se soportan en este incremento? → A: Solo `auth.log` clásico (syslog); otros formatos (journald) quedan para adaptadores posteriores.
- Q: ¿Qué alcance tiene la deduplicación cuando una carga se divide en varios lotes? → A: Solo dentro de cada lote; entre lotes la resuelve la persistencia del incremento 2.
- Q: ¿Qué rango de fechas es válido para el timestamp? → A: Un rango fijo y configurable, independiente del reloj (por defecto de 2000-01-01 a 2100-01-01); fuera de él el registro se rechaza.
- Q: ¿Se soportan los `sudo` fallidos en el adaptador de Linux auth? → A: Sí: `sudo` correcto (`success`) y fallido (`failure`, por contraseña incorrecta o falta de permiso); otros comandos de privilegios (`su`, `pkexec`) quedan fuera.
- Q: ¿Respecto a qué se mide que un evento está fuera de orden? → A: Un evento está fuera de orden si su timestamp es anterior al mayor timestamp visto antes que él en el mismo lote, según el orden de lectura; sin tolerancia y sin estado entre lotes.
- Q: ¿Se reproduce siempre el nombre de un campo desconocido en el motivo de rechazo? → A: Solo si es un identificador seguro (`^[A-Za-z0-9_.-]{1,64}$`); en otro caso se informa un marcador fijo (`<invalid-name>`), porque el nombre de un campo también es entrada no confiable (revisión del análisis).
- Q: ¿Qué ocurre con un archivo o una lista vacíos? → A: Son una entrada válida y devuelven un resultado con 0 registros, sin error.

## User Scenarios & Testing *(mandatory)*

Los "usuarios" de este incremento son el **administrador técnico** (carga archivos de log y revisa
el resultado) y el **desarrollador / ingeniero de ML** (usa los fixtures y el generador sintético
para probar y, más adelante, entrenar). Todavía no hay interfaz pública: la capacidad se entrega
como lógica reutilizable que los incrementos 2 (persistencia), 4 (entrenamiento) y 5 (API)
consumirán.

### User Story 1 - Cargar un lote de eventos y obtener un informe fiable (Priority: P1)

Un administrador entrega un archivo con eventos de seguridad en el esquema documentado (JSON o
CSV). El sistema devuelve los eventos válidos ya normalizados y un informe con cuántos se
aceptaron, cuáles se rechazaron (posición y motivo) y cuántos duplicados se omitieron.

**Why this priority**: es el valor central del incremento (US-01 de SPEC §11) y la base de todo lo
demás: sin un lote fiable no hay features ni modelo.

**Independent Test**: ingerir un archivo de fixtures que mezcla eventos válidos, inválidos y
duplicados y comparar el informe con el resultado esperado documentado.

**Acceptance Scenarios**:

1. **Given** un archivo JSON con eventos válidos, **When** se ingiere, **Then** todos aparecen como
   válidos y normalizados, y el informe indica 0 rechazados y 0 duplicados.
2. **Given** un archivo CSV equivalente al anterior, **When** se ingiere, **Then** el resultado es
   idéntico al del JSON.
3. **Given** un lote con eventos válidos y otros con errores, **When** se ingiere, **Then** los
   válidos se aceptan, los inválidos se informan con su posición y motivo, y el lote no se
   descarta entero (decisión D6).
4. **Given** un lote con dos eventos con la misma pareja (origen, identificador), **When** se
   ingiere, **Then** se conserva la primera aparición y la segunda se cuenta como duplicado
   omitido, no como error.
5. **Given** el mismo archivo ingerido dos veces, **When** se comparan los resultados, **Then** los
   eventos y sus identificadores son idénticos.

---

### User Story 2 - Rechazar entradas inválidas sin exponer datos (Priority: P1)

Un administrador carga logs con errores (fechas inválidas, campos obligatorios ausentes, valores
fuera de rango, campos demasiado largos) o supera los límites de tamaño. El sistema rechaza lo
inválido con un motivo claro que nunca reproduce el contenido sospechoso ni datos personales.

**Why this priority**: la entrada es no confiable (Principio IV de la constitución); sin esta
política, un log hostil o corrupto contamina el resto del sistema.

**Independent Test**: ingerir fixtures con cada tipo de error y comprobar que el motivo es el
esperado y que ninguna parte del valor recibido aparece en el informe ni en los registros.

**Acceptance Scenarios**:

1. **Given** un evento con timestamp inválido o sin zona horaria, **When** se ingiere, **Then** se
   rechaza con un motivo que identifica el campo y el tipo de error, sin el valor recibido.
2. **Given** un evento sin alguno de los campos obligatorios, **When** se ingiere, **Then** se
   rechaza indicando qué campos faltan.
3. **Given** un evento con una IP malformada o un `outcome` fuera del conjunto permitido, **When**
   se ingiere, **Then** se rechaza con el motivo correspondiente.
4. **Given** un campo de texto que supera la longitud máxima, **When** se ingiere, **Then** el
   evento se rechaza (no se trunca en silencio).
5. **Given** un archivo que supera el tamaño máximo, **When** se intenta ingerir, **Then** se
   rechaza entero y de inmediato con un motivo claro.
6. **Given** un lote con más eventos que el máximo permitido, **When** se intenta ingerir, **Then**
   se rechaza el lote completo con un motivo claro (no se procesa parcialmente).
7. **Given** un registro con contenido que parece una instrucción (por ejemplo, un comando o una
   orden dirigida a un asistente), **When** se ingiere, **Then** se trata únicamente como dato:
   nunca se interpreta ni se ejecuta.

---

### User Story 3 - Convertir logs reales de Linux a eventos del esquema (Priority: P2)

Un administrador entrega un archivo de autenticación de Linux (inicios de sesión SSH correctos y
fallidos, usuarios inválidos y uso de `sudo`) y el sistema lo convierte en eventos del esquema v1.

**Why this priority**: es el primer formato real acordado (decisión D4); los datos sintéticos
validan el software, pero este adaptador conecta el sistema con logs reales.

**Independent Test**: convertir un conjunto de líneas de ejemplo documentadas y comprobar que cada
una produce el evento esperado, que las no relacionadas se ignoran y que ninguna línea
sospechosa rompe el proceso.

**Acceptance Scenarios**:

1. **Given** una línea de inicio de sesión SSH correcto, **When** se convierte, **Then** produce un
   evento de autenticación con `outcome` `success`, el usuario, la IP de origen y el host.
2. **Given** una línea de inicio de sesión SSH fallido (con usuario válido o inválido), **When** se
   convierte, **Then** produce un evento con `outcome` `failure`.
3. **Given** una línea de usuario inválido, **When** se convierte, **Then** produce un evento con
   la acción correspondiente y `outcome` `failure`.
4. **Given** una línea de uso correcto de `sudo`, **When** se convierte, **Then** produce un evento
   de elevación de privilegios con `outcome` `success`, sin conservar el comando ejecutado.
5. **Given** una línea de `sudo` fallido (contraseña incorrecta o usuario sin permiso), **When** se
   convierte, **Then** produce un evento de elevación de privilegios con `outcome` `failure`, sin
   conservar el comando.
6. **Given** líneas que no corresponden a ningún evento soportado, **When** se convierte, **Then**
   se ignoran y se contabilizan aparte; no se tratan como error.
7. **Given** líneas sin año ni zona horaria en su fecha, **When** se convierten con el año y la
   zona horaria indicados por el operador, **Then** el timestamp resultante es correcto en UTC, incluido
   el cambio de año entre diciembre y enero.
8. **Given** líneas sin año ni zona horaria y sin esa información del operador, **When** se
   convierten, **Then** se rechazan con un motivo claro (no se adivinan).
9. **Given** dos líneas idénticas en instantes y posiciones distintos (por ejemplo, fallos
   repetidos), **When** se convierten, **Then** producen dos eventos con identificadores
   distintos, y reingerir el mismo archivo produce los mismos identificadores.

---

### User Story 4 - Normalización determinista y categorías acotadas (Priority: P2)

El sistema normaliza todos los eventos para que dos entradas equivalentes produzcan exactamente la
misma salida y para que el número de categorías posibles esté acotado, sin importar qué valores
arbitrarios lleguen.

**Why this priority**: las features del incremento 3 y el modelo del 4 dependen de datos
consistentes; sin esto, las mismas acciones aparecen con nombres distintos y las categorías
crecen sin control.

**Independent Test**: ingerir el mismo contenido con variaciones de formato (mayúsculas, zonas
horarias, valores ausentes) y comprobar que la salida normalizada es idéntica; ingerir categorías
desconocidas y comprobar que se agrupan.

**Acceptance Scenarios**:

1. **Given** timestamps con distintas zonas horarias que representan el mismo instante, **When** se
   normalizan, **Then** todos quedan en UTC y son idénticos.
2. **Given** valores de tipo de evento, acción o resultado con variaciones de mayúsculas o
   espacios, **When** se normalizan, **Then** quedan en su forma canónica.
3. **Given** un tipo de evento o acción que no figura en el catálogo, **When** se normaliza,
   **Then** se agrupa bajo la categoría `other`.
4. **Given** campos opcionales ausentes (usuario, IP, host), **When** se normaliza, **Then** se
   representan siempre de la misma forma determinista.
5. **Given** un lote en el que un evento tiene un timestamp anterior al mayor ya visto en ese lote,
   **When** se ingiere, **Then** el evento se acepta (decisión D5) y se marca como fuera de orden
   en el informe; los eventos en orden no se marcan.
6. **Given** un registro con un campo no definido en el esquema, **When** se ingiere, **Then** se
   rechaza con un motivo que nombra el campo desconocido (sin su valor) y, en ningún caso, el campo
   pasa a las características del modelo.

---

### User Story 5 - Proteger la identidad del usuario (Priority: P2)

El identificador de usuario que aparece en los logs se sustituye por un seudónimo estable antes de
que el evento salga del módulo de ingesta, de modo que el comportamiento por usuario siga siendo
analizable sin conservar el nombre real.

**Why this priority**: privacidad por diseño (Principio IV, decisión D8); el almacenamiento del
incremento 2 ya debe recibir datos seudonimizados.

**Independent Test**: ingerir eventos con usuarios conocidos y comprobar que el mismo usuario
produce siempre el mismo seudónimo, que usuarios distintos producen seudónimos distintos y que el
nombre real no aparece en ninguna salida, informe ni registro.

**Acceptance Scenarios**:

1. **Given** el mismo usuario en varios eventos, **When** se ingieren, **Then** todos reciben el
   mismo seudónimo.
2. **Given** dos usuarios distintos, **When** se ingieren, **Then** reciben seudónimos distintos.
3. **Given** una clave secreta de seudonimización distinta, **When** se ingiere el mismo usuario,
   **Then** el seudónimo es distinto (no se puede reconstruir sin la clave).
4. **Given** que no hay clave configurada, **When** se ingieren eventos con usuario, **Then** el
   proceso falla de forma controlada y nunca produce el nombre en claro.
5. **Given** cualquier salida o registro de la ingesta (eventos, informe, rechazos, logs),
   **When** se inspecciona, **Then** no contiene el nombre de usuario original.

---

### User Story 6 - Generar datos sintéticos reproducibles (Priority: P3)

Un desarrollador genera un conjunto de eventos sintéticos estilo Linux auth, con perfiles normales
y anomalías inyectadas, a partir de una semilla, para usarlo como fixtures y, más adelante, como
dataset de entrenamiento y evaluación.

**Why this priority**: habilita las pruebas de todos los incrementos y el primer dataset (SPEC
§15), pero el sistema funciona sin él.

**Independent Test**: generar dos veces con la misma semilla y comprobar que el resultado es
idéntico; ingerirlo y comprobar que la composición coincide con la configurada.

**Acceptance Scenarios**:

1. **Given** una semilla y una configuración, **When** se genera dos veces, **Then** los resultados
   son idénticos.
2. **Given** semillas distintas, **When** se generan, **Then** los resultados difieren.
3. **Given** el conjunto generado, **When** se ingiere, **Then** los eventos válidos cumplen el
   esquema y el informe coincide con lo inyectado (duplicados, fuera de orden, categorías nuevas).
4. **Given** perfiles de anomalía inyectada (ráfaga de fallos desde una IP, actividad en horario
   atípico, IP ausente), **When** se genera, **Then** cada anomalía queda identificada en un
   registro de etiquetas separado de los eventos, para poder evaluar más adelante.
5. **Given** una petición de más eventos que el máximo del dataset, **When** se genera, **Then**
   se rechaza con un motivo claro.
6. **Given** el conjunto generado, **When** se revisa, **Then** no contiene datos reales: usuarios,
   hosts e IPs son ficticios (rangos de documentación para las IPs).

---

### Edge Cases

- Archivo vacío (0 bytes) o lista vacía: entrada válida con resultado de 0 registros, sin error.
- Archivo inexistente, sin permisos de lectura o que no es un archivo regular: rechazo del lote.
- Codificación de caracteres inválida, presencia de BOM o caracteres de control en los campos.
- JSON que no es una lista de eventos ni líneas de eventos (por ejemplo, un único objeto con
  formato legible), o con elementos que no son objetos.
- CSV sin cabecera, con columnas desconocidas, con filas de distinto número de columnas o con
  campos entrecomillados que contienen saltos de línea.
- Timestamps fuera del rango válido (por ejemplo, el año 0001 o el 9999): se rechazan con motivo
  `fuera de rango`, y un timestamp "del futuro" respecto a la hora actual no se rechaza si está
  dentro del rango.
- IPv6 en formatos equivalentes (abreviada o completa) que deben normalizarse igual.
- Mismo `(origen, identificador)` con contenido distinto: se conserva la primera aparición y la
  segunda se cuenta como duplicado, indicando que su contenido difería.
- Un lote en el que todos los registros son inválidos: el informe lo refleja sin error global.
- El mismo `(origen, identificador)` en lotes distintos de una misma carga: este incremento no lo
  detecta; la idempotencia entre lotes llega con la persistencia (incremento 2).
- Líneas muy largas o con repeticiones masivas que podrían agotar la memoria.
- Valores con apariencia de instrucciones, rutas o código dirigidos a un asistente o un shell.
- Un registro con muchos campos desconocidos: se rechaza igualmente y el motivo nombra solo los
  primeros (máximo 5), sin crecer sin límite.
- Un campo desconocido cuyo nombre contiene texto hostil, datos personales o caracteres de
  control: el motivo usa el marcador fijo, nunca el nombre recibido.
- Usuario vacío, solo con espacios o con caracteres no imprimibles.
- Cambio de año entre diciembre y enero al interpretar fechas sin año.
- Registros de `sudo` cuyo comando contiene datos sensibles: el comando no se conserva.
- Generación sintética con semilla inválida o con proporciones de anomalías que no suman un
  conjunto coherente.

## Requirements *(mandatory)*

### Functional Requirements

**Esquema y formatos**

- **FR-001-01**: El sistema MUST aceptar eventos que cumplan el esquema v1 de SPEC §4.1 con los
  campos `event_id`, `timestamp`, `source`, `event_type`, `action`, `outcome` obligatorios y
  `username`, `source_ip` y `host` opcionales.
- **FR-001-02**: El sistema MUST leer eventos de archivos JSON (una lista de eventos y líneas de
  eventos) y CSV (con cabecera), con resultados equivalentes para el mismo contenido. Un archivo
  JSON que no sea una lista de objetos ni líneas de objetos (por ejemplo, un único objeto) MUST
  rechazarse completo.
- **FR-001-03**: El `timestamp` MUST ser ISO 8601 con zona horaria y MUST normalizarse a UTC; un
  timestamp sin zona horaria o inválido MUST rechazarse. El rango válido es fijo y configurable
  (por defecto de 2000-01-01 a 2100-01-01) y no depende de la hora de ejecución, de modo que el
  mismo archivo da siempre el mismo resultado; un timestamp fuera de rango MUST rechazarse.
- **FR-001-04**: `outcome` MUST ser uno de `success`, `failure` o `unknown`; `source_ip` MUST ser
  una IPv4 o IPv6 válida cuando exista.
- **FR-001-05**: Un registro con campos no definidos en el esquema MUST rechazarse con un motivo
  que nombra el campo desconocido y MUST NOT incorporarse nunca al vector de características del
  modelo. El nombre del campo solo se informa si es un identificador seguro
  (`^[A-Za-z0-9_.-]{1,64}$`); en otro caso se informa un marcador fijo (`<invalid-name>`), porque
  el nombre de un campo también es entrada no confiable. Este incremento no incluye un campo
  `metadata`.

**Adaptador de Linux auth**

- **FR-001-06**: El sistema MUST convertir al esquema v1 las líneas de `auth.log` clásico (formato
  syslog) de los tipos: inicio de sesión SSH correcto, inicio de sesión SSH fallido, usuario
  inválido y uso de `sudo` correcto o fallido (contraseña incorrecta o falta de permiso). Otros
  comandos de privilegios (`su`, `pkexec`) no se soportan en este incremento. Otros formatos (por ejemplo, journald) quedan fuera de este
  incremento y se añadirán como adaptadores posteriores.
- **FR-001-07**: Las líneas que no correspondan a ningún evento soportado MUST ignorarse y
  contabilizarse aparte, sin considerarlas error.
- **FR-001-08**: Para fechas sin año o sin zona horaria, el sistema MUST usar el año y la zona
  horaria indicados por el operador, MUST resolver correctamente el cambio de año entre diciembre
  y enero y MUST rechazar la línea con un motivo claro si esa información no se ha indicado.
- **FR-001-09**: El adaptador MUST asignar identificadores deterministas derivados del origen, la
  posición del registro y su contenido, de modo que reingerir el mismo archivo produzca los mismos
  identificadores y dos líneas idénticas en posiciones distintas no colisionen.
- **FR-001-10**: Para los eventos de `sudo`, el sistema MUST NOT conservar el comando ejecutado ni
  rutas de trabajo.

**Normalización**

- **FR-001-11**: La normalización MUST ser determinista: la misma entrada produce siempre la misma
  salida, byte a byte, independientemente del orden de los campos o de variaciones de mayúsculas y
  espacios.
- **FR-001-12**: `event_type` y `action` MUST pertenecer a un catálogo canónico y versionado;
  cualquier valor fuera del catálogo MUST agruparse como `other`, de modo que el número de
  categorías posibles sea acotado. `outcome` no se agrupa: se normaliza (mayúsculas y espacios) y,
  si no es `success`, `failure` ni `unknown`, el registro se rechaza (FR-001-04).
- **FR-001-13**: `source` MUST cumplir un formato acotado (letras minúsculas, dígitos y guiones, con
  longitud máxima) y un valor que no lo cumpla MUST rechazarse.
- **FR-001-14**: Los valores ausentes MUST representarse siempre de la misma forma determinista.
- **FR-001-15**: Un evento cuyo timestamp es anterior al mayor timestamp visto antes que él en el
  mismo lote, según el orden de lectura, MUST aceptarse (decisión D5) y MUST señalarse como fuera
  de orden en el informe. La definición es determinista, no usa tolerancia y no mantiene estado
  entre lotes.

**Calidad y límites**

- **FR-001-16**: El sistema MUST rechazar los registros con timestamp inválido, con campos
  obligatorios ausentes o con valores fuera de dominio, y MUST informar el motivo con un código
  estable y el campo afectado, sin reproducir el valor recibido.
- **FR-001-17**: Los límites MUST ser configurables y tener estos valores iniciales: 10 MB por
  archivo, 10.000 eventos por lote, 100.000 eventos por dataset y 256 caracteres por campo de
  texto.
- **FR-001-18**: Un archivo que supere el tamaño máximo, o un lote que supere el número máximo de
  eventos, MUST rechazarse completo con un motivo claro, sin procesamiento parcial; un campo que
  supere la longitud máxima MUST provocar el rechazo de ese registro, sin truncarlo.
- **FR-001-19**: La deduplicación MUST usar la pareja `(source, event_id)` dentro de cada lote:
  conserva la primera aparición y cuenta las siguientes como duplicados omitidos. No se mantiene
  estado entre lotes; la deduplicación entre lotes corresponde a la persistencia (incremento 2).
- **FR-001-20**: El contenido de los logs MUST tratarse únicamente como dato: nunca se interpreta
  como instrucción ni se ejecuta (Principio IV).

**Resultado de ingesta**

- **FR-001-21**: Cada ingesta MUST devolver un resultado con: los eventos válidos y normalizados;
  los rechazados (posición, código de motivo y campo); los duplicados omitidos; las líneas
  ignoradas (adaptador); los eventos fuera de orden; y los recuentos de registros leídos,
  aceptados, rechazados y duplicados, y de rechazos por código.
- **FR-001-22**: El resultado y los registros de la ingesta MUST NOT contener valores de entrada
  sospechosos ni datos personales; solo códigos, campos, posiciones y recuentos.

**Seudonimización**

- **FR-001-23**: El nombre de usuario MUST sustituirse por un seudónimo estable derivado con una
  clave secreta antes de que el evento salga del módulo; el mismo usuario con la misma clave MUST
  dar siempre el mismo seudónimo y claves distintas MUST dar seudónimos distintos.
- **FR-001-24**: La clave MUST obtenerse de la configuración del entorno y nunca del repositorio;
  si no está configurada y hay usuarios que seudonimizar, la ingesta MUST fallar de forma
  controlada, sin emitir nunca el nombre en claro. La clave MUST rechazarse si tiene menos de 32
  caracteres o si contiene el marcador de ejemplo del repositorio (`change-me`).
- **FR-001-25**: El nombre de usuario original MUST NOT aparecer en eventos, informes, motivos de
  rechazo ni logs.

**Datos sintéticos**

- **FR-001-26**: El sistema MUST generar eventos sintéticos estilo Linux auth de forma
  reproducible a partir de una semilla y una configuración (tamaño, perfiles y proporciones).
- **FR-001-27**: El generador MUST incluir perfiles de actividad normal y de anomalías inyectadas
  (ráfaga de fallos desde una IP, horario atípico, IP ausente) y MUST poder añadir duplicados,
  eventos fuera de orden y categorías nuevas.
- **FR-001-28**: El generador MUST producir, aparte de los eventos, un registro de etiquetas que
  identifique qué eventos son anomalías inyectadas y de qué tipo.
- **FR-001-29**: El generador MUST usar solo datos ficticios (IPs de rangos de documentación,
  usuarios y hosts inventados) y MUST NOT superar el máximo de eventos del dataset.
- **FR-001-30**: Este incremento MUST NOT introducir persistencia, endpoints, autenticación,
  features por ventana ni lógica de ML, ni dependencias no aprobadas.

### Key Entities

- **Evento v1**: registro de entrada con los campos del esquema; puede llegar de JSON, CSV o del
  adaptador de Linux auth.
- **Evento normalizado**: evento validado con timestamp en UTC, categorías canónicas, valores
  ausentes representados de forma uniforme, usuario seudonimizado y marca de fuera de orden.
- **Informe de ingesta**: resultado de un lote; contiene eventos válidos, rechazos (posición,
  código y campo), duplicados omitidos, líneas ignoradas y recuentos.
- **Rechazo**: registro de un evento no aceptado, con posición, código de motivo y campo, sin el
  valor recibido.
- **Política de ingesta**: límites configurables (tamaño de archivo, eventos por lote, eventos por
  dataset, longitud de campo) y catálogo de categorías; los campos desconocidos se rechazan.
- **Evento sintético y etiqueta de anomalía**: evento generado con semilla y su etiqueta
  (normal o tipo de anomalía inyectada).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un lote de 10.000 eventos se ingiere y se informa en menos de 10 segundos en una
  máquina de desarrollo convencional.
- **SC-002**: El 100 % de los eventos rechazados en los fixtures de prueba aparece en el informe
  con su posición, código y campo, y en el 100 % de los casos ni el informe ni los logs contienen
  el valor de entrada que causó el rechazo.
- **SC-003**: Ingerir dos veces el mismo contenido produce resultados idénticos en el 100 % de los
  casos, incluidos los identificadores de los eventos.
- **SC-004**: El 100 % de las líneas del conjunto de ejemplo documentado de Linux auth produce el
  evento esperado o es ignorada según lo previsto, y ninguna línea malformada interrumpe el
  proceso.
- **SC-005**: Con la misma semilla y configuración, el generador produce conjuntos idénticos en el
  100 % de las ejecuciones, y un dataset de 100.000 eventos se genera en menos de 60 segundos.
- **SC-006**: En una revisión de todas las salidas de la ingesta sobre los fixtures (eventos,
  informes, rechazos y logs) aparecen 0 nombres de usuario en claro.
- **SC-007**: Un archivo que excede el tamaño máximo se rechaza en menos de 1 segundo con un motivo
  claro.
- **SC-008**: Los eventos con categorías no catalogadas se agrupan en `other` en el 100 % de los
  casos, de modo que el número de valores distintos por categoría nunca supera el tamaño del
  catálogo más uno.

## Assumptions

- Los usuarios son el administrador técnico y el desarrollador / ingeniero de ML; no hay usuarios
  finales ni interfaz pública en este incremento.
- La capacidad se entrega como lógica reutilizable sin endpoints (la API llega en el incremento 5)
  y sin persistencia (el almacenamiento llega en el incremento 2).
- La seudonimización aplica al usuario; la IP se conserva porque las agregaciones por IP la
  necesitan (decisión D8). La retención de 90 días se aplicará en el incremento 2.
- El catálogo canónico inicial cubre autenticación y elevación de privilegios (tipos de evento
  `authentication` y `privilege_escalation`; acciones como `login`, `invalid_user` y `sudo`); todo
  lo demás se agrupa como `other`. Su detalle se fija en el plan.
- Los límites de SPEC §4.3 son valores iniciales configurables; el "dataset" de 100.000 eventos es
  el máximo del conjunto sintético y de un entrenamiento del MVP.
- Se asume un único origen de datos por archivo ingerido.
- Un dataset de más de 10.000 eventos se procesa como varios lotes independientes, cada uno con su
  informe; la deduplicación entre lotes se delega en el incremento 2.
- El adaptador de Linux auth trabaja con `auth.log` clásico, cuyas fechas no incluyen año ni zona
  horaria; por eso el operador debe indicarlos (FR-001-08). La viabilidad de journald y de
  otros formatos se estudia más adelante (roadmap).
- El generador sintético sirve a este incremento (fixtures) y a los incrementos 3 y 4; los
  fixtures y los datos sintéticos validan el comportamiento del software, no la capacidad real de
  detección (SPEC §14).
- Dependencias: incremento 0 completado (proyecto, configuración y CI). La clave de
  seudonimización se añade al contrato de variables de entorno; no se aprueban dependencias nuevas
  sin un ADR.
