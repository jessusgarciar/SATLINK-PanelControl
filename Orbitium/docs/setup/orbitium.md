# ORBITIUM

## Configuración local


`staleAfterSeconds=360` (6 minutos) y región US915 son provisionales hasta comprobar el dispositivo. El umbral deja un minuto de margen si el intervalo de transmisión resulta ser de 5 minutos; solo determina cuándo el panel y las comprobaciones de antigüedad consideran obsoleta una muestra. No cambia la frecuencia de transmisión ni el consumo de batería del firmware. El firmware de referencia [Ejercicio 09 PICARO FULL](https://github.com/ovelazquezj/radiosonda_PIcaro/tree/master/specs/exercises/09_radiosonda_picaro_full) transmite cada 30 s por defecto, con 19 bytes big-endian en fPort 10. No se ha confirmado la versión ni el intervalo configurado en el dispositivo. Un payload diferente requiere revisar compatibilidad; un decoder en ChirpStack no cambia los bytes transmitidos.

## Arranque

Desde `Orbitium` (o desde la raíz con `-App Orbitium`):

```powershell
.\scripts\start-dev.ps1 -Mode Live
```

El lanzador valida configuración, inicia PostgreSQL si hace falta, aplica migraciones, registra la misión mediante `init-mission`, inicia backend/frontend y comprueba el dashboard de la misión. Mantiene logs en la terminal y en `.local/dev-logs`. `-NoBrowser` evita abrir el navegador. Ctrl+C detiene frontend y backend; PostgreSQL permanece activo para la otra aplicación. Una misión existente permite actualizar únicamente `staleAfterSeconds`; cualquier otro cambio de configuración se rechaza y no se elimina ni sobrescribe el historial.

`frontend/.env.local` selecciona `orbitium` cuando se cambia de demo a estación real; `-Mode Live` también inicia directamente en estación real. La demo conserva sus datos de ejemplo.

## Recepción de telemetría

La conexión configurada se valida contra el broker con resolución DNS, acceso al puerto, TLS, autenticación y permiso de suscripción. Los valores permanecen en `backend/.env`; no copiarlos a documentación, logs compartidos ni chats. TLS usa la CA del sistema y verifica el certificado y hostname del servidor, sin certificado de cliente.


Al iniciar, retira del cliente MQTT la suscripción wildcard heredada y solicita el topic exacto. El decoder procesa únicamente uplinks `event/up`; no se suscribe a `event/#`. Si el cliente informa conectado, significa que la conexión y la suscripción fueron aceptadas, no que se haya recibido telemetría.

Para completar la aceptación con el dispositivo encendido, esperar un evento `up` y comprobar Application ID, DevEUI, `fPort=10`, `data` de 19 bytes tras decodificar base64 e intervalo de transmisión observado. No interpretar tramas de otras longitudes con un formato supuesto; registrar la incompatibilidad y revisar la versión/configuración del firmware. Revisar también la región del device profile; el panel actual admite US915.

La configuración local del broker se mantiene en `backend/.env`:

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

El arranque Live muestra disponibilidad del backend por HTTP; el estado MQTT representa conexión más suscripción. La recepción se confirma por separado cuando el uplink del DevEUI indicado aparece almacenado en PostgreSQL y visible en dashboard, historial y WebSocket. Las pruebas sintéticas verifican el flujo de software, pero no sustituyen la recepción física.

Los comandos reales siguen deshabilitados (`canCommand=false`). La recepción no demuestra que PING o RELEASE estén implementados ni habilita su envío.

## Predicción

La predicción real mantiene la bandera existente `SATLINK_PREDICTION_ENABLED=false`. Para habilitarla posteriormente, confirmar las referencias de altitud del GPS y configurar las referencias por misión según [la guía de Tawhiri](../features/prediction-tawhiri.md). La altitud de lanzamiento fue proporcionada como MSL; el datum del GPS sigue pendiente.
