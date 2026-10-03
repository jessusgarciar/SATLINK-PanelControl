# Frontend SATLINK

Panel de control de la cápsula estratosférica. React + TypeScript + Vite, Leaflet/React Leaflet, ECharts/echarts-for-react, Fetch y WebSocket nativos. Se conserva la arquitectura y las versiones fijadas por el equipo.

## Iniciar

Usa Node.js 22.18 o posterior dentro de la rama 22 y npm 10. Desde la raíz del repositorio:

```sh
cd frontend
npm ci
npm run dev
```

Abre la dirección que indique Vite, normalmente `http://localhost:5173`. El modo predeterminado es **DEMOSTRACIÓN**; funciona sin FastAPI. La tipografía es local. El mapa base necesita conexión al proveedor de mosaicos, pero las coordenadas y trayectorias siguen visibles cuando este falla.

## Recorrido de la demostración

1. Observa fase, tiempos, altitudes, sensores, radio, posición y cuatro gráficas con actualización cada segundo.
2. Abre **Recuperación** para ver lanzamiento, trayectoria medida, liberación estimada y aterrizaje predicho. Modifica los rangos y pulsa **Recalcular escenario**. Los vientos constantes son ficticios.
3. Pulsa **PING**, **STATUS?**, **TELEM?** o la baliza. La bitácora distingue pendiente, enviado, recibido y ejecutado, con evidencias simuladas.
4. **RELEASE** abre una confirmación. Escribe `LIBERAR` para simular descenso y un evento de liberación independiente del estado del comando.
5. **Pausar señal** detiene las muestras. Tras 15 segundos, el panel marca datos antiguos y deshabilita comandos. **Reanudar señal** recupera la actualización.
6. Cambia a **ESTACIÓN REAL** para usar el backend configurado. Si está desconectado aparece un error explícito. Nunca se sustituye automáticamente por una simulación.

Recarga la página o cambia de fuente para comenzar un escenario nuevo. La demo no persiste ni transmite órdenes físicas.

## Conectar FastAPI

Copia `.env.example` a `.env.local` y ajusta:

```dotenv
VITE_DATA_SOURCE=live
VITE_API_BASE_URL=/api/v1
VITE_MISSION_ID=satlink-001
SATLINK_BACKEND_ORIGIN=http://127.0.0.1:8000
```

Reinicia Vite después de cambiar variables. El proxy `/api` admite HTTP y WebSocket. `VITE_*` es configuración pública del navegador, nunca un lugar para credenciales. `SATLINK_BACKEND_ORIGIN` solo configura el proxy de desarrollo.

El backend implementa snapshot, stream e historial paginado del [contrato documentado](../docs/protocols/frontend-api-v1.md). En esta etapa local no necesita login, entrega permisos de escritura en `false` y `csrfToken=null`. Comandos y predicción permanecen pendientes. El panel funciona en lectura; la altura relativa se calcula en backend. El perfil de 19 bytes no transmite humedad y todavía no calcula velocidad vertical ni altitud barométrica: se muestran como desconocidas. Los objetivos configurables tienen un máximo de 15 000 m relativos; las mediciones que lo superen permanecen visibles.

El proveedor de mapa puede cambiarse con `VITE_TILE_URL` y su atribución obligatoria en `VITE_TILE_ATTRIBUTION`. Una URL vacía desactiva las solicitudes de mapa base. Se incluye la atribución de OpenStreetMap; respeta las condiciones de tu proveedor al desplegar.

## Verificar y compilar

```sh
npm test
npm run lint
npm run build
npm run preview
```

Las pruebas utilizan el runner nativo de Node y no necesitan un servidor. El build ejecuta TypeScript estricto y genera `dist/`. `preview` sirve esa compilación para revisión local; no inicia FastAPI. En producción sirve `dist/` y `/api` bajo el mismo origen HTTPS con soporte para WebSocket en el proxy.

Mapa, gráficas y recuperación se cargan bajo demanda. Vite informa que el módulo de ECharts supera 500 kB minificados; la advertencia no se ha ocultado. No impide compilar. Su descarga comprimida ronda 185 kB y se realiza al mostrar gráficas.

## Dónde trabajar

| Cambio                                             | Ubicación                       |
| -------------------------------------------------- | ------------------------------- |
| Tipos, unidades y combinación de eventos           | `src/domain/mission.ts`         |
| Casos de uso, suscripciones y permisos del cliente | `src/application/`              |
| Rutas HTTP, payloads, validadores                  | `src/infrastructure/http/`      |
| Reconexión y heartbeat                             | `src/infrastructure/websocket/` |
| Escenario de ejemplo                               | `src/infrastructure/demo/`      |
| Pantallas, componentes, formatos y estilos         | `src/presentation/`             |
| Configuración y composición de adaptadores         | `src/app/App.tsx`               |

Consulta la [arquitectura del frontend](../docs/architecture/frontend.md) para las decisiones visuales, recursos de Figma y límites de integración.
