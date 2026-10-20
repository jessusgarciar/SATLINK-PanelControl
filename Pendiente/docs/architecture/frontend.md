# Frontend del panel SATLINK

Implementación sobre el commit base `1bff7bc58cd196c161195fcdb8224e63af2809be`. Se conserva el stack fijado en `frontend/package.json`: React 19.3, TypeScript 6, Vite 8, React Leaflet 5 / Leaflet 1.9, ECharts 6 y echarts-for-react. La adaptación a Orbitium añade Motion y Hugeicons para React Bits y Playwright en desarrollo. No se añadió Tailwind, cliente HTTP, gestor de estado ni router.

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

Agrega consulta temporal, exportación y reproducción a esos puertos. El estado de ingestión MQTT y la conexión WebSocket son independientes. La vista histórica fija un intervalo y pagina HTTP con hasta 1200 muestras visibles más una página pendiente de hasta 200; suspende el stream en vivo y mantiene las fechas originales a 1×/5×/10×. La bitácora técnica conserva hasta 100 entradas de sesión sin persistirlas como eventos físicos. El mapa y las gráficas pueden usar subconjuntos reducidos del archivo; el CSV conserva todas las filas del intervalo.

## Figma y decisiones visuales

Referencias del archivo `vHGubRMQ7LDtfg2egfMrkw`:

- Dashboard móvil: `7:1097`.
- Recuperación y rastreo: `7:797`.
- Bitácora de respuestas: `7:1936`.

Pendiente conserva su paleta clara: fondo `#F4F7FB`, superficies `#FFFFFF`, superficie secundaria `#EEF2F7`, azul `#2563EB`, verde `#16A34A`, ámbar `#D97706` y rojo `#DC2626`, bordes de 1 px, radio de 4 px y JetBrains Mono. La tipografía se sirve localmente con licencia OFL incluida. La composición y componentes se adaptan del Orbitium actual; consulta [alcance y evidencia](../features/orbitium-adaptation.md).

El archivo contiene diseños móviles, no una pantalla de escritorio separada. La versión ancha reorganiza las mismas secciones con CSS Grid: resumen de altitud, cuatro indicadores, seis sensores, mapa y gráficas. En móvil las métricas pasan a dos columnas, mapa y gráficas a una, y los detalles secundarios se agrupan en un carrusel manual de altura automática. Recuperación pasa a pantalla completa con desplazamiento vertical. No hay navbar inferior ni navbar interna de Recuperación.

### Recursos

- `presentation/assets/figma/range-thumb.svg` conserva la exportación del nodo `9:4`, 9 × 9 px. Los diálogos de operación sobrescriben el thumb con una variante mayor y área táctil de al menos 44 px.
- Las líneas/áreas de gráficas y rutas de mapa son representaciones de datos dinámicos. Se implementaron con ECharts/Leaflet, conforme al stack solicitado, sin incrustar trazos estáticos ni capturas del diseño.
- Las capturas de Figma no se utilizan como recursos de interfaz. No quedan URLs temporales de Figma en el código.
