# Aceptación de telemetría del LilyGO de prueba

## Conectar y observar

Desde `Orbitium`, iniciar la estación en una terminal:

```powershell
.\scripts\start-dev.ps1 -Mode Live
```

Abrir `http://127.0.0.1:5173`. El lanzador toma el ID de `backend/mission.local.json`; la configuración local utiliza `orbitium` / **ORBITIUM**, asociada al LilyGO de prueba. La telemetría simulada transmitida por el LilyGO se observa en **estación real**, porque atraviesa la recepción de ChirpStack y MQTT. El modo DEMOSTRACIÓN genera sus propias lecturas en el navegador.

En otra terminal, también desde `Orbitium`:

```powershell
.\scripts\check-live.ps1 -Samples 10 -TimeoutSeconds 600
```

Para comprobar primero una sola transmisión:

```powershell
.\scripts\check-live.ps1 -Samples 1 -TimeoutSeconds 360
```

El tiempo es un límite máximo: la comprobación termina cuando reúne las muestras solicitadas. Si el dispositivo transmite cada cinco minutos, usar por ejemplo `-Samples 10 -TimeoutSeconds 3600`. Los valores de sensor pueden permanecer constantes si así está programada la simulación; una muestra nueva se identifica por el evento y su trazabilidad, no porque cambie la temperatura.

## Qué verifica automáticamente

1. Configuración efectiva con MQTT habilitado y misión válida, coincidente con el origen configurado.
2. Disponibilidad HTTP del dashboard y correspondencia de misión y DevEUI.
3. WebSocket de esa misión y suscripción MQTT al topic exacto `application/{applicationId}/device/{deviceEui}/event/up`.
4. Uplinks nuevos, no retenidos, con fecha reciente: sobre ChirpStack válido y PICARO FULL de **19 bytes big-endian en fPort 10**.
5. Correlación del evento MQTT original con `raw_json` del CSV por `deduplicationId`, y de la fila persistida con WebSocket por ID de muestra. Comprueba origen, dispositivo, misión, fecha, contador, valores decodificados, campos desconocidos y metadatos de dispositivo/radio.
6. Ausencia de filas duplicadas del mismo evento observado dentro del intervalo exportado.
7. Recuperación de las mismas muestras mediante historial HTTP paginado, separado del stream.
8. Estado conectado del consumidor MQTT del backend al finalizar.

La suscripción de diagnóstico usa un identificador aleatorio y una sesión limpia. No sustituye al consumidor del backend, no publica mensajes y no crea sesiones MQTT persistentes. Los valores, TLS y autenticación proceden de la misma configuración local. Un broker con restricciones adicionales sobre identificadores de cliente puede rechazar esta segunda conexión; revisar sus permisos si se informa un fallo MQTT.
