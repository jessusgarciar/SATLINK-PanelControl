# ORBITIUM

## Configuración local

`backend/mission.local.json` contiene el ID `orbitium`, nombre ORBITIUM, Application ID `2bc02a29-7e6a-49f8-8fab-701daef2c30a`, DevEUI `b45a2b79a8d3cadf`, lanzamiento `22.160278, -102.269626` a 1911 m MSL, objetivo relativo de 15000 m (16911 m MSL), ascenso y descenso de 5 m/s y watchdog de 3300 s. Estos parámetros no reprograman el firmware ni ejecutan acciones físicas.

`staleAfterSeconds=90` y región US915 son provisionales hasta comprobar el dispositivo. El firmware de referencia [Ejercicio 09 PICARO FULL](https://github.com/ovelazquezj/radiosonda_PIcaro/tree/master/specs/exercises/09_radiosonda_picaro_full) transmite cada 30 s por defecto, con 19 bytes big-endian en fPort 10. No se ha confirmado la versión instalada. Un payload diferente requiere revisar compatibilidad; un decoder en ChirpStack no cambia los bytes transmitidos.

## Arranque

Desde `Orbitium` (o desde la raíz con `-App Orbitium`):

```powershell
.\scripts\start-dev.ps1 -Mode Live
```

El lanzador valida configuración, inicia PostgreSQL si hace falta, aplica migraciones, registra la misión mediante `init-mission`, inicia backend/frontend y comprueba el dashboard de la misión. Mantiene logs en la terminal y en `.local/dev-logs`. `-NoBrowser` evita abrir el navegador. Ctrl+C detiene frontend y backend; PostgreSQL permanece activo para la otra aplicación. Una misión existente con configuración distinta produce un error; no se elimina ni sobrescribe su historial.

`frontend/.env.local` selecciona `orbitium` cuando se cambia de demo a estación real; `-Mode Live` también inicia directamente en estación real. La demo conserva sus datos de ejemplo.

## Datos que faltan para recibir telemetría

1. **Broker accesible desde esta computadora:** hostname o IP externo, puerto y si requiere TLS. La URL web `https://lns.pi-caro.org/` no confirma estos datos.
2. **Autenticación MQTT:** usuario/contraseña existentes o confirmación de acceso sin credenciales. Si requiere certificados cliente o CA privada, el consumidor actual necesita adaptación; no desactivar la validación TLS.
3. **Permisos de suscripción:** el consumidor actual solicita `application/+/device/+/event/up`. Confirmar que la cuenta puede suscribirse a ese filtro; si permite únicamente ORBITIUM, habrá que restringir el filtro antes de conectar.
4. **Un evento `up` del DevEUI indicado:** comprobar Application ID, fPort 10, campo `data` de 19 bytes decodificados desde base64 y frecuencia real de transmisión. Revisar también la región del device profile; el panel actual admite US915.

Con acceso solo como administrador web, solicitar los puntos 1–3 al administrador del servidor. No compartir contraseñas en el chat: colocarlas directamente en `backend/.env`.

En el [despliegue de ejemplo PI-CARO](https://github.com/ovelazquezj/radiosonda_PIcaro/tree/master/specs/exercises/00_chirpstack-docker), el broker está en `configuration/chirpstack/chirpstack.toml`, sección `[integration.mqtt]`; Mosquitto configura listeners y autenticación en `configuration/mosquitto/config/mosquitto.conf`. El puerto 1883 y acceso anónimo de ese laboratorio no acreditan la configuración del LNS público.

Una vez confirmados los datos y el payload, completar estas variables en `backend/.env`:

```dotenv
SATLINK_MQTT_ENABLED=true
SATLINK_MQTT_HOST=<hostname o IP, sin https://>
SATLINK_MQTT_PORT=<puerto confirmado>
SATLINK_MQTT_USERNAME=<usuario, o vacío si no requiere>
SATLINK_MQTT_PASSWORD=<contraseña, o vacío si no requiere>
SATLINK_MQTT_TLS=<true o false según configuración confirmada>
SATLINK_MQTT_CLIENT_ID=satlink-orbitium
SATLINK_CHIRPSTACK_SOURCE=chirpstack-local
```

Mientras falten estos datos, conservar `SATLINK_MQTT_ENABLED=false`. Verificar luego recepción MQTT, persistencia PostgreSQL y actualización HTTP/WebSocket con un uplink real. La ausencia de hardware no se sustituye por telemetría inventada.

## Predicción

La predicción real mantiene la bandera existente `SATLINK_PREDICTION_ENABLED=false`. Para habilitarla posteriormente, confirmar las referencias de altitud del GPS y configurar las referencias por misión según [la guía de Tawhiri](../features/prediction-tawhiri.md). La altitud de lanzamiento fue proporcionada como MSL; el datum del GPS sigue pendiente.
