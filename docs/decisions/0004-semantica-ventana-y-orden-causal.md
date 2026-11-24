# ADR 0004 — Semántica de la ventana y del orden causal de las características

- **Estado:** Aceptada
- **Fecha:** 2026-11-24
- **Contexto:** `specs/003-feature-engineering` (clarificaciones de la sesión 2026-11-22, FR-003-07, 09, 12,
  14 y 22; research R3 a R6 y R8). SPEC §4.4 y §4.5 piden calcular las agregadas «solo con eventos conocidos
  hasta el instante del evento puntuado» con una ventana de cinco minutos, y la constitución (Principio III)
  exige que no haya fuga de futuro y que entrenamiento e inferencia usen el mismo pipeline. Esas frases
  admiten varias lecturas; esta decisión fija la que se implementa. Como las decisiones de `docs/decisions/`
  complementan a SPEC.md, no se modifica SPEC.md: esta lectura es **más estricta** que su texto, nunca más laxa.

## Decisiones

| Tema | Decisión | Motivo |
|---|---|---|
| Orden y empates | Orden total `(timestamp UTC, source, event_id)`, el mismo de `read_range` (incremento 2). La historia de un evento incluye los que lo preceden en esa clave más él mismo. Un evento con el mismo instante pero posterior en la clave **no** entra. | SPEC §4.4 dice «timestamp menor o igual». Si entraran los empatados posteriores, el entrenamiento vería un evento que la inferencia, que solo conoce lo ya almacenado, no vería: sesgo entre entrenamiento e inferencia (NFR-04). |
| Tipo de ventana | Deslizante, anclada en el evento puntuado: `(t − 5 min, t]`. El borde inferior es exclusivo. | Sigue el caso principal de SPEC §2 (ráfaga en cinco minutos) sin saltos por cortes de cubo; el resultado no depende del punto del cubo en que cae el evento. |
| Clave de agregación | `(source, IP)` y `(source, usuario)`, sumando todos los hosts de la fuente; `host` no forma parte de la clave. | La fuente fija el significado de «fallo» y de «usuario»; los hosts de una misma fuente se suman para ver una IP que ataca a varios servidores. Cruzar fuentes exigiría un cambio de esquema. |
| Contexto completo | Lo declara quien llama (`history_start`): completo si `t − 5 min ≥ history_start`; nunca se deduce de los datos de entrada. | Es la única regla igual en entrenamiento y en inferencia de un solo evento. |
| Valores ausentes | Las agregadas que dependen de una IP o un usuario ausente valen 0 y el vector incluye `has_ip` y `has_user`. | Forma fija del vector, sin descartar eventos y sin `NaN` (Isolation Forest de scikit-learn no los admite). |

## Alternativas descartadas

- Incluir todos los empatados («menor o igual» literal): fuga potencial entre entrenamiento e inferencia.
- Cubos fijos de cinco minutos: cada cubo reinicia los contadores y parte las ráfagas.
- Agregar por `(source, host, IP)`: diluye la señal de una IP que ataca a varios servidores.
- Deducir el contexto del primer evento de la entrada: no sirve para un evento individual.

## Consecuencias

- Los tests de fuga (`tests/unit/features/test_no_future_leak.py`, `test_ties_order.py`) fijan esta semántica.
- Cambiar cualquiera de estas decisiones cambia el esquema de características: exige subir
  `FEATURE_SCHEMA_VERSION` y un nuevo ADR.
- Se propone aclarar SPEC §4.4/§4.5 en su próxima revisión para recoger estas precisiones.
