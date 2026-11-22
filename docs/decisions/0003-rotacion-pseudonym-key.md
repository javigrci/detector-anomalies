# ADR 0003 — Rotación de `PSEUDONYM_KEY`

- **Estado:** Aceptada
- **Fecha:** 2026-11-22
- **Contexto:** `specs/002-persistence` (FR-002-27, historia 6, research R12). Es una decisión pendiente
  del incremento 1: `PSEUDONYM_KEY` seudonimiza el usuario de cada evento y deriva los `event_id` del
  adaptador de Linux auth con HMAC. Hay que fijar qué ocurre al cambiarla antes de que existan datos
  reales almacenados.

## Decisión

**Hay una única clave de seudonimización durante la vida de los datos.** Los eventos no guardan
ninguna versión ni identificador de la clave con la que se seudonimizaron. Rotar la clave exige purgar
antes los datos seudonimizados con la clave anterior, o aceptar de forma explícita que el
comportamiento por usuario queda partido.

## Efecto de rotar la clave

1. **Seudónimos.** Cambian: el mismo usuario recibe un `user_pseudonym` distinto con la clave nueva. Los
   eventos antiguos y los nuevos del mismo usuario dejan de poder agruparse por usuario.
2. **Identificadores del adaptador de Linux auth.** Los `event_id` derivados con HMAC cambian también.
3. **Idempotencia al reingerir.** Reingerir el mismo `auth.log` tras rotar **no es idempotente**: los
   identificadores son nuevos, así que los eventos se insertan como eventos distintos de los ya
   almacenados (duplicados lógicos con otra identidad).
4. **No se puede reseudonimizar.** El nombre de usuario original no se guarda en ninguna parte (Principio
   IV), así que los datos ya almacenados no se pueden recalcular con la clave nueva.

## Procedimiento para rotar

1. Detener la ingesta.
2. Purgar los eventos seudonimizados con la clave anterior (purga explícita con el rol de
   mantenimiento; ver `contracts/operations.md`), **o** aceptar explícitamente y por escrito que el
   comportamiento por usuario queda partido en dos tramos.
3. Sustituir `PSEUDONYM_KEY` por la nueva (≥ 32 caracteres aleatorios, solo en variables de entorno).
4. Reanudar la ingesta y, si hace falta, reingerir desde la fuente original.

## Coste

Se pierde el histórico por usuario anterior a la rotación. Los modelos entrenados con características
por usuario basadas en el histórico anterior deben reentrenarse. Con la retención de 90 días por
defecto (decisión D8) el coste máximo queda acotado a ese horizonte.

## Alternativas descartadas

- **Guardar una versión de clave en cada evento:** permitiría convivir con varias claves, pero exigiría
  una columna, una migración y custodiar varias claves a la vez. No se justifica antes de tener datos reales.
- **Guardar el nombre original cifrado para poder reseudonimizar:** contradice la minimización de datos
  (Principio IV) y convierte la base de datos en un almacén de identificadores personales.

## Evolución

Si en el futuro hiciera falta rotar sin perder historia, se añadiría una columna de versión de clave
con una migración y un cambio de contrato, mediante un nuevo ADR.

## Consecuencias

El comportamiento observable queda cubierto por `tests/integration/storage/test_key_rotation.py`: el
mismo archivo ingerido con dos claves inserta dos veces, y tras purgar antes de rotar solo quedan los
eventos con la clave nueva.
