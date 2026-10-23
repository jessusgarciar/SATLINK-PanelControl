# Comandos e inicio de misión · SATLINK / system

Solo la ejecución confirmada por el firmware fija `startedAt` y activa los contadores de misión y watchdog. Un HTTP 202, PUBACK MQTT, txack del gateway o ACK LoRaWAN no acreditan ejecución. El inicio tampoco confirma ascenso ni cambia la cadencia de radio. El watchdog utiliza la duración configurada en la misión de Pendiente; su temporizador físico corresponde al firmware.

## Backend y persistencia

- `POST /api/v1/missions/{id}/commands` recibe `{type, clientRequestId}`. Exige un UUID, el mismo valor en `Idempotency-Key`, un `Origin` local permitido y el `X-CSRF-Token` del dashboard.
- Tipos reales admitidos por el soporte trasladado: `PING`, `STATUS`, `TELEMETRY`, `START_MISSION`. `BEACON_ON`, `BEACON_OFF` y liberación real se rechazan. La demo conserva su liberación simulada.
- La migración `0003` agrega la tabla `commands`. Una solicitud repetida devuelve el registro existente sin reenviar; reutilizar su identificador para otro tipo devuelve 409.
- El dashboard recupera las últimas 100 solicitudes y publica `commandSettings` con disponibilidad, tipos y motivo de bloqueo. Los cambios confirmados se notifican por WebSocket después del commit.
- Los diagnósticos permiten operar sin muestras recientes; iniciar misión requiere una muestra reciente de esa misma misión.

Antes de iniciar el backend, desde `Pendiente/backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

El lanzador habitual también prepara las migraciones. Este traslado conserva la identidad, parámetros, puertos y configuración privada de Pendiente.

## Perfil del firmware

Sin `SATLINK_COMMAND_PROFILE_FILE`, los envíos reales permanecen deshabilitados y el POST devuelve 503. La implementación de Orbitium tampoco incluye un decoder de confirmaciones de ejecución del firmware: se trasladó el mismo soporte, sin inventar bytes de radio ni simular confirmaciones en la estación real.

Cuando exista un protocolo aprobado, configurar un archivo privado `backend/command-profile.local.json` y establecer `SATLINK_COMMAND_PROFILE_FILE=command-profile.local.json`. Debe contener `missionId`, `applicationId`, `deviceEui`, `source`, `fPort` y un objeto `payloadHex` con los tipos implementados. Todos los valores de identidad deben pertenecer a Pendiente y coincidir con la misión persistida y el topic MQTT activo.

Cada plantilla hexadecimal requiere `{requestId}` (UUID del comando persistido, 16 bytes); `START_MISSION` requiere además `{watchdogSeconds}` (uint32 big-endian). El puerto y los bytes restantes deben acordarse con el firmware. No se suministra un perfil operativo.

El adaptador publica en `application/{app}/device/{eui}/command/down`, QoS 1, sin retención, con cliente separado. Correlaciona `event/txack` y `event/ack` mediante dispositivo y `queueItemId`; ignora eventos ajenos y no degrada estados con evidencias atrasadas. Un envío incierto queda registrado y no se reintenta automáticamente.

El puerto interno `RequestCommand.update` permite integrar posteriormente un decoder validado. Para ejecutar `START_MISSION` exige fecha con zona horaria, posterior a la solicitud y no futura. No existe un endpoint para que el navegador invente esa confirmación. El valor informativo de intervalo heredado del soporte de Orbitium es 21600 s; este traslado no modifica los intervalos ni la antigüedad máxima configurados en Pendiente.

## Comprobaciones

`npm test`, `npm run build`, `npm run lint` y `npm run test:commands-ui`, desde `frontend`, comprueban el controlador y la confirmación en pantalla móvil con HTTP/WebSocket sintéticos. Desde `backend`, `python -m pytest -q` incluye perfil y transporte simulado; las pruebas de persistencia requieren una base exclusiva terminada en `_test` mediante `SATLINK_TEST_DATABASE_URL`.

Estas pruebas no acreditan recepción de radio ni ejecución física.
