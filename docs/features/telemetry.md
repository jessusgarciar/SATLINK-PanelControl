# Telemetría del Ejercicio 09

## Funcionalidad

La recepción transforma uplinks ChirpStack del Ejercicio 09 en muestras del contrato SATLINK. El perfil admitido utiliza exactamente 19 bytes y `fPort=10`; su descripción está en [PICARO FULL v1](../protocols/picaro-full-v1.md).

La secuencia de ingestión es: validar el evento y su asociación a una misión, decodificar el payload, identificar duplicados, persistir la muestra y sus metadatos, confirmar la transacción y finalmente emitir `type: telemetry` a los clientes de esa misión. Los mensajes no válidos no se presentan como mediciones ni se convierten en ceros plausibles.

Los metadatos conservan la fuente y trazabilidad del uplink. La combinación `(source, dev_eui, deduplication_id)` distingue retransmisiones de nuevos eventos; no se guarda una sesión inferida. El contador de trama aislado no identifica suficientemente una muestra tras una nueva sesión.

Se expone metadatos normalizados de dispositivo y radio, además del estado de ingestión del backend. `device` conserva GPS activo/fix, satélites, batería porcentual y flags de carga/USB; `radio` conserva gateway, frecuencia, datarate y puerto disponibles. Los campos ausentes o inválidos permanecen desconocidos. El voltaje de batería sigue siendo una medición separada del porcentaje recibido.

## Datos y límites

- Temperatura, presión, batería y GPS proceden del payload medido; RSSI y SNR proceden de ChirpStack.
- `relativeAltitudeM` se calcula únicamente cuando hay altitud GPS válida, restando la altitud de lanzamiento persistida. El resultado puede ser negativo.
- `humidityPct`, `altitudeBarometricM` y `verticalSpeedMs` son `null` en esta etapa: el perfil no transmite humedad y los otros dos cálculos no se implementan todavía.
- La validez del GPS se toma de sus flags. No se utiliza `(0, 0)` como sustituto de una posición ausente.
- Los timestamps de recepción definen el orden del panel. Los mensajes tardíos se conservan sin desplazar una lectura más reciente.
- Los datos de demostración permanecen en el adaptador del frontend. Los fixtures de pruebas son sintéticos y no se ingresan como datos de vuelo real.

La fase de misión no se infiere de la pendiente de dos muestras. El disparador GPS, el watchdog y la actuación física permanecen en firmware. Esta entrega no transmite downlinks.

## Uso

Sigue la [guía del backend](../setup/backend.md) para crear el esquema, registrar la misión, iniciar el servicio y habilitar MQTT. El snapshot HTTP permite recuperar la ventana reciente; el WebSocket agrega muestras nuevas después de guardarlas. Envía heartbeat incluso cuando no hay uplinks.

La estación local funciona sin login inicial y no concede permisos para comandos ni predicción. Consultar una misión inexistente produce `404`; el cliente conserva la distinción entre un backend disponible sin muestras y un fallo de conexión.

El snapshot incluye `ingestion`; los cambios de estado llegan por WebSocket con `type: ingestion`. La conexión MQTT y el WebSocket se muestran por separado: broker conectado no demuestra una lectura reciente, ni WebSocket conectado demuestra enlace con ChirpStack. Consulta [Dashboard y conexión ChirpStack](dashboard-chirpstack.md) para ventanas, exportación y reproducción histórica.

## Verificación

Los casos de aceptación cubren payloads válidos e inválidos, flags GPS, unidades, alturas con signo, duplicados, aislamiento entre misiones, rollback de persistencia y emisión posterior al commit. También se comprueba el arranque sin MQTT y la reconexión del transporte.

Los resultados ejecutados están en [Verificación PICARO](picaro-verification.md). Quedan pendientes una captura real de ChirpStack, pruebas con el dispositivo y validación de radio y vuelo; ninguna prueba sintética los sustituye. El consumidor reintenta en memoria ante fallos de base, pero no tiene un spool duradero de MQTT: una caída del proceso antes del commit puede perder un mensaje.
