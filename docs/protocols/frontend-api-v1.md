# Contrato propuesto del panel SATLINK

Estado: implementado en el cliente, pendiente de implementar y acordar con el equipo de FastAPI. El repositorio base no tenía endpoints. Este documento no afirma que exista una conexión operativa con ChirpStack, MQTT, PostgreSQL, Tawhiri o la cápsula.

## Transporte y sesión

- Base HTTP: `/api/v1`. WebSocket: mismo origen, con `ws` en desarrollo y `wss` bajo HTTPS.
- Sesión del operador mediante cookie `HttpOnly`, `Secure` en producción y política `SameSite` apropiada. La creación/cierre de sesión pertenecen al backend; el frontend no inventa un login.
- Fetch usa `credentials: include`. Los POST incluyen `X-CSRF-Token`, obtenido del snapshot. FastAPI debe validar sesión, rol, pertenencia a misión, origen y CSRF. Ocultar/deshabilitar botones no es autorización.
- No incluir credenciales de MQTT, PostgreSQL ni ChirpStack en variables `VITE_*`.
- Fechas RFC3339 con zona horaria explícita, preferentemente UTC `Z`. El panel presenta hora local del navegador y usa la hora de recepción como eje de telemetría.
- JSON de aplicación; el límite de 11 bytes se aplica al payload de radio, no a HTTP/WebSocket.

## Operaciones

| Método    | Ruta                                  | Respuesta                                   |
| --------- | ------------------------------------- | ------------------------------------------- |
| GET       | `/missions/{id}/dashboard?limit=1200` | `DashboardSnapshot`                         |
| WebSocket | `/missions/{id}/stream`               | Mensajes discriminados por `type`           |
| POST      | `/missions/{id}/commands`             | `Command` registrado, normalmente `pending` |
| POST      | `/missions/{id}/predictions`          | Última `Prediction` calculada               |

No hay otras rutas supuestas. Si el equipo decide otro contrato, se cambian los adaptadores de `infrastructure`; dominio y componentes quedan independientes de esas URLs.

## Snapshot

La definición completa y tipada está en `frontend/src/domain/mission.ts`. `dashboard.example.json` es una muestra **sintética**, sin permisos de escritura ni credenciales. No debe utilizarse como configuración de un vuelo real.

| Campo         | Contenido                                                              |
| ------------- | ---------------------------------------------------------------------- |
| `mission`     | Identidad, origen persistente, configuración, fase confirmada y fechas |
| `telemetry`   | Últimas muestras de la misión, con ID único por evento                 |
| `commands`    | Historial reciente de comandos y sus evidencias                        |
| `events`      | Eventos de misión, incluida liberación física cuando se confirme       |
| `prediction`  | Última predicción válida, o `null`                                     |
| `permissions` | `canCommand` y `canPredict`, booleanos derivados de la sesión          |
| `csrfToken`   | Token de sesión para POST o `null` cuando no corresponda               |

`Mission` contiene: `id`, `name`, `updatedAt`, `startedAt`, `endedAt`, `phase`, `launch`, `launchLabel`, `targetRelativeAltitudeM`, `nominalAscentMs`, `nominalDescentMs`, `watchdogSeconds`, `staleAfterSeconds`, `deviceEui`, `region`, `beaconOn`. `launch` contiene `latitude`, `longitude` y `altitudeM` sobre nivel del mar. `beaconOn` admite `null` para un estado desconocido.

Fases: `preflight`, `ascending`, `descending`, `landed`, `unknown`. El backend/firmware confirma las fases. El frontend real no declara aterrizaje a partir de un solo paquete.

### Telemetría y unidades

| Campo                   | Tipo / unidad                                                                       |
| ----------------------- | ----------------------------------------------------------------------------------- |
| `id`, `missionId`       | Texto; ID persistente del evento, no solo `frameCounter`                            |
| `receivedAt`            | Fecha de recepción con zona horaria                                                 |
| `frameCounter`          | Entero sin signo, 0–4 294 967 295                                                   |
| `latitude`, `longitude` | Grados, ambos `null` si no hay posición válida                                      |
| `altitudeGpsM`          | Metros sobre nivel del mar                                                          |
| `altitudeBarometricM`   | Metros sobre nivel del mar, derivada por backend; `null` fuera del rango del sensor |
| `relativeAltitudeM`     | Metros respecto al origen de lanzamiento, derivada por backend                      |
| `verticalSpeedMs`       | m/s filtrados por backend; signo positivo = ascenso                                 |
| `temperatureC`          | °C                                                                                  |
| `humidityPct`           | %                                                                                   |
| `pressureHpa`           | hPa                                                                                 |
| `batteryV`              | V, no porcentaje de carga inferido                                                  |
| `rssiDbm`, `snrDb`      | dBm y dB, metadatos de ChirpStack                                                   |

Todos los campos numéricos de sensores admiten `null`. El adaptador normaliza a `null` los sensores ausentes, no finitos o fuera del rango del payload v1. Los valores reservados deben decodificarse en backend antes de emitir JSON; nunca se sustituyen por cero. La presión binaria 255, por ejemplo, no debe enviarse como 255 hPa: el frontend no puede distinguir un sentinel no decodificado de una presión física válida.

El cliente almacena hasta 1200 muestras y dibuja hasta 600 por gráfica. Ordena por `receivedAt`, deduplica por ID y no desplaza la lectura actual cuando llega un paquete anterior. La deduplicación persistente por dispositivo/sesión/evento y el archivo histórico completo son responsabilidad del backend.

