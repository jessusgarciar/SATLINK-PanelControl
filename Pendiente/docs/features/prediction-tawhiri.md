# Predicción Tawhiri y comparación con SondeHub

La integración solicita un perfil físico de ascenso/descenso a Tawhiri desde el backend, normaliza su resultado y conserva la última predicción válida en PostgreSQL. Se mantiene separada de la telemetría recibida y del escenario de vientos constantes de demostración. Solicitar un cálculo no envía un comando al dispositivo. La precisión física del vuelo permanece pendiente de mediciones observadas.

## Configuración y operación

Sigue [la configuración del backend](../setup/backend.md#habilitar-predicción-local) y aplica las migraciones. El proveedor predeterminado es `https://api.v2.sondehub.org/tawhiri`; el predictor permanece deshabilitado hasta configurarlo explícitamente. Los parámetros y mensajes están en el [contrato del panel](../protocols/frontend-api-v1.md#predicción).

- **Lanzamiento planeado (`planned`):** permite definir un origen independiente mediante coordenadas y altitud MSL, con una fecha/hora de lanzamiento explícita. Si la API omite el origen manual, conserva el origen persistido. No cambia la misión ni afirma que haya despegado. La [planificación independiente](prediction-planning.md) describe el popup y su verificación.
- **Continuación desde GPS (`ascending`):** usa la muestra GPS válida más reciente, dentro del umbral de antigüedad de la misión. Como PICARO FULL no aporta hora GPS, `receivedAt` es una aproximación temporal; retrasos de radio/ingestión pueden afectar el cálculo. Elegir este modo no demuestra ascenso físico.
- **Objetivo relativo:** el máximo de 15000 m se mide respecto al origen elegido para planificación o al lanzamiento persistente en continuación GPS. Tawhiri recibe la altitud absoluta del cambio de fase. La tasa nominal de descenso corresponde al nivel del mar.
- **Altitud:** solo se usan referencias MSL comprobadas. El origen manual requiere una declaración explícita en su solicitud; el origen persistente usa la configuración de la misión y continuación exige también la del GPS. Declarar una referencia no convierte altitud elipsoidal.

El contexto del resultado identifica origen, fecha efectiva, muestra usada cuando corresponde, modo y dataset meteorológico. La interfaz muestra el resultado como estimación. El punto `release` es el cambio de ascenso a descenso del perfil, sin acreditar liberación física; el punto final es un aterrizaje calculado, sin confirmarlo como observado. Los disparadores GPS y watchdog permanecen en firmware.

Una solicitud puede durar hasta 10 s y no tiene reintentos automáticos. La separación mínima es de 60 s por misión, incluida una consulta que falle. Su fecha permitida y la última respuesta válida sobreviven al reinicio. Una respuesta inválida/incompleta, fallo del proveedor o timeout mantiene el resultado anterior; no publica una predicción fallida como válida. La persistencia precede al mensaje WebSocket.

La validación del resultado admite una diferencia de hasta ±10 m entre la altitud de transición y el objetivo, y hasta ±1 s entre el primer punto y la hora efectiva del origen, por la resolución numérica del solver. Esas tolerancias verifican coherencia del perfil calculado; no representan error de vuelo, precisión física ni incertidumbre meteorológica.

## Comparación reproducible en SondeHub

La comparación utiliza [SondeHub Predictor](https://predict.sondehub.org/), el [contrato Tawhiri](https://tawhiri.readthedocs.io/en/latest/api.html) y su [repositorio oficial](https://github.com/cuspaceflight/tawhiri). Contrasta exactamente la misma consulta y dataset: dos resultados calculados con meteorología distinta no demuestran un error de adaptación.

1. Registra el caso con coordenadas, altitud MSL, hora UTC efectiva, altitud absoluta objetivo, tasas de ascenso y descenso al nivel del mar, perfil y dataset. Usa datos sintéticos claramente identificados para una prueba sin vuelo.
2. Ejecuta el POST de SATLINK y guarda la entrada, respuesta normalizada y respuesta original del proveedor, sin incluir el token CSRF. Para continuación usa el origen/hora del `context`, no el punto inicial de lanzamiento ni la hora posterior en que se abrió el navegador.
3. Introduce las mismas entradas en SondeHub, incluidos hora UTC y perfil. Registra la URL, valores visibles, captura y resultado; si permite fijar dataset, utiliza el mismo. Si no permite fijarlo, verifica en su respuesta de red qué dataset utilizó y declara la limitación cuando difiera.
4. Compara latitud/longitud del aterrizaje, hora final, altitud final, cambio de fase y trayectoria por segmento. Distingue discrepancia de redondeo visible de discrepancia del resultado original. Conserva las diferencias numéricas calculadas y la resolución con que cada interfaz muestra sus datos.
5. Repite un caso después de fallo del proveedor y después de reiniciar para verificar conservación/cadencia. Una captura de SondeHub no reemplaza las pruebas de esos comportamientos locales.

La coincidencia con SondeHub comprueba que SATLINK adapta y presenta de forma coherente el motor para las mismas entradas. Si ambos usan el mismo motor y meteorología, esa coincidencia no es una validación independiente de precisión física. Para evaluar precisión de vuelo hacen falta una trayectoria GPS observada y un aterrizaje confirmado, con sus fechas, datum y error frente a la predicción que existía antes del aterrizaje. No se publican porcentajes de precisión ni radios de incertidumbre sin esa evidencia.

## Entrega inicial: alcance y verificación del 4 de octubre de 2026

Esta entrega agrega el servicio de predicción, persistencia, configuración por misión, los dos perfiles de consulta, contrato/UI y metodología SondeHub. No implementa telecomandos, cambio automático de fase ni actuación en hardware. Las pruebas con entradas sintéticas se identifican como tales.

Los resultados siguientes corresponden a la integración inicial. La verificación de la ampliación del popup y origen independiente se registra por separado en [Planificación independiente](prediction-planning.md).

| Verificación | Estado y evidencia |
| --- | --- |
| Dominio, entradas, normalización y fallos del proveedor | Ejecución completa final del backend: `118 passed, 1 warning` en 29,92 s, comunicada por la raíz. Los proveedores de las pruebas automáticas son sintéticos. |
| PostgreSQL, cadencia, conservación y publicación posterior al commit | Incluidas en la suite completa con PostgreSQL 17/SSPI y base exclusiva `satlink_prediction_20261003_test`. El proveedor de integración es sintético; no acredita meteorología real ni vuelo. |
| Frontend: pruebas, lint y compilación | Ejecución final: `36 passed`; `npm run lint` y `npm run build` satisfactorios, ejecutados por la raíz. |
| Validación del contrato en frontend | `parsePrediction` consumió correctamente ambos JSON reales de evidencia: 75 puntos planeados y 65 de continuación. |
| Consulta real a Tawhiri | Casos planeado y continuación desde GPS consultados en proveedor real y normalizados en SATLINK con entradas sintéticas. [Planeado](../evidence/prediction-tawhiri/planned.json) y [continuación](../evidence/prediction-tawhiri/ascending.json). |
| Comparación en SondeHub con entradas/dataset equivalentes | Ambos casos visibles en SondeHub y comparados con CSV del mismo proveedor/dataset. Diferencias dentro del redondeo del CSV; detalle abajo. |
| Interfaz SATLINK con predicción real | Estación FastAPI local: [formulario planeado con hora local/UTC](../evidence/prediction-tawhiri/satlink-planned.png), POST planeado exitoso y edición nativa de fecha; solicitud de continuación y respuesta real conservada, contexto y cadencia visibles; [captura de recuperación](../evidence/prediction-tawhiri/satlink-ascending.png). La fase permanece sin confirmar. |
| Precisión de vuelo, enlace RF y actuación física | Pendiente de evidencia de hardware/vuelo. |

Caso planeado observado en [SondeHub](https://predict.sondehub.org/): origen sintético 21°, −102°, altitud 1870 m MSL; lanzamiento `2026-10-04T08:00:00Z`; objetivo absoluto 16870 m; ascenso 5 m/s y descenso al nivel del mar 6,5 m/s; perfil estándar y modelo meteorológico mostrado `20261004-00`. El resultado visible muestra aterrizaje en 20,8422°, −102,1461°, a las 09:13 UTC, y transición en 20,8853°, −102,1002°, altitud 16868 m a las 08:49 UTC. Son valores observados con redondeo de interfaz, no mediciones de vuelo. [Captura del caso planeado](../evidence/prediction-tawhiri/sondehub-planned.png).

La [respuesta guardada](../evidence/prediction-tawhiri/planned.json) identifica dataset `2026-10-04T00:00:00Z`. Sus 75 puntos normalizados se compararon con [el CSV](../evidence/prediction-tawhiri/planned.csv), que contiene 76 filas por repetir la unión de ascenso y descenso. Al tratar esa repetición, las diferencias máximas son 0,0000048852° de latitud, 0,0000049733° de longitud, 0,049318 m de altitud y 0 s de tiempo. Cumplen las tolerancias declaradas de 0,0000051°, 0,051 m y 0,000001 s, acordes con el redondeo del CSV. La respuesta conserva el aterrizaje en `2026-10-04T09:13:28.125000Z`, altitud 1889,2519 m; no fuerza la altitud final a la del origen de lanzamiento.

El caso de continuación utiliza una muestra GPS **sintética**, identificada en [su contexto guardado](../evidence/prediction-tawhiri/ascending.json): 21,02°, −102,01°, 5000 m MSL y recepción `2026-10-04T06:02:00Z`. Mantiene el objetivo absoluto 16870 m respecto al origen de misión de 1870 m, tasas 5/6,5 m/s y el mismo dataset. Su ejecución en SondeHub conserva [las entradas](../evidence/prediction-tawhiri/sondehub-ascending.png) y [el mapa del resultado](../evidence/prediction-tawhiri/sondehub-ascending-result.png). Los 65 puntos normalizados corresponden a [66 filas CSV](../evidence/prediction-tawhiri/ascending.csv) con unión duplicada; diferencias máximas de 0,0000049945° de latitud, 0,0000047987° de longitud, 0,046696 m de altitud y 0 s, dentro de las mismas tolerancias. El aterrizaje calculado es 20,8760664°, −102,1217752°, a `2026-10-04T07:04:50.625000Z`, altitud 1977,1698 m. Este caso verifica adaptación de un origen GPS supuesto; no acredita recepción de hardware ni precisión de un vuelo.

El recorrido real en la interfaz de SATLINK mostró el modo de continuación, solicitud en curso y resultado guardado con fecha `2026-10-04T06:03:18Z` (00:03:18 en el navegador de prueba), meteorología de las 00:00 UTC y cadencia posterior. El objetivo siguió siendo 15000 m relativos y la misión mantuvo `phase=unknown`. La captura de recuperación muestra separadamente posición de la cápsula, ruta predicha y marcadores estimados.

La prueba del formulario planeado utilizó origen temporal `2026-10-04T07:02:00Z` y produjo un POST exitoso observado a las `2026-10-04T06:04:40Z`; corresponde a otra solicitud, separada del caso API/SondeHub de las 08:00 UTC. La edición nativa con `ArrowUp`/`ArrowDown` modificó la fecha UTC visible y permitió volver al valor anterior. Estas comprobaciones cubren interacción y presentación, sin acreditar exactitud física.

Las versiones del proyecto permanecen fijadas en sus manifiestos y archivos de bloqueo. La raíz confirmó la consulta Context7 antes de implementar APIs y comunicó los resultados anteriores; el rol Documentación contrastó el contrato con configuración, DTOs, caso de uso, rutas, persistencia y pruebas. Los estados pendientes no acreditan una integración verificada.
