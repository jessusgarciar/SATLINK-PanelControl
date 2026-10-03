# Verificación de telemetría PICARO FULL

Fecha: 2 de octubre de 2026. Entorno Windows, Python 3.13, PostgreSQL 17.11, dependencias fijadas del proyecto. Se consultó Context7 y se contrastaron las APIs con los paquetes instalados; en particular, aiomqtt 2.5.1 usa `client.messages` y reconexión explícita, no las APIs v3 mostradas en parte de la documentación indexada.

## Resultados ejecutados

| Comprobación | Resultado |
| --- | --- |
| Backend: `python -m pytest -q` con base exclusiva | **33 aprobadas**, 0 fallos, 0 omitidas |
| PostgreSQL de pruebas | `satlink_picaro_test`, separada de `satlink_dev`, autenticación SSPI |
| Migraciones: `python -m alembic check` | Sin operaciones nuevas: modelos y migración coinciden |
| Dependencias: `python -m pip check` | Sin requisitos rotos |
| Frontend: `npm test` | **19 aprobadas** |
| Frontend: `npm run build` | Correcto |
| Frontend: `npm run lint` | Correcto |
| Python: compilación de módulos y migraciones | Correcta |

Se aplicó Alembic en la base de pruebas; no se migró ni se sembró la base de operación. No se registró una misión real ni se configuraron credenciales de broker. El ejemplo de misión exige completar datos reales antes de aceptarlo. El workflow de GitHub Actions está añadido para repetir las comprobaciones con PostgreSQL 17; no se ha ejecutado remotamente ni se han publicado cambios.

## Evidencia y cobertura funcional

- Vectores de bytes conocidos: temperatura con signo y cero válido, altitud GPS negativa, escalas, batería desconocida, ausencia de fix y humedad, presión 255 hPa válida.
- Rechazo de longitud, puerto, Base64, contador, fechas y sobre inválidos; protección frente a valores no finitos, claves JSON repetidas y cadenas incompatibles con JSONB.
- Altura relativa 0 al origen, 15 000 m sobre origen y observación superior al objetivo sin recorte. Barómetro y velocidad permanecen desconocidos.
- Seis ingestiones concurrentes del mismo evento producen una sola muestra y emisión; repetir tras abrir otra instancia del repositorio no duplica. Un nuevo evento con el mismo contador sí se conserva.
- Antes de publicar, otra conexión PostgreSQL puede leer la muestra confirmada. Un fallo durante la inserción revierte evento y muestra y no emite; un fallo de publicación conserva el historial.
- Archivo sintético de **1206 muestras**, ventana de 1200 y recorrido por páginas de 113, sin IDs perdidos o duplicados, incluso con timestamps iguales. Filtros temporales y aislamiento entre misiones comprobados.
- Respuestas reales de la API de prueba validadas por los parsers TypeScript del frontend mediante Node. `/docs`, OpenAPI, errores y permisos de lectura comprobados.
- Flujo sintético de ingestión → PostgreSQL → WebSocket, snapshot posterior y diez reconexiones consecutivas. Heartbeat recibido tras 20 segundos sin muestras. Orígenes externos y clientes no locales rechazados.
- Consumidor MQTT probado con adaptador simulado: desconexión, reconexión, reintento de la misma muestra ante fallo temporal de persistencia y cancelación. No se utilizó un broker real.

## Límites y advertencias

Las pruebas no prueban recepción RF, cobertura, vuelo, precisión del sensor ni configuración de ChirpStack. Faltan broker, Application ID, DevEUI y configuración real del lanzamiento para la validación física. La procedencia de transporte no certifica por sí sola que un evento se originó en hardware.

El consumidor no tiene spool duradero: una caída del proceso entre ACK MQTT y commit puede perder un uplink. La reconexión WebSocket recupera lo que ya fue persistido. Comandos, firmware, importación de microSD y Tawhiri quedan fuera de esta entrega.

Starlette 1.7.0 advierte que su TestClient con HTTPX está deprecado. Se conservaron las versiones acordadas; no se instaló HTTPX2. Vite mantiene la advertencia conocida del bloque ECharts de más de 500 kB; el build finaliza correctamente. No se afirma un porcentaje de cobertura de líneas porque no se midió.
