# Research: Ingesta y normalización de logs

Todas las decisiones respetan SPEC §2 y la constitución. No quedan `NEEDS CLARIFICATION`.
**No se añade ninguna dependencia nueva**: todo se resuelve con la biblioteca estándar y las
dependencias ya aprobadas (Pydantic v2).

## R1. Forma de entrega: biblioteca sin interfaz
- **Decisión:** módulos Python reutilizables en `ingestion/` y `schemas/`, sin endpoints ni CLI. Los
  incrementos 2, 4 y 5 los consumen como funciones.
- **Racional:** la spec excluye endpoints, persistencia y autenticación; el Principio VII pide el
  alcance mínimo.
- **Alternativas:** CLI de ingesta (útil para probar a mano, pero no pedida; se puede añadir después).

## R2. Modelos de datos: Pydantic v2
- **Decisión:** `EventV1` (entrada), `NormalizedEvent` (salida) y los modelos del informe son modelos
  Pydantic v2 inmutables. `EventV1` usa `extra="forbid"`, así que un campo desconocido produce error
  de validación → rechazo (FR-001-05).
- **Racional:** Pydantic v2 ya está aprobado y da tipado, validación y serialización a JSON para el
  incremento 5.
- **Saneo de errores:** los errores de Pydantic incluyen `input`; se traducen a pares
  `(campo, código)` descartando `input` y `msg`, igual que en `core/config.py`.
- **Nombres de campos desconocidos (revisión del análisis):** el nombre de un campo también lo
  controla quien envía el log (clave JSON o cabecera CSV) y puede traer texto hostil o datos
  personales. Solo se informa si cumple `^[A-Za-z0-9_.-]{1,64}$`; en otro caso se informa el
  marcador fijo `<invalid-name>`. Se informan como máximo los 5 primeros por registro.

## R3. Códigos de rechazo estables
Códigos en `StrEnum`, uno por causa, usados en el informe, los logs y los tests:

| Código | Causa |
|---|---|
| `missing_field` | falta un campo obligatorio |
| `unknown_field` | campo no definido en el esquema |
| `invalid_type` | tipo de dato incorrecto (p. ej. número donde se espera texto) |
| `invalid_timestamp` | no es ISO 8601 o no tiene zona horaria |
| `timestamp_out_of_range` | fuera del rango válido (FR-001-03) |
| `invalid_ip` | IP malformada (o con identificador de ámbito) |
| `invalid_outcome` | `outcome` fuera de `success`/`failure`/`unknown` |
| `invalid_source` | `source` no cumple el formato acotado |
| `field_too_long` | un campo supera la longitud máxima |
| `invalid_characters` | caracteres de control en un campo |
| `invalid_record` | el registro no es un objeto o la fila CSV está mal formada |
| `missing_time_context` | línea de `auth.log` sin año o zona horaria indicados |

Rechazos de lote (excepción `BatchRejected`): `file_too_large`, `too_many_events`,
`invalid_encoding`, `invalid_format`, `file_unreadable`, `not_a_regular_file`.

## R4. Lectura de archivos
- **Decisión:**
  - Se comprueba el tamaño con `stat` **antes** de leer (SC-007) y se rechaza si supera el límite.
  - Se decodifica en UTF-8 estricto (`utf-8-sig` tolera BOM); un error de decodificación rechaza el
    archivo (`invalid_encoding`).
  - JSON: si el primer carácter no blanco es `[` se parsea como lista; si es `{` se trata como JSON
    Lines (un objeto por línea). Si falla la primera línea no vacía (por ejemplo, un único objeto
    con formato legible, que ocupa varias líneas) → `invalid_format` para el lote entero. Se usa
    `json` de la biblioteca estándar con `parse_constant` que rechaza `NaN`/`Infinity`;
    `RecursionError` o `ValueError` → `invalid_format`.
  - Un archivo vacío (0 bytes), solo con espacios o una lista vacía es una entrada válida y devuelve
    un resultado con 0 registros, sin error.
  - CSV: `csv.DictReader` con cabecera obligatoria; `csv.Error` en una fila → `invalid_record` solo
    para esa fila; columnas de más o de menos → `invalid_record`; columnas desconocidas → `unknown_field`.
  - El número de eventos se cuenta antes de normalizar y, si supera el máximo, se rechaza el lote
    entero (`too_many_events`).
- **Racional:** con 10 MB como máximo, leer en memoria es seguro y más simple que un lector por
  flujo; el tamaño se comprueba antes de leer. Evita cargar archivos arbitrarios.
- **Alternativas:** `ijson`/pandas (dependencias nuevas, innecesarias para 10 MB).

