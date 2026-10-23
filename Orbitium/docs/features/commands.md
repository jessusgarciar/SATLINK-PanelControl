# Comandos e inicio de misión · ORBITIUM

## Implementado en la aplicación

- `POST /api/v1/missions/{id}/commands`: `{type, clientRequestId}`; UUID canónico en el cuerpo y en `Idempotency-Key`, `Origin` local y `X-CSRF-Token` del dashboard. Devuelve HTTP 202 con `Command`.
- Tipos de esta etapa: `PING`, `STATUS`, `TELEMETRY`, `START_MISSION`. RELEASE real y BEACON_ON/OFF se rechazan con 422. La demo conserva la liberación simulada.
- Migración `0003`: solicitudes y evidencias persistidas. Un UUID repetido devuelve el registro existente sin publicar otra vez; reutilizarlo para otro tipo devuelve 409. No se crean solicitudes duplicadas activas del mismo tipo.
- El snapshot recupera las últimas 100 solicitudes. Los cambios de evidencia se emiten por WebSocket después del commit.
- PING, STATUS y TELEMETRY permiten diagnóstico sin muestras recientes. START_MISSION requiere una muestra reciente de esa misión y confirmación explícita en el panel.
- **Iniciar misión** sustituye a la baliza. El HTTP 202, PUBACK MQTT, txack del gateway y ACK LoRaWAN no equivalen a ejecución.
- Solo la ejecución confirmada de START_MISSION fija `startedAt`; no se infiere ascenso, no se reinicia una misión iniciada y no se cambia el intervalo de radio. Los contadores del panel derivan de la fecha persistida. El temporizador físico debe implementarse en la Heltec.
- `commandSettings` informa disponibilidad, tipos soportados, motivo de bloqueo e intervalo previsto. Sin perfil de firmware, no se conceden permisos ni se publica por MQTT; POST devuelve 503.

## Estado del firmware recibido

`placaheltec.txt:589–621` recibe downlinks y muestra metadatos/bytes por serie, pero no interpreta comandos. El encoder compartido en ChirpStack devuelve siempre `E1 E6 FF 00`; no se usa como implementación de PING/STATUS/TELEM.

Se necesita acordar con el responsable de la placa el puerto, bytes, respuesta de aplicación, correlación y persistencia de misión/watchdog ante reinicios. No se asignaron códigos supuestos.

## Perfil configurable cuando el firmware esté implementado

`SATLINK_COMMAND_PROFILE_FILE` queda vacío por defecto. Cuando se conozcan los bytes aprobados, crear un `backend/command-profile.local.json` privado con esta estructura (los marcadores **no son valores operativos**):

```json
{
  "missionId": "<id persistido de la misión Heltec>",
  "applicationId": "<Application ID de esa misión>",
  "deviceEui": "<DevEUI de 16 caracteres hex minúsculos>",
  "source": "chirpstack-local",
  "fPort": "<sustituir por un entero acordado con firmware>",
  "payloadHex": {
    "PING": "<bytes hex aprobados con {requestId}>",
    "STATUS": "<bytes hex aprobados con {requestId}>",
    "TELEMETRY": "<bytes hex aprobados con {requestId}>",
    "START_MISSION": "<bytes hex aprobados con {requestId} y {watchdogSeconds}>"
  }
}
```

Se pueden definir solo los comandos implementados. `{requestId}` inserta el UUID **del comando persistido** como 16 bytes en orden UUID, sin guiones. `{watchdogSeconds}` inserta cuatro bytes uint32 big-endian. Su colocación y los bytes restantes los determina el perfil acordado con la placa. Si el firmware elige otra codificación se adaptará este encoder; estos marcadores no describen el firmware actual.

Al establecer la variable y reiniciar, se exige coincidencia entre perfil, source y topic MQTT de la configuración activa. Cada envío comprueba misión, Application ID y DevEUI contra PostgreSQL. El tipo solo se habilita si existe en el perfil.

Publicación: `application/{app}/device/{eui}/command/down`, JSON ChirpStack con `id` igual al UUID del comando, `devEui`, `fPort`, `confirmed=true` y `data` Base64. QoS 1, `retain=false`, cliente MQTT temporal distinto del de ingestión y sin reintentos de aplicación. El broker MQTT 3.1.1 puede confirmar PUBACK aunque una ACL descarte la publicación; PUBACK no prueba autorización efectiva ni encolado en ChirpStack.

Un fallo de publicación deja evidencia **incierta** persistida y no vuelve a enviar. Al reiniciar el proceso no se reproducen automáticamente solicitudes pendientes. Esto no garantiza entrega exactamente una vez por radio: el firmware debe deduplicar por requestId.

## Evidencias y respuesta de ejecución

- `event/txack` del dispositivo exacto y `queueItemId` coincidente → `sent`: gateway aceptó/programó el downlink; no prueba recepción.
- `event/ack`, `acknowledged=true` → `received`: ACK LoRaWAN; no prueba ejecución.
- `event/ack`, `acknowledged=false` → `expired`: ChirpStack no obtuvo ACK; no afirma que sea imposible una ejecución física.
- Eventos retenidos, ajenos o no correlacionados se ignoran. Eventos atrasados no degradan estados y los estados terminales se conservan.

`RequestCommand.update` es el puerto interno para el futuro decoder de respuestas de aplicación. Para START_MISSION ejecutado requiere una fecha UTC con zona, posterior a la solicitud y no futura. La respuesta debe ser validada por el adaptador contra puerto, origen, dispositivo, tipo e identificador antes de invocarlo. **No hay un endpoint HTTP que permita al navegador fingir esa confirmación**, ni se interpreta un GPS cualquiera como ejecución. Aún no se conecta un decoder de ejecución porque el formato no fue proporcionado.

## Intervalos

Intervalo esperado: 21600 s. Antigüedad máxima: 21900 s. El watchdog existente es 3300 s; su duración y la acción al vencer siguen pendientes de acuerdo con la placa. No se programa liberación automática. Clase A recibe después de un uplink: con seis horas entre envíos, un comando puede esperar aproximadamente ese tiempo y su respuesta puede requerir otro uplink. Una preparación de 30 s debe implementarse explícitamente en firmware si se desea; la app no modifica esa cadencia.

## Identidad y comprobaciones

Ver [Configuración de Orbitium](../setup/orbitium.md) para el diagnóstico entre firmware, archivo local y base. La misión seleccionada es `orbitium-original`, ya vinculada a la Heltec. `orbitium` conserva el dispositivo y las muestras del LilyGO de pruebas.

Pruebas nuevas cubren idempotencia concurrente, tipos/origen/token inválidos, ausencia de perfil, publicación incierta, identidad del destino, ACKs ajenos/atrasados, inicio pendiente frente a ejecutado, persistencia y el umbral de seis horas. Los transportes se simulan; no acreditan recepción RF ni ejecución en hardware.

Desde `frontend`, `npm run test:commands-ui` verifica el diálogo de inicio, cancelación, solicitud única, contadores pendientes/confirmados y el bloqueo por firmware pendiente en una pantalla de 375 px, con HTTP/WebSocket sintéticos y movimiento reducido. `npm test`, `npm run build` y `npm run lint` completan las comprobaciones del cliente.
