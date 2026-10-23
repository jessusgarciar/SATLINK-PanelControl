# ORBITIUM

## Configuración local

La misión de la **Heltec WiFi LoRa 32 V3** es `orbitium-original`, con nombre persistido **ORBITIUM ORIGINAL**. `frontend/.env.local` (`VITE_MISSION_ID`) y `backend/mission.local.json` (`id`) seleccionan esa misma misión. El archivo local también debe coincidir con la aplicación y el dispositivo registrados en PostgreSQL; cambiar únicamente el nombre o el ID no reasocia un dispositivo existente. El guardado de parámetros rechaza estas discrepancias con HTTP 409 y el panel muestra el detalle del conflicto.

La comprobación del 22 de octubre de 2026 detectó que `orbitium` seleccionaba el dispositivo de pruebas `02389205358e71db`, aplicación `00a687c6-727a-4b61-8c25-33ec7962814f` (80 muestras archivadas). La Heltec del firmware compartido tiene DevEUI `b45a2b79a8d3cadf`, aplicación `2bc02a29-7e6a-49f8-8fab-701daef2c30a`, y ya estaba registrada como `orbitium-original`. Se seleccionó esta misión existente conservando sus parámetros y manteniendo separado el historial del LilyGO de pruebas; no se reasignaron muestras. La Heltec todavía no tiene muestras archivadas en esa base.

La operación prevista utiliza envíos cada **6 horas** (`PICARO_UPLINK_INTERVAL_S=21600`). `staleAfterSeconds=21900` (**6 horas y 5 minutos**) deja cinco minutos de margen. Backend y frontend admiten umbrales de hasta un día. El inicio de misión y las predicciones que requieren GPS comprueban su antigüedad; PING/STATUS/TELEM permiten diagnóstico incluso sin muestras recientes cuando exista un protocolo habilitado. Cambiar el umbral no modifica la frecuencia del firmware. La región es US915.

Las gráficas del panel y del historial usan una escala temporal con divisiones cada **10 minutos**, alineadas a `:00`, `:10`, `:20`, etc. Las etiquetas muestran `HH:mm` en hora de Aguascalientes (UTC−06:00), con fecha al cruzar medianoche; al consultar un punto se muestra su fecha y hora completas. En pantallas estrechas se ocultan etiquetas superpuestas, conservando las divisiones. Los puntos mantienen las horas reales de recepción y las líneas indican tendencia: no se rellenan datos entre los envíos ni se desplazan las lecturas al inicio de un intervalo de resumen.

Los archivos compartidos `placaheltec.txt`, `boardheltec.txt` y `configlorawan.txt` corresponden a la Heltec del Ejercicio 12. El sketch construye GPS de 11 bytes little-endian, tipo 1 de VUELO D-64, en **fPort 17**, y espera el máximo entre seis horas y el tiempo exigido por RadioLib. Lee BME280 y batería, pero no los incluye en ese payload GPS. Orbitium también admite PICARO FULL de 19 bytes big-endian/fPort 10. Un decoder en ChirpStack no cambia los bytes transmitidos.

Tras aplicar las migraciones, comprobar identidad desde `Orbitium/backend`:

```powershell
./.venv/Scripts/python.exe -m app.bootstrap.cli check-identity --file mission.local.json --firmware ../configlorawan.txt
```

Compara únicamente identidad, origen y configuración persistida; no imprime la AppKey ni se conecta al broker. `matched` acredita coherencia local, no recepción RF. `latestTelemetryAt=null` indica que la misión no tiene muestras.

## Arranque

Desde `Orbitium` (o desde la raíz con `-App Orbitium`):

```powershell
.\scripts\start-dev.ps1 -Mode Live
```

El lanzador valida configuración, inicia PostgreSQL si hace falta, aplica migraciones, registra la misión mediante `init-mission`, inicia backend/frontend y comprueba el dashboard de la misión. Mantiene logs en la terminal y en `.local/dev-logs`. `-NoBrowser` evita abrir el navegador. Ctrl+C detiene frontend y backend; PostgreSQL permanece activo para la otra aplicación. Una misión existente permite actualizar únicamente `staleAfterSeconds`; cualquier otro cambio de configuración se rechaza y no se elimina ni sobrescribe el historial.

`frontend/.env.local` selecciona `orbitium` cuando se cambia de demo a estación real; `-Mode Live` también inicia directamente en estación real. La demo conserva sus datos de ejemplo.

## Recepción de telemetría

La conexión configurada se valida contra el broker con resolución DNS, acceso al puerto, TLS, autenticación y permiso de suscripción. Los valores permanecen en `backend/.env`; no copiarlos a documentación, logs compartidos ni chats. TLS usa la CA del sistema y verifica el certificado y hostname del servidor, sin certificado de cliente.


Al iniciar, retira del cliente MQTT la suscripción wildcard heredada y solicita el topic exacto. El decoder procesa uplinks `event/up`; un perfil de comandos habilitado añade únicamente los topics exactos `event/txack` y `event/ack`, sin suscribirse a `event/#`. Si el cliente informa conectado, significa que la conexión y la suscripción fueron aceptadas, no que se haya recibido telemetría.

Para completar la aceptación con la Heltec encendida, esperar un evento `up` y comprobar Application ID, DevEUI, `fPort=17`, `data` de 11 bytes tras decodificar base64 e intervalo observado. No interpretar tramas de otras longitudes con un formato supuesto. Revisar también la región US915 del device profile.

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

La aplicación implementa solicitudes PING, STATUS, TELEMETRY y START_MISSION, con persistencia, CSRF e idempotencia. **Iniciar misión** reemplaza a Baliza ON/OFF; el inicio confirmado fija `startedAt` sin afirmar ascenso ni reiniciar una misión existente. El watchdog configurado sigue siendo **3300 s (55 minutos)**, independiente de las seis horas de telemetría. No se definió una actuación automática al vencerlo. RELEASE real no está implementado.

El firmware compartido solo imprime downlinks; por eso `canCommand=false` y el panel explica que falta el protocolo. El POST responde 503 y no publica sin un perfil explícito compatible. La integración de respuestas de ejecución, incluido START_MISSION, requiere el formato del firmware; ACK/txack no arrancan los contadores. Consulta [Comandos e inicio de misión](../features/commands.md).

Para verificar automáticamente uplinks nuevos contra WebSocket, CSV e historial, ejecutar `./scripts/check-live.ps1` en otra terminal desde `Orbitium`. El informe y el diagnóstico se explican en [Aceptación de telemetría del LilyGO](../features/live-telemetry-check.md).

## Predicción

La predicción real mantiene la bandera existente `SATLINK_PREDICTION_ENABLED=false`. Para habilitarla posteriormente, confirmar las referencias de altitud del GPS y configurar las referencias por misión según [la guía de Tawhiri](../features/prediction-tawhiri.md). La altitud de lanzamiento fue proporcionada como MSL; el datum del GPS sigue pendiente.
