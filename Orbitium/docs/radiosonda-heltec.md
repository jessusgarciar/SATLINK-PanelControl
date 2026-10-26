# Heltec: protocolo radiosonda v1

Implementación alineada con `C:/Dev/radiosonda_heltec_itpa_tics/docs/RADIOSONDA-ESPEC.md` y `CAMBIOS-PANEL.md`.

## Configuración

En `backend/mission.local.json`, conservar id, source, Application ID y DevEUI de la misión real. Usar:

```json
{
  "telemetryProtocol": "radiosonda-v1",
  "altitudeTargetMode": "absolute",
  "targetRelativeAltitudeM": 15000,
  "watchdogSeconds": 3300,
  "staleAfterSeconds": 900
}
```

El nombre histórico `targetRelativeAltitudeM` se conserva en la API por compatibilidad: con `altitudeTargetMode: absolute` significa altitud absoluta del dispositivo. No se suma la elevación del lanzamiento, tampoco en la solicitud a Tawhiri. El predictor sigue requiriendo declaración de datum MSL; recibir un número GPS no certifica su datum.

Aplicar migraciones con `.venv/Scripts/python.exe -m alembic upgrade head` e inicializar la misma misión con `.venv/Scripts/python.exe -m app.bootstrap.cli init-mission --file mission.local.json`, desde backend. La actualización de protocolo/cadencia conserva identidad, historial e inicio almacenado. No usar otro id para duplicar el mismo dispositivo.

Si MQTT está habilitado y no hay `SATLINK_COMMAND_PROFILE_FILE`, se construye el adaptador radiosonda desde la identidad local, comprobando source y topic exactos. Para un perfil explícito usar `protocol: radiosonda-v1`, missionId, applicationId, deviceEui y source; no requiere plantillas UUID. Un perfil antiguo no habilita comandos para una misión radiosonda.

## Recepción

- 20: GPS y satélites; 21: sensor externo y batería %; 22: voltaje y uptime; 23: banderas de vuelo y corte.
- 30: Polo; 31: eventos de corte. Se archivan, pero no generan muestras de sensores ni puntos de ruta.
- El backend continúa consumiendo `event/up`. `txack` y `ack` son evidencia de transporte, nunca de corte físico.
- No se exige que los cuatro paquetes tengan fCnt consecutivos: el firmware puede intercalar respuestas. No se afirma disponer de una lectura completa si faltan partes.
- Cada muestra conserva sus propios campos y metadatos de presencia. La proyección visual busca la última observación de cada magnitud y conserva su fecha; un null explícito invalida el valor anterior. Las gráficas no rellenan puntos entre paquetes.
- La predicción de ascenso usa el último paquete que contiene posición; un nuevo paquete sin fix impide reutilizar una posición anterior como actual.

## Comandos y estado

MARCO publica un byte de secuencia por fPort 30. CORTE publica `CORT` seguido de la secuencia por fPort 31. Ambos usan confirmed=false, retain=false y no se reenvían automáticamente si la publicación es incierta.

La secuencia se reserva y persiste antes de publicar, bajo bloqueo por misión. Se utilizan 1–255 sin reutilización dentro de la misión. Al agotar las secuencias se rechazan solicitudes adicionales. Respuestas se correlacionan por misión/dispositivo, tipo, secuencia y ventana de 15 minutos; las solicitudes vencidas conservan evidencia de ejecución desconocida. La secuencia por sí sola no autentica un evento fuera de ChirpStack.

Polo confirma MARCO y reporta RTT desde la reserva local hasta el evento recibido, más RSSI/SNR del downlink. Un evento de corte de motivo automático o consola no se atribuye a un comando. `inicio`, `confirmado` y `sin_confirmar` se conservan por separado. `executed` en un comando terminado describe la secuencia ejecutada; el resultado físico está en `result.evento`, y la interfaz muestra explícitamente sin confirmar.

No hay botón START_MISSION en este perfil. El inicio/watchdog pertenecen al dispositivo. `flightState` guarda el último estado recibido y su hora; no inventa un instante de activación ni un contador continuo si el firmware no lo reporta. El estado general de ascenso/descenso no se infiere del simple indicador enVuelo.

## Historial en Info

Al final de Info se consulta `GET /api/v1/missions/{id}/packets?limit=50&cursor=...`. Pagina los eventos recibidos por hora de ingestión e id, incluidos rechazados asociados al topic exacto de la misión y respuestas de comandos. Cada selección muestra solo su contenido, evento original, payload Base64, datos decodificados y motivo de rechazo. Los rechazados antiguos sin misión asociada no se reasignan retrospectivamente.

## Validación

- Backend: pytest con `SATLINK_TEST_DATABASE_URL` apuntando exclusivamente a una base terminada en `_test`.
- Frontend: `npm test`, `npm run build`, `npm run lint`.
- UI sintética: `npm run test:radiosonda-ui` (Edge headless en Windows). Bloquea conexiones externas y usa fixtures HTTP/WebSocket.
- Prueba física pendiente: uplinks reales 20–23, MARCO/Polo y corte con LED siguiendo la guía de Electrónica. Una prueba local o sintética no acredita cobertura RF ni funcionamiento del nicromo.

Los problemas OTAA/DevNonce, sensores, cableado, perfil de radio y validación del corte físico corresponden a Electrónica/LoRaWAN. Este cambio no modifica firmware ni borra contadores de seguridad.
