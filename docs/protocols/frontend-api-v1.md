# Contrato propuesto del panel SATLINK

Estado: snapshot, stream e historial implementados en FastAPI para telemetría PICARO FULL de 19 bytes. La predicción incorpora consultas Tawhiri opcionales y persistencia de la última respuesta válida; consulta [la guía y el estado de verificación](../features/prediction-tawhiri.md). La etapa actual es local, sin login ni telecomandos. Los comandos y la sesión de operador para acceso compartido describen contratos futuros. La verificación con hardware permanece pendiente.

Incorpora estado de ingestión, metadatos de dispositivo/radio, ventana temporal y CSV. La reproducción es una vista de cliente sobre el historial persistido. Consulta [Dashboard y conexión ChirpStack](../features/dashboard-chirpstack.md).

## Transporte y sesión

- Base HTTP: `/api/v1`. WebSocket: mismo origen, con `ws` en desarrollo y `wss` bajo HTTPS.
- Excepción de esta etapa: acceso exclusivo desde loopback y orígenes locales permitidos, sin login y `canCommand=false`. La predicción está deshabilitada por defecto. Al habilitarla, el snapshot puede dar `canPredict=true` y un token CSRF generado por el proceso; el POST requiere `Origin` de la lista local permitida y `X-CSRF-Token` válido. Un reinicio renueva el token: refresca el snapshot antes de volver a solicitar. Para acceso compartido se requerirá sesión del operador mediante cookie `HttpOnly`, `Secure` en producción y política `SameSite` apropiada. La creación/cierre de sesión pertenecen al backend.
- Fetch usa `credentials: include`. Los POST incluyen `X-CSRF-Token`, obtenido del snapshot. El POST local de predicción valida origen, CSRF y configuración de la misión. Para el futuro acceso compartido FastAPI deberá añadir sesión, rol y pertenencia a misión. Ocultar/deshabilitar botones no es autorización.
- No incluir credenciales de MQTT, PostgreSQL ni ChirpStack en variables `VITE_*`.
- Fechas RFC3339 con zona horaria explícita, preferentemente UTC `Z`. El panel presenta hora local del navegador y usa la hora de recepción como eje de telemetría.
- JSON de aplicación. El perfil de radio actual utiliza 19 bytes y fPort 10, descritos en [PICARO FULL v1](picaro-full-v1.md); no se aplica el antiguo borrador compacto de 11 bytes.

## Operaciones

| Método    | Ruta                                  | Respuesta                                   |
| --------- | ------------------------------------- | ------------------------------------------- |
| GET       | `/missions/{id}/dashboard?limit=1200` | `DashboardSnapshot`                         |
| WebSocket | `/missions/{id}/stream`               | Mensajes discriminados por `type`           |
| GET       | `/missions/{id}/telemetry`           | `{items, nextCursor}`; historial paginado     |
| GET       | `/missions/{id}/telemetry/window`    | `{from, to, total, series, track}`; ventana visual |
| GET       | `/missions/{id}/telemetry/export.csv` | CSV con todas las filas del intervalo       |
| POST      | `/missions/{id}/commands`             | `Command` registrado, normalmente `pending` |
| POST      | `/missions/{id}/predictions`          | Última `Prediction` calculada               |

El POST de comandos aún no existe y devuelve 404. El POST de predicción se habilita mediante configuración explícita. El historial acepta `from`, `to` RFC3339 con zona, intervalo `[from,to)`, `cursor` opaco y `limit` de 1–1200 (predeterminado 200). Ordena por `(receivedAt,id)` ascendente y devuelve `nextCursor=null` al terminar. Se deben conservar los filtros entre páginas; cursor malformado o ajeno a los filtros produce 422. El snapshot devuelve las últimas muestras, con límite predeterminado 1200. La adaptación del Ejercicio 10 agrega consulta temporal y reproducción histórica al dashboard.

La ventana y el CSV aceptan `from`/`to` opcionales con el mismo intervalo `[from,to)`. Si `from` falta, el inicio del archivo no se restringe; si `to` falta, se fija a la hora de consulta. La ventana devuelve ese corte temporal, `total` para todas las muestras y las listas reducidas `series` (hasta 600 `Telemetry`) y `track` (hasta 500 `Telemetry` con posición disponible). `from` puede ser `null`. El CSV exporta todas las filas, sin tomar las listas reducidas como fuente, e incluye telemetría, metadatos aplanados `device_*`/`radio_*`, `source`, `applicationId`, `devEui` y `raw_json`. Para exportar el corte mostrado se envían los límites devueltos por la ventana.

## Snapshot

La definición completa y tipada está en `frontend/src/domain/mission.ts`. `dashboard.example.json` es una muestra **sintética**, sin permisos de escritura ni credenciales. No debe utilizarse como configuración de un vuelo real.