## R5. Normalización
- **Decisión:** por campo, en este orden: (1) quitar espacios en los extremos y normalizar a Unicode
  NFC; (2) rechazar caracteres de categoría `Cc` (control); (3) rechazar longitudes superiores al
  límite; (4) transformar:
  - `timestamp`: `datetime.fromisoformat` exigiendo `tzinfo`; convertir a UTC; comprobar el rango.
  - `source`, `event_type`, `action`, `outcome`: minúsculas; `source` debe cumplir
    `^[a-z0-9][a-z0-9-]{0,63}$`.
  - `event_type` y `action` fuera del catálogo → `other`; `outcome` fuera de su conjunto → rechazo.
  - `source_ip`: `ipaddress.ip_address`, forma comprimida (IPv6 equivalentes dan la misma cadena);
    rechazo si tiene identificador de ámbito (`%`).
  - `host`: minúsculas.
  - Cadenas vacías en campos opcionales → `None`.
- **Catálogo v1:** `event_type ∈ {authentication, privilege_escalation, other}`; `action ∈
  {login, invalid_user, sudo, other}`; versión `catalog_version = 1`, registrada en el informe.
- **Racional:** determinista, sin dependencias de reloj ni de entorno regional (no se usa `locale`).

## R6. Seudonimización y claves
- **Decisión:** `HMAC-SHA256` (`hmac` + `hashlib`) sobre el usuario normalizado (NFC y sin espacios,
  **respetando mayúsculas**, porque en Linux distinguen), con la clave de `PSEUDONYM_KEY`. El seudónimo
  es `usr_` + los 32 primeros caracteres hexadecimales (128 bits).
- **Clave:** secreto de al menos 32 caracteres, tipo `SecretStr`; nunca por defecto. Se rechaza
  (`ConfigError`) una clave que contenga el marcador de ejemplo del repositorio (`change-me`), porque
  el valor de `.env.example` mide más de 32 caracteres y, si alguien lo copiara sin cambiarlo, la
  clave sería pública y los seudónimos reversibles por diccionario. Sin clave y con
  un usuario que seudonimizar, se lanza `PseudonymKeyMissing` y la ingesta no devuelve eventos
  (falla cerrado, FR-001-24).
- **Hallazgo de seguridad:** el identificador de evento del adaptador se deriva del contenido de la
  línea, que incluye el usuario. Un `SHA-256` sin clave permitiría confirmar un usuario adivinado
  probando candidatos (ataque de diccionario) y anularía la seudonimización. Por eso los
  identificadores del adaptador también se derivan con HMAC y la misma clave, con separación de
  dominio (prefijo distinto: `id` frente a `user`).
- **Consecuencia:** rotar la clave cambia seudónimos e identificadores, así que reingerir tras
  rotarla no es idempotente. Queda documentado y la política de rotación se decide en el incremento 2.
- **Alternativas:** `SHA-256` sin clave (vulnerable), `bcrypt`/`argon2` (lentos y con dependencia nueva).

## R7. Adaptador de Linux auth (`auth.log` clásico)
- **Decisión:** expresiones regulares **ancladas** y con cuantificadores acotados (sin
  retroceso catastrófico) para la cabecera syslog y para cuatro mensajes:

| Mensaje | Evento |
|---|---|
| `sshd: Accepted <método> for <user> from <ip> port <n> ssh2` | `authentication` / `login` / `success` |
| `sshd: Failed <método> for [invalid user ]<user> from <ip> port <n> ssh2` | `authentication` / `login` / `failure` |
| `sshd: Invalid user <user> from <ip> [port <n>]` | `authentication` / `invalid_user` / `failure` |
| `sudo: <user> : … COMMAND=…` | `privilege_escalation` / `sudo` / `success` |
| `sudo: <user> : N incorrect password attempts ; …` y `sudo: <user> : user NOT in sudoers ; …` | `privilege_escalation` / `sudo` / `failure` |

- Las líneas de PAM (`pam_unix(sudo:auth)…`) se ignoran para no contar dos veces el mismo `sudo`
  fallido. Del `sudo` solo se guarda el usuario: el comando, el directorio y el usuario destino se
  descartan al leer (FR-001-10).
- **Fecha sin año ni zona:** el operador indica `start_year` (año de la primera línea) y una zona
  horaria (por defecto UTC). El año se incrementa cuando el mes de una línea es menor que el de la
  anterior (diciembre → enero). Las horas ambiguas del cambio de horario usan la primera ocurrencia
  (`fold=0`) y las inexistentes se rechazan con `invalid_timestamp`. **Limitación:** un archivo que
  no sea cronológico en el cambio de año se interpreta mal; se documenta.
- **Identificador:** `la-` + 32 hex de `HMAC(clave, "id" ‖ nº de línea ‖ línea completa)`. El número
  de línea garantiza que líneas idénticas no colisionen y reingerir el mismo archivo repite los
  identificadores.
- **Cabecera de host:** el host sale de la propia línea; `source = "linux-auth"`.
- **Líneas largas:** las superiores a 2.048 caracteres se ignoran y se cuentan aparte, para acotar el
  coste de las expresiones regulares ante entradas hostiles.
- **Zonas horarias:** se usa `zoneinfo`; la imagen `python:3.12-slim` incluye la base de datos (se
  comprobó). No hace falta añadir `tzdata`.

