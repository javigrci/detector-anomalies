# Contrato de datos

Contrato del evento de seguridad y de su ingesta (incremento 1). Fuente de verdad técnica:
[`specs/001-ingestion/`](../specs/001-ingestion/) (spec, modelo de datos y
[contrato de la API](../specs/001-ingestion/contracts/ingestion-api.md)) y SPEC §4. El esquema
JSON está en [`event-v1.schema.json`](../specs/001-ingestion/contracts/event-v1.schema.json).

> Los datos sintéticos y los fixtures validan el comportamiento del software; **no demuestran
> capacidad real de detección** (SPEC §14). Una anomalía no implica un ataque.

## Evento de entrada v1

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `event_id` | string | Sí | 1–256 caracteres, sin caracteres de control. Único por `(source, event_id)` dentro de un lote |
| `timestamp` | ISO 8601 | Sí | Con zona horaria; se convierte a UTC; rango válido `2000-01-01 ≤ t < 2100-01-01` (configurable) |
| `source` | string | Sí | En minúsculas debe cumplir `^[a-z0-9][a-z0-9-]{0,63}$` |
| `event_type` | string | Sí | Catálogo v1; un valor fuera de él se agrupa como `other` |
| `action` | string | Sí | Catálogo v1; un valor fuera de él se agrupa como `other` |
| `outcome` | string | Sí | `success`, `failure` o `unknown` (sin distinguir mayúsculas); otro valor se **rechaza** |
| `username` | string \| null | No | Se seudonimiza con HMAC; nunca sale en claro |
| `source_ip` | string \| null | No | IPv4 o IPv6 válida, sin identificador de ámbito (`%`); se normaliza a forma comprimida |
| `host` | string \| null | No | Se normaliza a minúsculas |

Todos los textos: espacios en los extremos eliminados, Unicode NFC, sin caracteres de control y de
como máximo 256 caracteres (configurable). Las cadenas vacías de los campos opcionales equivalen a
`null`. **Un campo no definido en el esquema rechaza el registro** (no hay `metadata` en este
incremento).

## Catálogo canónico (versión 1)

| Campo | Valores |
|---|---|
| `event_type` | `authentication`, `privilege_escalation`, `other` |
| `action` | `login`, `invalid_user`, `sudo`, `other` |
| `outcome` | `success`, `failure`, `unknown` |

El número de valores distintos por categoría está acotado por el catálogo. Cambiarlo exige subir
`catalog_version`.

## Evento normalizado (salida)

`event_id`, `timestamp` (UTC), `source`, `event_type`, `action`, `outcome`, `user_pseudonym`
(`usr_` + 32 hexadecimales, o `null`), `source_ip`, `host`, `out_of_order` y `position`.
**No contiene el nombre de usuario original.**

## Reglas de ingesta

- **Formatos:** JSON (lista de objetos o JSON Lines) y CSV con cabecera, en UTF-8. Un JSON que no es
  una lista ni líneas de objetos (por ejemplo, un único objeto) se rechaza entero.
- **Límites** (configurables): 10 MB por archivo, 10.000 eventos por lote, 100.000 por dataset
  sintético y 256 caracteres por campo. Un archivo o lote que los supera se rechaza entero, sin
  procesamiento parcial; un campo demasiado largo rechaza solo su registro.
- **Entrada vacía:** un archivo o una lista vacíos son válidos y dan un resultado con 0 registros.
- **Duplicados:** se deduplica por `(source, event_id)` **dentro de cada lote**: se conserva la
  primera aparición y las siguientes se cuentan como duplicados (indicando si su contenido
  difería). No hay estado entre lotes; la idempotencia entre lotes llega con la persistencia.
- **Fuera de orden:** un evento con timestamp anterior al mayor ya aceptado antes en el mismo lote se
  acepta y se marca (sin tolerancia). Los rechazados y los duplicados no actualizan ese máximo.