| Campo         | Contenido                                                              |
| ------------- | ---------------------------------------------------------------------- |
| `mission`     | Identidad, origen persistente, configuración, fase confirmada y fechas |
| `ingestion`   | Estado MQTT del backend y su fecha de cambio; `null` si no está disponible |
| `telemetry`   | Últimas muestras de la misión, con ID único por evento                 |
| `commands`    | Historial reciente de comandos y sus evidencias                        |
| `events`      | Eventos de misión, incluida liberación física cuando se confirme       |
| `prediction`  | Última predicción válida, o `null`                                     |
| `predictionSettings` | Habilitación, referencias de altitud y próximo instante permitido de consulta |
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
| `device`               | `gpsActive`, `gpsFix`, `satellites`, `batteryPct`, `charging`, `usbPowered`; objeto o `null` |
| `radio`                | `gatewayId`, `frequencyHz`, `dataRate`, `fPort`; objeto o `null`                      |

Todos los campos numéricos de sensores admiten `null`. El adaptador normaliza a `null` sensores ausentes, no finitos o fuera del rango del perfil. En PICARO FULL la presión es uint16/10, sin sentinel 255: **255 hPa es válido**. El porcentaje de batería 255 es desconocido y permanece en metadatos internos; no reemplaza al voltaje. Sin fix GPS, coordenadas y altitud GPS son `null`. La humedad no viaja en este perfil; barométrica y velocidad vertical todavía no se calculan. Las tres son `null`.

Los valores de `device` y `radio` también admiten `null`. `batteryPct` expone el porcentaje recibido si está en 0–100; 255 permanece desconocido. `frequencyHz` se expresa en Hz y `dataRate` es el índice de datarate del sobre ChirpStack, no una velocidad calculada por el cliente. `gatewayId`, RSSI y SNR proceden de la misma recepción seleccionada. Muestras antiguas sin estos metadatos siguen siendo legibles como `null`; no se les inventan flags ni valores de radio.

El objetivo configurable máximo es 15 000 m relativos. Las mediciones que excedan esa altura no se recortan. El GPS admite altitudes negativas hasta −500 m; la altura relativa puede ser negativa respecto al origen persistente. No se infieren fase, liberación o aterrizaje de estas muestras: la fase inicial es `unknown`.

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
| `ingestion`  | `{source, status, updatedAt}`        |
| `mission`    | `Mission` completa, con `updatedAt` |
| `command`    | `Command` completa                  |
| `event`      | `MissionEvent` completa             |
| `prediction` | `Prediction` completa               |
| `heartbeat`  | Sin `data` requerida                |

Enviar heartbeat al menos cada 20 s aun si no hay uplinks. El cliente cierra una conexión sin mensajes durante 45 s y reintenta con espera exponencial de 1–30 s más jitter. Cada apertura solicita un nuevo snapshot y mezcla el historial con los mensajes ya recibidos. No se asume replay ilimitado: una interrupción mayor que la ventana disponible requiere consultar el archivo histórico del backend.

El servidor debe emitir mensajes después de persistirlos. Cierres `1008`, `4401` y `4403` detienen la reconexión automática por sesión/permiso; el operador puede reintentar tras corregir la sesión. Mensajes desconocidos o malformados se descartan con error visible. Los datos anteriores se conservan y muestran su antigüedad.

Los cambios de ingestión son estado técnico de transporte, no muestras ni eventos físicos persistidos. `status` admite `disabled`, `connecting`, `connected`, `reconnecting` y `offline`; `updatedAt` conserva la fecha del cambio con zona. Su estado es independiente del WebSocket: `connected` no prueba recepción RF ni actualidad de los sensores. Representa la última suscripción confirmada y los cambios observados; un reintento de persistencia puede retrasar la detección de una caída MQTT.

## Ventanas, reproducción y bitácora técnica

El cliente ofrece ventanas de 15 minutos, 1 hora, 6 horas, 24 horas y todo el archivo mediante la consulta de ventana. La reproducción fija los límites al abrir y usa la API paginada, con hasta 1200 muestras visibles más una página pendiente de hasta 200. Las velocidades 1×/5×/10× modifican la espera entre muestras y conservan sus fechas originales. La vista se identifica como histórica, no consume el stream en vivo y deshabilita comandos y predicción; salir solicita de nuevo el estado actual. Los paquetes tardíos que cambian el conjunto consultado requieren reiniciar el intervalo para asegurar que quedan incluidos.

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

Ejemplo **sintético** de lanzamiento planeado; reemplaza la fecha por una admisible al consultar:

```json
{ "mode": "planned", "launchDatetime": "2026-10-04T18:00:00Z", "targetRelativeAltitudeM": 15000, "ascentRateMs": 5, "descentRateMs": 6.5 }
```

El POST exige `mode` (`planned` o `ascending`) y las tres entradas numéricas: objetivo relativo de 1000–15000 m, ascenso de 1–10 m/s y descenso al nivel del mar de 1–15 m/s. `launchDatetime` es obligatorio, futuro y RFC3339 con zona en `planned`; está prohibido en `ascending`. El perfil planeado parte del origen persistente de misión y la hora elegida. El perfil `ascending` parte del último GPS válido y reciente con el objetivo absoluto por encima de su altitud; usa `receivedAt` como aproximación temporal porque el perfil PICARO no contiene hora GPS de medición. No selecciona silenciosamente otro origen ni convierte el último paquete en punto de lanzamiento.

