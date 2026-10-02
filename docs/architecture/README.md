# Arquitectura limpia

El dominio define conceptos y contratos del problema. La aplicación coordina casos de uso mediante esos contratos. Estas dos capas permanecen independientes de React, FastAPI, PostgreSQL, MQTT y Tawhiri.

La dirección de las dependencias es hacia el interior: presentación e infraestructura pueden depender de aplicación y dominio; dominio no depende de las otras capas y aplicación solo depende del dominio y de sus propios puertos.

En el frontend, `presentation` alojará componentes, páginas, hooks, recursos y estilos. `infrastructure/http` y `infrastructure/websocket` alojarán adaptadores basados en Fetch y WebSocket nativos. `app` servirá como punto de composición y configuración.

En el backend, `domain/entities` y `domain/repositories` quedan reservados para conceptos y contratos independientes de frameworks. `application/use_cases` y `application/ports` alojarán la coordinación y sus interfaces. `infrastructure/database`, `mqtt` y `prediction` contendrán adaptadores de dependencias externas. `presentation/api`, `schemas` y `websocket` contendrán la interfaz HTTP, validación Pydantic y transporte WebSocket. `bootstrap` ensamblará las implementaciones.

React pertenece a presentación y al arranque del frontend; FastAPI y Pydantic pertenecen a presentación y al arranque del backend. Los controladores de PostgreSQL, MQTT y servicios HTTP externos pertenecen a infraestructura. Instalar una biblioteca no crea una integración.

`decisions` queda reservado para registros de decisiones de arquitectura. `migrations` y los niveles de pruebas quedan preparados como carpetas vacías. No hay entidades, repositorios concretos, casos de uso, API ni migraciones implementados.
