# Arquitectura limpia

El dominio define conceptos y contratos del problema. La aplicación coordina casos de uso mediante esos contratos. Estas dos capas permanecen independientes de React, FastAPI, PostgreSQL, MQTT y Tawhiri.

La dirección de las dependencias es hacia el interior: presentación e infraestructura pueden depender de aplicación y dominio; dominio no depende de las otras capas y aplicación solo depende del dominio y de sus propios puertos.

En el frontend, `presentation` alojará componentes, páginas, hooks, recursos y estilos. `infrastructure/http` y `infrastructure/websocket` alojarán adaptadores basados en Fetch y WebSocket nativos. `app` servirá como punto de composición y configuración.

En el backend, `domain/entities` contiene misión y uplink normalizado. `application/use_cases` coordina validación, asociación a misión, cálculo relativo, persistencia y publicación mediante `application/ports`. `infrastructure/database` implementa PostgreSQL asíncrono y `infrastructure/mqtt` el codec y consumidor. `presentation/schemas` valida entradas ChirpStack y respuestas HTTP con Pydantic; `presentation/api` restringe acceso local y `presentation/websocket` distribuye muestras mediante colas acotadas. `bootstrap` ensambla los adaptadores, rutas y CLI. El dominio y la aplicación no importan esas dependencias externas.

React pertenece a presentación y al arranque del frontend; FastAPI y Pydantic pertenecen a presentación y al arranque del backend. Los controladores de PostgreSQL, MQTT y servicios HTTP externos pertenecen a infraestructura. Instalar una biblioteca no crea una integración.

La migración inicial crea `missions`, `received_events` y `telemetry`; cada evento aceptado y su muestra se guardan en una misma transacción antes de publicar. La identidad del uplink impide duplicados concurrentes. Se conserva el origen de lanzamiento y no se modifica al repetir la inicialización. No se crea esquema al arrancar HTTP: se aplica Alembic explícitamente.

Esta etapa usa un único proceso local: consumidor MQTT y hub WebSocket comparten el ciclo de vida FastAPI. Clientes lentos se cierran con 1013 y recuperan muestras mediante snapshot/historial. No hay broker de distribución entre workers ni spool duradero de MQTT; esas capacidades no se presuponen. Las pruebas de PostgreSQL se ejecutan únicamente contra una base exclusiva `_test`. La simulación sigue en el adaptador demo del frontend y los fixtures no ingresan a la base de operación.

El consumidor comunica estados técnicos de ingestión y el snapshot/stream los exponen separados de la telemetría. Los adaptadores de PostgreSQL consultan ventanas reducidas para visualización y recorren todas las filas para CSV. El cliente reproduce el historial HTTP en una vista aislada, con fechas originales y memoria acotada.
