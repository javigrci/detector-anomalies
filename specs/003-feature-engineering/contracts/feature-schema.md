# Contrato: esquema de características v1

`FEATURE_SCHEMA_VERSION = 1`. Ventana: **300 s**, deslizante, anclada en el evento puntuado, `(t − 5 min, t]`.
El orden y los nombres son el contrato con el incremento 4. Cualquier cambio exige subir la versión.

| # | Nombre | Tipo | Ámbito | Definición |
|---|---|---|---|---|
| 1 | `hour_sin` | float | evento | `sin(2π·h/24)`, `h` = hora entera UTC, redondeado a 12 decimales |
| 2 | `hour_cos` | float | evento | `cos(2π·h/24)`, ídem |
| 3 | `day_of_week` | int | evento | día de la semana UTC, lunes = 0 … domingo = 6 |
| 4 | `event_type` | category | evento | tipo de evento del catálogo v1 |
| 5 | `action` | category | evento | acción del catálogo v1 |
| 6 | `outcome` | category | evento | resultado del catálogo v1 |
| 7 | `source` | category | evento | fuente del evento |
| 8 | `ip_event_count` | int | ventana | eventos de `(source, ip)` en la ventana, incluido el propio; 0 sin IP |
| 9 | `ip_failure_count` | int | ventana | los de resultado `failure`; 0 sin IP |
| 10 | `ip_failure_rate` | float | ventana | `ip_failure_count / ip_event_count`; 0 sin IP |
| 11 | `ip_distinct_users` | int | ventana | seudónimos distintos no nulos de `(source, ip)`; 0 sin IP |
| 12 | `user_distinct_ips` | int | ventana | IPs distintas no nulas de `(source, usuario)`; 0 sin usuario |
| 13 | `has_ip` | int | indicador | 1 si el evento tiene IP, 0 si no |
| 14 | `has_user` | int | indicador | 1 si el evento tiene usuario, 0 si no |

Reglas:

- Las IPs se comparan por valor (formas equivalentes de IPv6 cuentan como la misma).
- Los usuarios son seudónimos; el nombre original no existe en ninguna parte.
- Los eventos de fuentes distintas no se mezclan; `host` no forma parte de ninguna clave.
- El evento puntuado cuenta como parte de su propia ventana.
- Un evento con IP pero sin usuario aporta a `ip_event_count` y `ip_failure_count` y no a `ip_distinct_users`.
- La huella del esquema (SHA-256 del JSON canónico de versión, ventana y definiciones) se fija en un test junto
  con la versión.
