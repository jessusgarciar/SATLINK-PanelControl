# Telemetría PICARO FULL v1

Perfil del Ejercicio 09: **19 bytes exactos, big-endian, fPort 10**. El identificador interno `picaro-full-19-v1` pertenece al codec del backend; no hay byte de versión en la trama. Cambiar las opciones de sensores del firmware exige acordar otro perfil y su codec. El backend no adapta automáticamente longitudes distintas ni modifica firmware o ADR.

## Distribución binaria

| Bytes | Tipo | Contenido | Conversión |
| --- | --- | --- | --- |
| 0 | uint8 | Estado | bit0 fix GPS, bit1 cargando, bit2 USB, bit3 IMU, bit4 magnetómetro, bit5 GPS activo |
| 1–4 | int32 | Latitud | dividir entre 1 000 000; grados |
| 5–8 | int32 | Longitud | dividir entre 1 000 000; grados |
| 9–10 | int16 | Altitud GPS | metros |
| 11 | uint8 | Satélites | entero |
| 12–13 | uint16 | Batería | dividir entre 1000; voltios |
| 14 | uint8 | Batería porcentual | 0–100; 255 desconocido |
| 15–16 | int16 | Temperatura | dividir entre 100; °C |
| 17–18 | uint16 | Presión | dividir entre 10; hPa |

El formato no transmite humedad, IMU, rumbo ni fecha de medición. Sus flags no agregan esas lecturas. La microSD del firmware queda fuera de esta integración. Los 19 bytes no caben en el perfil US915 DR0 descrito en el ejercicio; se necesita un datarate que los admita (DR1 o superior). No se promete alcance de radio a partir de esta integración de software.

Vector del Ejercicio 09: `04 00000000 00000000 0000 00 01CC 00 0A34 1FDB`: sin fix, USB activo, 0.460 V, 26.12 °C y 815.5 hPa. Se usa como vector de prueba; no como lectura actual de hardware.

## Normalización

`gpsFix=false` implica `latitude`, `longitude` y `altitudeGpsM` en `null`, aunque los bytes contengan cero u otra posición. Coordenadas fuera de ±90/±180 invalidan la pareja y altitud. `(0,0)` con fix sí es una posición válida. `gpsActive` se conserva como metadato, sin inferir confirmación de enlace.

Se conservan como mediciones los valores dentro de los rangos del contrato: GPS −500 a 32767 m en este perfil, temperatura −127 a 127 °C, presión 5 a 1270 hPa y batería 0 a 5.08 V. Fuera de ellos se entrega `null`, preservando la trama original. Estos rangos de transporte no certifican el rango metrológico del sensor. **255 hPa es una presión válida**, no el sentinel del antiguo borrador compacto. La batería porcentual fuera de 0–100 se normaliza a desconocida y permanece en metadatos internos.

`humidityPct`, `altitudeBarometricM` y `verticalSpeedMs` son `null`. Solo se deriva `relativeAltitudeM = altitudeGpsM − launch.altitudeM`. El origen configurado debe usar el mismo datum de altitud que el GPS. No se toma el primer paquete como origen ni se recortan lecturas superiores a 15 km.

El firmware puede producir ceros ambientales que este formato no permite distinguir de una lectura fallida. No se inventan flags de calidad; cero °C sigue siendo válido. El payload y los metadatos de origen permiten revisar esa limitación posteriormente.

## Sobre ChirpStack y persistencia

Entrada JSON en `application/{applicationId}/device/{devEui}/event/up`; topic y sobre deben coincidir exactamente. El sobre exige `deviceInfo`, `deduplicationId` UUID, `time` RFC3339 con zona, `fPort` y `data` Base64. `fCnt` admite uint32; su omisión representa cero según la serialización Protobuf JSON. Se guarda la hora ChirpStack como `receivedAt` en UTC y la hora de ingestión por separado. Eventos mayores de 256 KiB se rechazan; se archiva solo el prefijo hasta ese límite con indicador de truncamiento.

La misión se resuelve por origen configurado, applicationId y DevEUI. La unicidad persistente es `(source, dev_eui, deduplication_id)`. Un contador repetido con otro ID no colisiona; no se infieren sesiones a partir del contador. No hay alta automática de misiones o dispositivos.

Se conservan el mensaje MQTT original, sobre completo, flags, porcentaje recibido, versión del codec y todos los `rxInfo`. Para la interfaz se elige la recepción con mayor SNR válido, luego RSSI y gatewayId como desempate; RSSI y SNR provienen siempre del mismo gateway. Valores inválidos o ausentes quedan en `null`.

Expone los metadatos guardados como `device` y `radio`, sin cambiar el formato binario ni agregar sensores. `device` incluye GPS activo/fix, satélites, batería porcentual y flags de carga/USB. `radio` incluye gateway seleccionado, frecuencia en Hz, datarate y puerto. Los campos ausentes siguen en `null`; el porcentaje recibido no se calcula a partir del voltaje. El historial anterior se enriquece únicamente con metadatos que ya estaban archivados, sin inventar observaciones ni requerir una nueva captura física.

El commit de evento y muestra es atómico y precede a WebSocket. Un duplicado no vuelve a emitirse. Los rechazos se archivan sin publicarse. Una emisión fallida se recupera mediante snapshot/historial. MQTT usa suscripción QoS 1 y reconexión; si falla la base se reintenta el mensaje en memoria. **No existe spool duradero de MQTT**: el ACK del cliente MQTT no está unido al commit, por lo que un cierre del proceso antes de guardar puede perder un mensaje. Tampoco puede recuperarse tráfico que ChirpStack no haya recibido.

Las pruebas usan una base separada y eventos sintéticos. En operación, el consumidor solo recibe del broker configurado; no existe endpoint de simulación o inyección HTTP. La procedencia `chirpstack` identifica el transporte, no demuestra por sí sola una recepción física de radio.
