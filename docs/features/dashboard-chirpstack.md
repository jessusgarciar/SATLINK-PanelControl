# Dashboard y conexión ChirpStack

Esta etapa adapta los comportamientos del Ejercicio 10 al panel React y a la persistencia PostgreSQL de SATLINK: diagnóstico de recepción, datos del dispositivo y radio, ventanas temporales, exportación CSV, reproducción histórica y bitácora técnica de sesión. Conserva el perfil PICARO FULL de 19 bytes del Ejercicio 09 y la ingestión existente: validar, guardar y confirmar la transacción antes de emitir por WebSocket.

## Recepción, dispositivo y radio

El estado del WebSocket describe la conexión entre navegador y API. El estado de ingestión describe la conexión del backend con MQTT. Tener WebSocket conectado no demuestra que el broker esté conectado ni que haya llegado una lectura nueva. La interfaz muestra esa distinción y conserva los datos anteriores con su antigüedad cuando falla el transporte.

La información del dispositivo procede de los flags y campos realmente transmitidos; la radio procede de los metadatos ChirpStack. Los valores ausentes permanecen desconocidos. Un flag indica el estado informado por el firmware, no prueba la ejecución de un telecomando ni una actuación física. El RSSI y SNR mostrados corresponden a una misma recepción; no se mezclan gateways para fabricar una pareja de mejores valores.

`ingestion` contiene `source`, `status` y `updatedAt`, tanto en el snapshot como en mensajes WebSocket `type: ingestion`. Sus estados son `disabled`, `connecting`, `connected`, `reconnecting` y `offline`; son independientes del estado del WebSocket del navegador. Cada muestra incorpora `device` con `gpsActive`, `gpsFix`, `satellites`, `batteryPct`, `charging` y `usbPowered`, y `radio` con `gatewayId`, `frequencyHz`, `dataRate` y `fPort`.

## Ventanas y CSV

Las ventanas de 15 minutos, 1 hora, 6 horas, 24 horas y todo el historial se consultan en el backend. El archivo PostgreSQL no se limita a las 1200 muestras que conserva normalmente el cliente. El panel puede reducir puntos para visualizar una ventana extensa, pero identifica esa reducción y conserva la distinción entre cantidad almacenada y puntos dibujados.

El CSV exporta todas las muestras del intervalo solicitado, con sus fechas, valores desconocidos y metadatos disponibles; no exporta solo el subconjunto reducido para las gráficas. El esquema de SATLINK responde al perfil binario y al contrato web: no se asume que las 23 columnas del Ejercicio 10 correspondan a sensores presentes en este dispositivo.

`GET /api/v1/missions/{id}/telemetry/window` acepta `from` y `to` opcionales, con fechas RFC3339 y zona. Sin `from` consulta desde el inicio del archivo; sin `to` fija el fin en la hora de la consulta. Devuelve `{from, to, total, series, track}`: `from` puede ser `null`, `total` cuenta todas las muestras del intervalo, `series` contiene como máximo 600 muestras y `track` como máximo 500 puntos. El intervalo es `[from,to)`.

`GET /api/v1/missions/{id}/telemetry/export.csv` usa los mismos filtros y entrega las filas completas: campos de `Telemetry`, metadatos aplanados con prefijos `device_` y `radio_`, y trazabilidad `source`, `applicationId`, `devEui` y `raw_json`. Para exportar exactamente la ventana visible se envían los límites que devolvió la consulta, incluido su `to` fijado.

`raw_json` contiene el evento archivado; una muestra sin ese evento original deja la celda vacía. Los datos desconocidos no se convierten en ceros ni se rellenan con un sobre ficticio.

## Reproducción histórica y bitácora

La reproducción utiliza únicamente muestras ya persistidas de la misión seleccionada. Es una vista histórica aislada de la estación en vivo; no inserta muestras, no publica telemetría y no habilita telecomandos ni solicitudes de predicción. Sus velocidades 1×, 5× y 10× comprimen el tiempo de reproducción y conservan las fechas originales de las muestras. Al salir se recupera el estado de la estación en vivo.

Al abrirla se fijan `from` y `to`; la reproducción utiliza el historial paginado y limita a 1200 las muestras visibles, más una página pendiente de hasta 200 muestras. Durante esta vista no consume el stream en vivo. La paginación es estable para un conjunto que no cambia: si llegan paquetes atrasados dentro del intervalo mientras se consulta, hay que reiniciar el intervalo para incluirlos.

La bitácora técnica registra cambios de conexión, errores y acciones explícitas de filtro, exportación y reproducción durante la sesión del navegador. No representa un registro de cada consulta HTTP exitosa. Es distinta de la bitácora de comandos y no constituye evidencia de recepción, ejecución o liberación física. No se presenta como archivo persistente del backend ni como historial completo tras recargar la página.

Conserva hasta 100 entradas de la sesión y descarta las más antiguas al alcanzar ese límite. Las entradas técnicas no se transforman en eventos físicos de misión.

## Verificación y límites

Las comprobaciones de esta etapa cubren cambios de estado MQTT, reconexión, persistencia antes de publicación, campos ausentes, aislamiento de misiones, ventanas extensas, exportación sin reducción y reproducción sin alterar fechas. Los resultados ejecutados y la revisión visual están en [Verificación PICARO](picaro-verification.md).

La validación con broker y hardware depende de configurar el origen ChirpStack, Application ID, DevEUI, broker y misión reales. Una prueba sintética no acredita recepción RF ni vuelo. La entrega del Ejercicio 10 no agregó firmware, downlinks, autenticación compartida ni predicción Tawhiri; la ampliación posterior del predictor está en [su guía y verificación](prediction-tawhiri.md). El consumidor sigue sin spool MQTT duradero; una caída antes del commit puede perder un uplink.

El estado MQTT refleja el último cambio observado por el consumidor y la suscripción confirmada, no una comprobación continua de salud. Si el consumidor está reintentando guardar una muestra por fallo de PostgreSQL, detectar una caída del broker puede demorarse hasta reanudar la lectura MQTT.