## R8. Informe de ingesta
- **Decisión:** `IngestionResult` (Pydantic, inmutable) con `events`, `report`. `IngestionReport`
  contiene: `total_records`, `accepted`, `rejected` (registros rechazados), `rejections` (posición 1-based, código, campo; hasta 5 por registro), `duplicates`
  (posición y si el contenido difería), `out_of_order` (posiciones), `ignored_lines` (solo adaptador),
  `by_code` (recuento por código) y `catalog_version`. Serialización canónica con claves ordenadas
  para que dos ejecuciones sean idénticas byte a byte (SC-003).
- **Posición:** número de registro desde 1 (elemento de la lista, línea de JSON Lines, fila de datos
  de CSV sin la cabecera, o línea del `auth.log`).
- **Racional:** solo códigos, campos, posiciones y recuentos; nunca valores (FR-001-22).

## R9. Deduplicación y fuera de orden
- **Decisión:** un recorrido único en orden de lectura con `seen: dict[(source, event_id)] → huella`
  y `max_timestamp`. La huella es un `hash` del evento normalizado para saber si el duplicado difería.
  Fuera de orden: `timestamp < max_timestamp` visto antes; se actualiza `max_timestamp` solo con
  eventos aceptados (rechazados y duplicados no cuentan). Sin estado entre lotes (aclaración 1).
- **Racional:** O(n) en tiempo y memoria; determinista.

## R10. Generador sintético
- **Decisión:** `generate_synthetic(config, *, policy=IngestionPolicy()) -> SyntheticDataset` con
  `random.Random(seed)`, usando
  solo `random()` y aritmética propia para elegir (sin `choice`/`shuffle`, cuyas implementaciones
  pueden cambiar entre versiones de Python). Produce eventos en forma de diccionarios del esquema v1
  y una lista de etiquetas aparte. Sin CLI (YAGNI): los tests y los incrementos posteriores lo usan
  como función.
- **Perfiles:** normal (usuarios con horario laboral, pocas IPs por usuario, ≈3 % de fallos), ráfaga
  de fallos (N intentos fallidos en 5 min desde una IP), horario atípico (02:00–04:00 UTC), IP
  ausente; además duplicados, eventos fuera de orden y categorías nuevas.
- **Datos ficticios:** IPs de los rangos de documentación (`192.0.2.0/24`, `198.51.100.0/24`,
  `203.0.113.0/24`, `2001:db8::/32`), usuarios `user001…`, hosts `srv-demo-NN`.
- **Límite:** `n_events` ≤ `policy.max_events_per_dataset` (100.000 por defecto), si no, `ValueError`
  con motivo claro. Así el máximo del dataset se configura en un solo sitio (la política).
- **Ubicación:** `ingestion/synthetic.py`; no se crea un paquete nuevo porque la constitución fija la
  estructura (Restricciones Técnicas); simula una fuente de logs, así que encaja en `ingestion`.
- **Alternativas:** NumPy `Generator` (dependencia innecesaria ahora), Faker (dependencia nueva).

## R11. Configuración de límites y clave
- **Decisión:** `IngestionPolicy` (modelo Pydantic con los valores por defecto de la spec) y
  `Pseudonymizer`, ambos construibles de forma explícita (tests y llamadas) o desde el entorno con
  `from_environ()`. No se amplía `Settings` porque exige `DATABASE_URL` y la ingesta no debe depender
  de la base de datos.
- **Variables:** `INGEST_MAX_FILE_BYTES`, `INGEST_MAX_EVENTS_PER_BATCH`, `INGEST_MAX_EVENTS_PER_DATASET`,
  `INGEST_MAX_FIELD_LENGTH`, `INGEST_TIMESTAMP_MIN`, `INGEST_TIMESTAMP_MAX` y `PSEUDONYM_KEY`. Ver
  [contracts/environment.md](contracts/environment.md).
- **Refactor menor:** el saneo de errores de `core/config.py` se generaliza en una función
  reutilizable (`load_model`) para no duplicarlo; los tests existentes de configuración la cubren.

## R12. Logging
- **Decisión:** un único registro `ingestion_completed` por ingesta con recuentos (aceptados,
  rechazados por código, duplicados, fuera de orden, ignorados) y la duración. Nunca valores de
  entrada ni nombres de usuario; los rechazos individuales solo van en el informe.
- **Racional:** evita inundar los logs con 10.000 rechazos y cumple FR-001-22/25.

## R13. Pruebas
- **Decisión:** tests unitarios por módulo y de extremo a extremo con fixtures en
  `tests/fixtures/ingestion/` (JSON, CSV, líneas de `auth.log`, archivos inválidos). Pruebas de
  propiedades sencillas sin dependencia nueva: bucles con el generador y distintas semillas.
  Tests de "no fuga": las salidas se serializan y se comprueba que no contienen ninguna cadena
  centinela (usuario, valor rechazado, comando de `sudo`).
- **Rendimiento (SC-001):** un test con 10.000 eventos y umbral de 10 s, medido y registrado.