- **Determinismo:** la misma entrada, política y clave dan siempre el mismo resultado, byte a byte
  (`to_canonical_json()`). El rango de fechas es fijo, no depende de la hora de ejecución.

## Informe de ingesta

`catalog_version`, `total_records`, `accepted`, `rejected`, `rejections`, `duplicates`,
`out_of_order`, `ignored_lines` y `by_code`. Invariante: `total_records = accepted + rejected +
len(duplicates)`. Las posiciones son 1-based. El informe contiene **solo** códigos, nombres de
campo, posiciones y recuentos, nunca valores de entrada.

### Códigos de rechazo de registro

| Código | Causa |
|---|---|
| `missing_field` | falta un campo obligatorio o está vacío |
| `unknown_field` | campo no definido en el esquema (el nombre solo se informa si es `^[A-Za-z0-9_.-]{1,64}$`; si no, `<invalid-name>`) |
| `invalid_type` | tipo de dato incorrecto |
| `invalid_timestamp` | no es ISO 8601 o no tiene zona horaria |
| `timestamp_out_of_range` | fuera del rango válido |
| `invalid_ip` | IP malformada o con identificador de ámbito |
| `invalid_outcome` | `outcome` fuera de `success`/`failure`/`unknown` |
| `invalid_source` | `source` no cumple el formato acotado |
| `field_too_long` | un campo supera la longitud máxima |
| `invalid_characters` | caracteres de control en un campo |
| `invalid_record` | el registro no es un objeto o la fila CSV está mal formada |
| `missing_time_context` | línea de `auth.log` sin el año indicado por el operador |

Un registro rechazado puede tener hasta 5 entradas (una por campo con error) y cuenta como un solo
registro rechazado.

### Códigos de rechazo de lote

`file_too_large`, `too_many_events`, `invalid_encoding`, `invalid_format`, `file_unreadable`,
`not_a_regular_file`.

## Seudonimización

El usuario se sustituye por `usr_` + 32 caracteres hexadecimales de un `HMAC-SHA256` con la clave
`PSEUDONYM_KEY` (mínimo 32 caracteres; se rechaza el marcador `change-me`). El mismo usuario con la
misma clave da siempre el mismo seudónimo; se distinguen mayúsculas y se normaliza Unicode (NFC) y
los espacios. La IP se conserva (los agregados por IP la necesitan). Sin clave y con usuarios que
seudonimizar, la ingesta falla de forma controlada y no emite nada.

Rotar la clave cambia seudónimos e identificadores derivados, así que reingerir los mismos datos
tras rotarla no es idempotente (la política de rotación se decide en el incremento 2).

## Adaptador de Linux auth (`auth.log` clásico)

| Línea | Evento |
|---|---|
| `sshd: Accepted <método> for <usuario> from <ip> port <n>` | `authentication` / `login` / `success` |
| `sshd: Failed <método> for [invalid user ]<usuario> from <ip> port <n>` | `authentication` / `login` / `failure` |
| `sshd: Invalid user <usuario> from <ip>` | `authentication` / `invalid_user` / `failure` |
| `sudo: <usuario> : … COMMAND=…` | `privilege_escalation` / `sudo` / `success` |
| `sudo: <usuario> : N incorrect password attempts …` o `user NOT in sudoers …` | `privilege_escalation` / `sudo` / `failure` |

- Del `sudo` solo se conserva el usuario: el comando, el directorio y el usuario destino se descartan.
- Las demás líneas (PAM, cron, etc.) y las de más de 2.048 caracteres se ignoran y se cuentan en
  `ignored_lines`; no son un error.
- Las fechas de `auth.log` no tienen año ni zona horaria: el operador indica `start_year` (año de la
  primera línea) y la zona horaria (UTC por defecto). El año aumenta cuando el mes de una línea es
  menor que el de la anterior. Sin `start_year`, las líneas reconocidas se rechazan con
  `missing_time_context`. Las horas ambiguas del cambio de horario usan la primera ocurrencia y las
  inexistentes se rechazan. **Limitación:** un archivo no cronológico en el cambio de año se
  interpreta mal.
