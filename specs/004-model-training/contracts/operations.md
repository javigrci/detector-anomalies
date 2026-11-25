# Contrato de operación: migración, permisos y CLI

## Migración

```bash
alembic upgrade head        # con MIGRATION_DATABASE_URL (rol anomaly_migrator); aplica 0002_create_ml_tables
```

- Crea `training_runs` y `model_versions` con sus `CHECK` e índices únicos parciales y concede al rol
  `anomaly_app` los permisos de `data-model.md` (sin `DELETE`; `UPDATE` solo por columna).
- Aplicarla dos veces no cambia nada. `downgrade` se niega si hay filas salvo con `-x destructive=yes`.

## CLI de operación

```bash
python -m security_anomaly.ml train --start 2026-01-01T00:00:00+00:00 --end 2026-02-01T00:00:00+00:00 \
        [--history-start ISO] [--labels etiquetas.json] [--n-estimators N]
python -m security_anomaly.ml status [--run ID]
python -m security_anomaly.ml list
python -m security_anomaly.ml activate v0003 --approve
```

| Subcomando | Variables necesarias | Qué hace |
|---|---|---|
| `train` | `DATABASE_URL`, `MODEL_DIR` (+ opcionales de `environment.md`) | Entrena, evalúa, guarda y registra una versión; no la activa |
| `status` | `DATABASE_URL` | Estado de un entrenamiento o de todos los recientes (`running`, `succeeded`, `failed`) |
| `list` | `DATABASE_URL` | Versiones registradas y cuál está activa |
| `activate` | `DATABASE_URL`, `MODEL_DIR` | Activa una versión; **exige `--approve`** |

- Salida: **una línea JSON** con recuentos, estados, versiones y códigos; nunca valores de datos, rutas ni
  credenciales.
- Códigos de salida: `0` correcto; `2` configuración o argumentos inválidos (se nombra la variable, no su valor);
  `1` error controlado (solo su `code`).
- `--labels` es un JSON `{event_id: etiqueta}` de tamaño acotado, leído solo como datos.
- `train` marca como `failed` (`stale`) los entrenamientos `running` con latido anterior al límite antes de empezar y
  falla con `training_in_progress` si queda uno vivo.

## Privilegios esperados

| Operación | `anomaly_app` | `anomaly_maint` | `anomaly_migrator` |
|---|---|---|---|
| `SELECT` en `training_runs` y `model_versions` | ✅ | ❌ | ✅ |
| `INSERT` en ambas | ✅ | ❌ | ✅ |
| `UPDATE` de columnas permitidas | ✅ | ❌ | ✅ |
| `UPDATE` de `metrics`, `params`, `artifact_sha256`… | ❌ | ❌ | ✅ |
| `DELETE`, `TRUNCATE`, DDL | ❌ | ❌ | ✅ |
