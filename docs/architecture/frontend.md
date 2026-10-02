# Frontend del panel SATLINK

Implementación sobre el commit base `1bff7bc58cd196c161195fcdb8224e63af2809be`. Se conserva el stack fijado en `frontend/package.json`: React 19.3, TypeScript 6, Vite 8, React Leaflet 5 / Leaflet 1.9, ECharts 6 y echarts-for-react. No se añadió Tailwind, cliente HTTP, gestor de estado, router ni dependencia de producción.

## Responsabilidades

| Capa                       | Implementación                                                                                       | Dependencias permitidas                    |
| -------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `domain`                   | Tipos con unidades, unión de telemetría, comandos y eventos; cálculos de edad/distancia              | TypeScript / API estándar, sin React       |
| `application`              | Puerto `MissionGateway` y `MissionController`: carga, estado, suscripción, recuperación, solicitudes | Dominio y sus propios puertos              |
| `infrastructure/http`      | Fetch con sesión/CSRF, timeouts, validación en ejecución y adaptación del contrato                   | Aplicación y dominio                       |
| `infrastructure/websocket` | WebSocket nativo, heartbeat, reconexión y limpieza                                                   | Dominio y validadores del transporte       |
| `infrastructure/demo`      | Escenario determinista y respuestas simuladas; ninguna conexión a hardware                           | Puerto de aplicación y dominio             |
| `presentation`             | Componentes, páginas, hooks React, Leaflet/ECharts, formato local y estilos                          | Aplicación, dominio y bibliotecas visuales |
| `app`                      | Composición de adaptadores y configuración de entorno                                                | Todas las capas exteriores necesarias      |

Una fuente de estado sirve dashboard, mapa, gráficas, recuperación y comandos. `useSyncExternalStore` conecta el controlador independiente de React a la presentación. Las suscripciones, timers, peticiones y sockets se limpian al desmontar/cambiar de modo. El historial inicial y los mensajes simultáneos se mezclan por identidad y fecha. Los botones consumen casos de uso, no llaman Fetch desde componentes.

## Figma y decisiones visuales

Referencias del archivo `vHGubRMQ7LDtfg2egfMrkw`:

- Dashboard móvil: `7:1097`.
- Recuperación y rastreo: `7:797`.
- Bitácora de respuestas: `7:1936`.

Se preservan paleta de fondo `#060A12`, superficies `#0D1625`, cabecera `#04080F`, cian `#00E5FF`, verde `#4ADE80`, ámbar `#FBBF24`, rojo `#F87171`, bordes de 1 px, radio de 4 px, separación de 12 px y JetBrains Mono. La tipografía se sirve localmente con licencia OFL incluida. Se eleva el contraste de textos secundarios para que sean legibles en operación.

El archivo contiene diseños móviles, no una pantalla de escritorio separada. La versión ancha reorganiza las mismas secciones con CSS Grid: cuatro indicadores de misión, seis sensores, mapa/altitud a la izquierda y gráficas a la derecha. En 393 px se conserva el orden del diseño y las tarjetas pasan a dos columnas. La recuperación pasa a pantalla completa con desplazamiento vertical, sin recortar contenidos.

### Recursos

- `presentation/assets/figma/range-thumb.svg` es la exportación original del nodo `9:4`, 9 × 9 px. Se usa sin cambiar su geometría en los siete controles de rango del simulador y los tres del modo real.
- Las líneas/áreas de gráficas y rutas de mapa son representaciones de datos dinámicos. Se implementaron con ECharts/Leaflet, conforme al stack solicitado, sin incrustar trazos estáticos ni capturas del diseño.
- Las capturas de Figma no se utilizan como recursos de interfaz. No quedan URLs temporales de Figma en el código.

### Ajustes semánticos respecto al mockup

1. Identidad SATLINK; selector visible entre demostración y estación real. Nunca se cambia automáticamente a datos ficticios por una desconexión.
2. GPS absoluto y altura relativa separados. El objetivo de 15 km se interpreta como relativo al origen, conforme al reporte.
3. Coordenadas numéricas válidas en lugar de copiar errores tipográficos del diseño. El origen de demo es explícitamente un ejemplo, no una ubicación aprobada para lanzar.
4. El watchdog mostrado es una referencia temporal; el disparador permanece en firmware.
5. Se reemplaza el texto `Challenge-Response` por una respuesta de dispositivo basada en evidencias; no se finge autenticación criptográfica que el backend no implementa.
6. La predicción por vientos constantes solo existe en demostración y se etiqueta como tal. La real se solicita al backend con meteorología; se mantiene la predicción anterior cuando el proveedor falla.
7. Los textos `recibido`, `ejecutado` y `liberación` corresponden a evidencias distintas. No hay reintentos automáticos de comandos.

## Operación y límites

El frontend está preparado para el [contrato propuesto](../protocols/frontend-api-v1.md). El backend, la sesión/roles, el transporte radio, el codec, las migraciones, el servicio Tawhiri y las pruebas de vuelo siguen a cargo de sus integraciones respectivas. La demo no las valida.

La ventana del cliente conserva hasta 1200 muestras; cada gráfica representa hasta 600. PostgreSQL debe conservar el archivo completo y resolver reinicios, sesiones, duplicados y trazabilidad. Un comando de liberación se confirma manualmente y no se publica al abrir la página.

La cartografía tiene proveedor configurable y atribución visible. Se solicita solo lo necesario para la vista interactiva, sin descargas masivas, precarga ni promesa de mapas sin conexión. Sin mosaicos se conservan trazas, coordenadas y un aviso visible. El proveedor estándar está sujeto a la [política de OpenStreetMap](https://operations.osmfoundation.org/policies/tiles/).

Referencias de implementación: [React Leaflet 5](https://react-leaflet.js.org/docs/api-map/), [ECharts](https://echarts.apache.org/en/index.html), documentación de tipos instalada y reporte de stack proporcionado por el equipo.
