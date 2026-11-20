# Contrato: API pública de la ingesta

Interfaz que consumen los incrementos 2 (persistencia), 4 (entrenamiento) y 5 (API). Todo se
importa de `security_anomaly.ingestion`. No hay endpoints ni CLI en este incremento.

## Funciones

```python
ingest_file(path: Path, *, policy: IngestionPolicy, pseudonymizer: Pseudonymizer,
            fmt: Literal["json", "csv"] | None = None) -> IngestionResult
```
Lee un archivo JSON (lista o JSON Lines) o CSV. Con `fmt=None` se deduce de la extensión
(`.json`, `.jsonl`, `.ndjson`, `.csv`); otra extensión → `BatchRejected("invalid_format")`. Un
JSON que no sea una lista de objetos ni líneas de objetos (por ejemplo, un único objeto) →
`BatchRejected("invalid_format")`. Un archivo o una lista vacíos devuelven un resultado con 0
registros, sin error.

```python
ingest_records(records: Iterable[Mapping[str, object]], *, policy: IngestionPolicy,
               pseudonymizer: Pseudonymizer) -> IngestionResult
```
Ingiere registros ya parseados (por ejemplo, de una petición futura de la API o del generador).

```python
ingest_linux_auth(path: Path, *, policy: IngestionPolicy, pseudonymizer: Pseudonymizer,
                  start_year: int | None, tz: tzinfo = UTC) -> IngestionResult
```
Convierte un `auth.log` clásico. `start_year` es el año de la primera línea; si es `None`, las
líneas se rechazan con `missing_time_context`. El comando de `sudo` nunca se conserva.

```python
generate_synthetic(config: SyntheticConfig, *, policy: IngestionPolicy | None = None) -> SyntheticDataset
```
Determinista para una misma `config`. Con `policy=None` se usa la política por defecto. Lanza
`ValueError` si `n_events` supera `policy.max_events_per_dataset` o la configuración es incoherente.
`n_events` es el total de eventos devueltos; las etiquetas van aparte, una por evento único.

## Exportaciones

`security_anomaly.ingestion` exporta exactamente:

- Funciones: `ingest_file`, `ingest_records`, `ingest_linux_auth`, `generate_synthetic`.
- Configuración: `IngestionPolicy`, `Pseudonymizer`, `SyntheticConfig`.
- Resultados: `IngestionResult`, `IngestionReport`, `NormalizedEvent`, `Rejection`, `SyntheticDataset`, `SyntheticLabel`.
- Códigos: `RejectionCode`, `BatchRejectionCode`.
- Excepciones: `IngestionError`, `BatchRejected`, `PseudonymKeyMissing`, `ConfigError`.

## Garantías

- **Determinismo:** misma entrada, política y clave → mismo `IngestionResult` (incluido
  `to_canonical_json()`).
- **Sin valores:** el informe, las excepciones y los logs contienen solo códigos, nombres de campo,
  posiciones y recuentos. El nombre de un campo desconocido solo se informa si cumple
  `^[A-Za-z0-9_.-]{1,64}$`; si no, se informa `<invalid-name>`.
- **Sin estado entre llamadas:** cada llamada es un lote independiente.
- **Orden:** los eventos salen en el orden de lectura.
- **Entrada no confiable:** nunca se evalúa, interpreta ni ejecuta contenido de los datos.

## Excepciones

| Excepción | Cuándo | Atributos |
|---|---|---|
| `BatchRejected` | el archivo o el lote se rechazan enteros | `code`, `limit` (el valor del límite, no del dato) |
| `PseudonymKeyMissing` | hay usuarios que seudonimizar y no hay clave | — |
| `ConfigError` | variables de entorno inválidas (de `from_environ`) o clave de seudonimización corta o igual al marcador `change-me` | mensaje sin valores |

Códigos de lote: `file_too_large`, `too_many_events`, `invalid_encoding`, `invalid_format`,
`file_unreadable`, `not_a_regular_file`.

## Códigos de rechazo de registro

`missing_field`, `unknown_field`, `invalid_type`, `invalid_timestamp`, `timestamp_out_of_range`,
`invalid_ip`, `invalid_outcome`, `invalid_source`, `field_too_long`, `invalid_characters`,
`invalid_record`, `missing_time_context`. Estables: añadir uno es un cambio de contrato.

## Correspondencia con SPEC

- Rechazo de lote por tamaño → `413` en la API del incremento 5.
- `invalid_*` y `missing_*` → `422` con el informe.
- `PseudonymKeyMissing` → `503` controlado.