- Los identificadores son `la-` + 32 hexadecimales de un HMAC (con la clave) de la posición y la
  línea: reingerir el mismo archivo repite los identificadores y líneas idénticas en posiciones
  distintas no colisionan.

## Persistencia (incremento 2)

Tabla `events` en PostgreSQL 16 (ver `specs/002-persistence/data-model.md`). Clave única
`(source, event_id)`.

| Se guarda | No se guarda |
|---|---|
| `source`, `event_id`, `timestamp` (con zona horaria; se devuelve en UTC), `event_type`, `action`, `outcome` | `username` (el nombre original nunca llega a la base de datos) |
| `user_pseudonym` (nulo si el evento no tenía usuario), `source_ip` (`inet`), `host` | `out_of_order` y `position`: son relativos al lote de origen |
| `ingested_at` (la pone la base de datos y no cambia al reguardar) y `batch_id` (identificador del guardado) | Una versión de la clave de seudonimización (se asume una única clave; ver ADR 0003) |

Solo se guardan los eventos válidos; los registros rechazados siguen únicamente en el informe de la
ingesta. Si llega un evento con la misma clave y contenido distinto, se conserva el original y se
contabiliza en `existing_with_different_content`. La retención se cuenta desde `ingested_at`.

## Características (incremento 3)

Vector por evento con el esquema v1 (`specs/003-feature-engineering/contracts/feature-schema.md`; versión y
huella fijadas en `tests/unit/features/test_schema_golden.py`). Identifica al evento con `(source,
event_id)` y `timestamp` fuera de `features`, e incluye `schema_version` y `context_complete`.

| Ámbito | Características |
|---|---|
| Por evento (UTC) | `hour_sin`, `hour_cos` (hora entera, 12 decimales), `day_of_week` (lunes = 0), `event_type`, `action`, `outcome`, `source` |
| Por ventana `(t - 5 min, t]` | `ip_event_count`, `ip_failure_count`, `ip_failure_rate`, `ip_distinct_users` (por `(source, IP)`), `user_distinct_ips` (por `(source, usuario)`) |
| Indicadores | `has_ip`, `has_user` |

Reglas: historia = eventos que preceden al evento en `(timestamp, source, event_id)` más él mismo (los
empatados posteriores no cuentan); el evento puntuado cuenta en su ventana; sin IP o sin usuario, las
agregadas valen 0 y el indicador, 0; los hosts de una misma fuente se suman y `host` no forma parte de
ninguna clave. Los vectores nunca contienen IP, seudónimo, host ni `event_id` como característica. Ver
`docs/decisions/0004-semantica-ventana-y-orden-causal.md`.

## Modelo y versiones (incremento 4)

Dos tablas nuevas (migración `0002`; `specs/004-model-training/data-model.md`): `training_runs` (cada
ejecución: estado `running`, `succeeded` o `failed`, latido, tamaños de los conjuntos, huella del dataset y
versión producida) y `model_versions` (cada versión: esquema de características con versión y huella,
parámetros, métricas, huella del dataset, nombre y huella SHA-256 del artefacto, versiones de las librerías y
si está activa). A lo sumo un entrenamiento `running` y una versión `active`.

| Se guarda | No se guarda |
|---|---|
| Versión, esquema (versión y huella), parámetros, métricas, fechas, huellas y versiones de librerías | IPs, seudónimos, hosts, identificadores de evento ni valores de eventos |
| Un archivo de modelo por versión en el directorio interno `MODEL_DIR` | Archivos de modelo en Git ni en rutas recibidas de usuarios |

La puntuación de anomalía es un **percentil** frente a la calibración (de 0 a 1), no una probabilidad de
ataque. La severidad usa umbrales provisionales (0,80 y 0,95). Ver `docs/decisions/0006-confianza-de-artefactos-y-concurrencia.md`.
