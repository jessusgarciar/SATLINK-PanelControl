# Telemetría VUELO del LILYGO

ORBITIUM acepta PICARO FULL (19 bytes big-endian, fPort 10) y VUELO D-64
(11 bytes little-endian, fPort 17). La estructura VUELO se contrastó el
15 de octubre de 2026 con el codec visible del perfil Radiosonda-Terreno-ClaseA
y con eventos `up` de ChirpStack. No requiere cambiar el firmware ni el perfil.

El byte 0 contiene el tipo en los dos bits superiores y el identificador de
ráfaga en los seis restantes. Los diez bytes siguientes dependen del tipo:

| Tipo | Datos, en orden |
| --- | --- |
| 1, posición | latitud i32 / 1e7, longitud i32 / 1e7, altitud u16 m |
| 2, ambiente | temperatura i16 / 100, presión u16 / 10, humedad u8, batería u16 / 1000, porcentaje u8, satélites u8, banderas u8 |
| 3, navegación | velocidad u16 / 10 km/h, rumbo u16 / 10 grados, HDOP u8 / 10, velocidad vertical i16 / 10 m/s, uptime u24 s |

Las banderas de ambiente indican fix GPS (bit 0), USB (1), carga (2), GPS
activo (3), magnetómetro (4) y BME (5). No coinciden con las de PICARO FULL.
Los sentinelas 0x7fff para i16, 0xffff para u16 y 0xff para u8 se conservan
como desconocidos según el campo; posiciones (0, 0) indican ausencia de fix.
Se validan además rangos físicos antes de publicar las medidas.

Cada uplink se archiva por separado con su JSON original, tipo y ráfaga.
No se mezclan paquetes ni se asigna una fecha nueva a medidas anteriores.
Los campos ausentes quedan en null en el archivo. Las tarjetas conservan la
última lectura disponible de cada campo y los detalles GNSS/radio; cada sensor
conserva su fecha original para marcar lecturas antiguas. La hora y contador
de «Último dato» corresponden siempre al último paquete recibido.
Las gráficas unen las mediciones disponibles de cada variable usando su hora
de recepción y muestran puntos incluso con una sola lectura; no dependen de
que la misión tenga una hora de lanzamiento ni rellenan medidas ausentes.
Velocidad horizontal, rumbo,
HDOP y uptime quedan en metadatos, sin ampliar el contrato visual del panel.
Los paquetes de prueba recibidos por radio siguen siendo datos de prueba;
el transporte real no demuestra mediciones físicas ni un vuelo.

La compatibilidad del codec es independiente de la entrega MQTT. Una
suscripción aceptada sin eventos no demuestra que ChirpStack esté publicando
en ese broker/topic o que sus permisos permitan recibirlos. No se habilitan
comandos ni predicción por añadir este formato.