## WebSocket

Cada mensaje usa uno de estos sobres:

```json
{
  "type": "telemetry",
  "data": {
    "id": "...",
    "missionId": "...",
    "receivedAt": "2026-10-02T03:00:00Z"
  }
}
```

El ejemplo de `data` anterior está abreviado. Debe respetar el tipo completo correspondiente.

| `type`       | `data`                              |
| ------------ | ----------------------------------- |
| `telemetry`  | `Telemetry`                         |
| `mission`    | `Mission` completa, con `updatedAt` |
| `command`    | `Command` completa                  |
| `event`      | `MissionEvent` completa             |
| `prediction` | `Prediction` completa               |
| `heartbeat`  | Sin `data` requerida                |

Enviar heartbeat al menos cada 20 s aun si no hay uplinks. El cliente cierra una conexión sin mensajes durante 45 s y reintenta con espera exponencial de 1–30 s más jitter. Cada apertura solicita un nuevo snapshot y mezcla el historial con los mensajes ya recibidos. No se asume replay ilimitado: una interrupción mayor que la ventana disponible requiere consultar el archivo histórico del backend.

El servidor debe emitir mensajes después de persistirlos. Cierres `1008`, `4401` y `4403` detienen la reconexión automática por sesión/permiso; el operador puede reintentar tras corregir la sesión. Mensajes desconocidos o malformados se descartan con error visible. Los datos anteriores se conservan y muestran su antigüedad.

## Comandos

```json
{ "type": "PING", "clientRequestId": "UUID-generado-por-el-cliente" }
```

Además de CSRF se envía `Idempotency-Key` con el mismo UUID. El backend debe imponer unicidad por misión/operador/ID y devolver el mismo registro ante duplicados. Los tipos admitidos son `PING`, `STATUS`, `TELEMETRY`, `BEACON_ON`, `BEACON_OFF` y `RELEASE_NOW`.

`Command`: `id`, `missionId`, `clientRequestId`, `type`, `status`, `createdAt`, `updatedAt`, `evidence`, `simulated`. En la estación real, `simulated` es `false`.

| Estado     | Evidencia esperada                                                   |
| ---------- | -------------------------------------------------------------------- |
| `pending`  | Solicitud autorizada y persistida                                    |
| `sent`     | `txack` correlacionado del gateway                                   |
| `received` | ACK de downlink o respuesta de recepción; indicar cuál en `evidence` |
| `executed` | Respuesta de ejecución correlacionada del firmware                   |
| `rejected` | Rechazo explícito                                                    |
| `expired`  | Vencimiento registrado por backend                                   |

El panel nunca transforma un timeout o un ACK en ejecución. No reintenta automáticamente un POST. Después de un resultado incierto, solicita revisar la bitácora. La liberación exige escribir `LIBERAR`, estar en ascenso, tener datos recientes y no tener otra solicitud activa. Estas comprobaciones deben repetirse en backend y firmware.

`MissionEvent`: `id`, `missionId`, `receivedAt`, `type` (`info`, `warning`, `release`, `landed`), `message`, `position` (`Position` o `null`). La confirmación física de liberación llega como evento independiente; no se deduce del HTTP 200.

## Predicción

```json
{ "targetRelativeAltitudeM": 15000, "ascentRateMs": 5, "descentRateMs": 6.5 }
```

El backend transforma objetivo relativo en altitud absoluta usando el origen persistente, normaliza longitud para Tawhiri, valida el datum y el perfil, consulta el servicio, conserva parámetros/meteorología/fecha y devuelve la respuesta normalizada. Impone permisos, límites y una separación inicial mínima de 60 s entre consultas. El panel no contacta directamente a Tawhiri ni transmite los vientos del simulador a la API real.

`Prediction`: `id`, `missionId`, `generatedAt`, `weatherAt`, `source` (`tawhiri` real, `demo` simulado), `parameters`, `trajectory`, `release`, `landing`. Cada punto contiene `latitude`, `longitude`, `altitudeM` y `time`. `parameters` contiene las tres entradas del POST; los cuatro parámetros de viento del dominio son opcionales en JSON real y se normalizan a cero.

El objetivo debe superar la altitud actual durante el ascenso. Durante descenso/aterrizaje, el cliente conserva la predicción previa y desactiva el perfil estándar. No fuerza solicitudes con ascenso negativo ni alturas de cambio inferiores a la inicial. `weatherAt` puede ser `null` si la fuente no lo proporciona; no se inventa fecha meteorológica ni precisión estadística.

## Errores y despliegue

Usar HTTP 401 para sesión ausente, 403 para permisos/CSRF, 404 para misión inexistente, 409 para comandos incompatibles y 429 para cadencia excedida. El cliente también maneja 5xx, desconexión, respuestas HTML y timeouts de 12 s. Un error al refrescar el snapshot deja los datos visibles y deshabilita escrituras hasta recuperar permisos válidos.

En producción servir `frontend/dist` y `/api` bajo el mismo origen HTTPS; el reverse proxy debe soportar upgrade WebSocket. El proxy de Vite solo es para desarrollo. El backend debe permitir el origen de desarrollo explícitamente y verificar cookies/CSRF con ese esquema. El frontend no instala servicios ni cambia configuración de PostgreSQL.
