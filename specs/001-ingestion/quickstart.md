# Quickstart: validar el incremento 1

Guía de validación; no contiene código de implementación. Contratos: [contracts/](contracts/).

## Requisitos previos
- Incremento 0 instalado: `uv sync --frozen`.
- Una clave de prueba solo en tu terminal: `export PSEUDONYM_KEY="$(openssl rand -hex 32)"` (64 caracteres).

## Escenario 1 — Calidad y tests (todas las historias)
1. `uv run ruff check . && uv run ruff format --check .`
2. `uv run mypy && uv run mypy tests`
3. `uv run pytest -m "not integration"`

**Esperado:** todo pasa; los tests de ingesta no necesitan base de datos ni red.

## Escenario 2 — Lote válido en JSON y en CSV (historia 1)
1. Ingerir `tests/fixtures/ingestion/valid.json` y `valid.csv` con `ingest_file`.
2. **Esperado:** mismos eventos en ambos, 0 rechazados, 0 duplicados; `to_canonical_json()` idéntico
   entre dos ejecuciones.

## Escenario 3 — Rechazos y duplicados (historias 1 y 2)
1. Ingerir `mixed_batch.json` (válidos, inválidos y duplicados).
2. **Esperado:** los válidos aceptados; cada rechazo con posición, código y campo; los duplicados
   contados aparte; `total_records == accepted + rechazos + duplicados`.
3. Buscar en el informe cualquier valor de los fixtures (cadenas centinela): **no debe aparecer ninguno**.

## Escenario 4 — Límites (historia 2)
1. Archivo de más de 10 MB → `BatchRejected("file_too_large")` en menos de 1 s.
2. Lote de 10.001 eventos → `BatchRejected("too_many_events")`, sin procesamiento parcial.
3. Un campo de 257 caracteres → ese registro se rechaza con `field_too_long`; el resto sigue.

## Escenario 5 — Linux auth (historia 3)
1. Ingerir `linux_auth_sample.log` con `start_year=2026` y zona `Europe/Madrid`.
2. **Esperado:** eventos para SSH correcto y fallido, usuario inválido y `sudo` correcto y fallido; el
   comando de `sudo` no aparece en ninguna salida; las líneas ajenas se cuentan en `ignored_lines`.
3. Con `start_year=None` → todas las líneas con `missing_time_context`.
4. `linux_auth_year_rollover.log` (diciembre → enero) → los timestamps de enero son del año siguiente.
5. Ingerir el mismo archivo dos veces → mismos `event_id`.

## Escenario 6 — Normalización (historia 4)
1. `variants.json`: mismas acciones con mayúsculas, espacios y zonas horarias distintas → salida
   idéntica; tipos/acciones desconocidos → `other`; `outcome` desconocido → rechazo.
2. `out_of_order.json` → los eventos anteriores al máximo ya visto, marcados; los demás no.

## Escenario 7 — Seudonimización (historia 5)
1. Mismo usuario → mismo seudónimo; usuarios distintos → distintos; otra clave → otro seudónimo.
2. Sin `PSEUDONYM_KEY` y con usuarios → `PseudonymKeyMissing` y ningún evento.
3. Serializar todas las salidas y los logs capturados y buscar los nombres de usuario: **0 coincidencias**.

## Escenario 8 — Datos sintéticos (historia 6)
1. `generate_synthetic` con la misma semilla dos veces → resultados idénticos; con otra semilla → distintos.
2. Ingerir el resultado → el informe coincide con lo inyectado (duplicados, fuera de orden, categorías nuevas).
3. 100.000 eventos en menos de 60 s; 100.001 → `ValueError`.
4. Revisar que las IPs están en los rangos de documentación y que las etiquetas viven aparte.

## Escenario 9 — Rendimiento (SC-001)
1. Ingerir 10.000 eventos sintéticos y medir el tiempo. **Esperado:** menos de 10 s; registrar la medida real.
