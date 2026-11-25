# ADR 0005 — Dependencia `scikit-learn` para el modelo de detección

- **Estado:** Aceptada
- **Fecha:** 2026-11-24
- **Contexto:** `specs/004-model-training` (research R1; FR-004-32). SPEC §5.1 fija `IsolationForest` y
  `ColumnTransformer` de scikit-learn, que no estaban en las dependencias aprobadas (ADR 0002). La constitución
  (Principio I) y AGENTS.md (regla 3) exigen aprobar y registrar toda dependencia nueva antes de usarla.

## Decisión

Se añade **`scikit-learn`** (cota `>=1.9,<2`, versión instalada `1.9.1`, fijada por `uv.lock`). Sus dependencias
transitivas entran con ella y quedan fijadas en `uv.lock`: `numpy 2.5.5`, `scipy 1.18.1`, `joblib 1.6.0`,
`threadpoolctl 3.8.0`, `cloudpickle 3.1.3` y `narwhals 2.29.0`. No se añade ninguna otra dependencia directa;
en particular **no** se usa `pandas`: el vector de características se trabaja como arrays de `numpy`.

En `pyproject.toml` se configuran los módulos `sklearn`, `joblib` y `scipy` con `ignore_missing_imports` en mypy,
porque no publican anotaciones de tipos completas; el código propio sigue en modo estricto.

## Alternativas descartadas

- **Implementar Isolation Forest a mano:** más código y más riesgo de errores, y contradice SPEC §5.1.
- **`pandas`:** dependencia grande sin necesidad; `ColumnTransformer` funciona con arrays de objetos y columnas
  por posición.
- **`skops` u ONNX para serializar:** dependencias nuevas no aprobadas, y ONNX no es el pipeline exacto de
  entrenamiento.

## Riesgos y mitigaciones

- **`joblib` serializa con `pickle`:** deserializar un archivo manipulado ejecuta código. Mitigación (ADR 0006): los
  artefactos solo se cargan desde un directorio interno de confianza y **después** de verificar su huella SHA-256
  contra la registrada en la base de datos.
- **Compatibilidad entre versiones:** un modelo entrenado con otra versión de las librerías puede no cargarse o
  puntuar distinto. Cada versión de modelo registra las de scikit-learn, numpy y scipy y la carga las comprueba.
- **Tamaño de la imagen de Docker:** crece con numpy y scipy. Medido al implementar el incremento 4 con
  `docker build`: **263 MB antes y 618 MB después** (+355 MB). Se acepta; si el tamaño importa más adelante se
  puede separar una imagen de entrenamiento de la de la API.

## Consecuencias

- Cualquier otra dependencia nueva requiere un ADR o una enmienda a este.
- Subir la versión mayor de scikit-learn exige reentrenar y registrar un ADR.