Elegir un modo expresa un perfil de cálculo del operador; no confirma fase física ni cambia `mission.phase=unknown`. Las fases confirmadas de descenso/aterrizaje no admiten este perfil estándar. Tampoco se envía un comando de liberación por solicitar una predicción.

`predictionSettings` contiene `enabled`, `launchAltitudeReference` y `gpsAltitudeReference` (`MSL` o `unknown`), y `nextAllowedAt` (RFC3339 o `null`). La configuración permanece deshabilitada por defecto. Se requiere referencia MSL comprobada del lanzamiento para ambos modos y del GPS para `ascending`; declarar MSL no efectúa conversión de datum. La altitud elipsoidal necesita conversión validada antes de esta etapa.

El backend transforma el objetivo relativo en altitud absoluta usando la altitud persistente del lanzamiento, normaliza la longitud al intervalo requerido por Tawhiri y consulta el perfil estándar de ascenso/descenso. El descenso nominal se interpreta al nivel del mar. La URL predeterminada es `https://api.v2.sondehub.org/tawhiri`, configurable solo en backend. La consulta tiene límite total de 10 s y no se reintenta automáticamente. Se registra una separación mínima persistente de 60 s por misión, incluso si falla el proveedor; `nextAllowedAt` permite reflejarla después de refrescar. El panel no contacta directamente a Tawhiri ni transmite los vientos del simulador.

`Prediction`: `id`, `missionId`, `generatedAt`, `weatherAt`, `source` (`tawhiri` real, `demo` simulado), `parameters`, `context`, `trajectory`, `release`, `landing`. Cada punto contiene `latitude`, `longitude`, `altitudeM` MSL y `time` con zona. `parameters` conserva modo, hora planeada cuando corresponde y las tres entradas; los cuatro vientos del dominio son opcionales en JSON real y se normalizan a cero. `context` conserva `mode`, `origin` (`Position`), `originAt`, `telemetryId` (`null` para origen planeado), `dataset` (texto o `null` si el proveedor no lo expone) y `altitudeReference="MSL"`. La respuesta identifica las entradas efectivamente utilizadas; no sustituye su fecha por la hora local de pantalla. Los snapshots anteriores y la demo pueden omitir `context` y `predictionSettings`; el cliente no habilita predicción real si faltan ajustes.

`release` representa el cambio de ascenso a descenso del perfil de predicción. Su marcador y fecha son estimados; no acreditan ruptura, liberación física ni ejecución de firmware. `landing` es el punto final calculado del perfil, sin confirmación de aterrizaje medido. `weatherAt` identifica la fecha meteorológica disponible, puede ser `null` si falta y no se inventa. Tampoco se inventa precisión estadística.

La validación admite hasta ±10 m de diferencia de la transición frente al objetivo y ±1 s entre el primer punto y la hora efectiva del origen para resolver tolerancias numéricas del solver. Esos márgenes no describen precisión física ni incertidumbre del vuelo.

Una respuesta válida se guarda antes de emitirse como mensaje WebSocket `prediction`. Un fallo, timeout o respuesta incompleta conserva en PostgreSQL la última predicción válida y no emite un resultado fallido como válido. El snapshot la recupera después de reiniciar el servidor; la cadencia también sobrevive al reinicio. El cliente conserva el resultado anterior y muestra el error del nuevo intento. Consultar SondeHub con las mismas entradas comprueba coherencia del cálculo y de la adaptación; verificar precisión física requiere trayectoria y aterrizaje observados.

## Errores y despliegue

En la predicción local: HTTP 403 para predictor deshabilitado/origen/CSRF inválido, 404 para misión inexistente, 422 para entradas, datum, contexto o perfil inválidos, 429 para cadencia excedida, 502 para fallo/respuesta inválida del proveedor y 504 para timeout. El 429 devuelve `Retry-After` en segundos y `X-Prediction-Next-Allowed-At` con zona. Los rechazos de validación antes de reservar un intento no consultan al proveedor ni consumen cadencia; los fallos de un intento reservado sí la consumen.

Para la futura sesión/telecomando se prevén HTTP 401 para sesión ausente y 409 para comandos incompatibles. El cliente también maneja 5xx, desconexión, respuestas HTML y timeouts de 12 s. Un error al refrescar el snapshot deja los datos visibles y deshabilita escrituras hasta recuperar permisos válidos.

En producción servir `frontend/dist` y `/api` bajo el mismo origen HTTPS; el reverse proxy debe soportar upgrade WebSocket. El proxy de Vite solo es para desarrollo. El backend debe permitir el origen de desarrollo explícitamente y verificar cookies/CSRF con ese esquema. El frontend no instala servicios ni cambia configuración de PostgreSQL.
