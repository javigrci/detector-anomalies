# Fixtures de ingesta

Todo el contenido de este directorio es **ficticio**:

- IPs solo de los rangos de documentación: `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` y
  `2001:db8::/32`.
- Usuarios inventados (`user001`…), hosts `srv-demo-NN`.
- Sin datos reales, credenciales ni secretos.

Algunos fixtures contienen **cadenas centinela** (`SENTINEL-…`) y contenido hostil (comandos,
instrucciones dirigidas a un asistente). Sirven para comprobar que esos valores nunca aparecen en
informes, excepciones ni logs, y que el contenido de un log se trata solo como dato. **Nunca se
ejecuta ni se interpreta**; se leen únicamente con las funciones de la ingesta.

Los fixtures validan el comportamiento del software, no demuestran capacidad real de detección
(SPEC §14).
