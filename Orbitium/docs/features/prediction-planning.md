# Planificación independiente desde Recuperación

Estado de la tarea: implementación en código, pruebas automáticas y recorrido visual en demostración verificados. La integración PostgreSQL y la consulta real del origen manual permanecen pendientes.

## Alcance y comportamiento

La planificación abre un popup desde Recuperación para elegir fecha/hora, coordenadas y altitud sobre el nivel del mar. Permite seleccionar un punto con clic en el mapa, arrastrar su marcador o introducir las coordenadas numéricas; la altitud MSL se introduce y confirma explícitamente, sin inferirla de los mosaicos del mapa. En la estación real, Generar utiliza el perfil `planned` de Tawhiri y muestra el resultado en Recuperación.

Los controles de altitud relativa, ascenso y descenso al nivel del mar permanecen en Recuperación. El recálculo conserva el origen y hora del escenario elegido y utiliza las velocidades actuales; durante continuación GPS mantiene el origen de misión y la muestra reciente conforme a su perfil. La fecha local se convierte a UTC con zona para el POST. Elegir un escenario no modifica la fase de misión, el punto persistente de lanzamiento ni las muestras GPS.

Abre **Recuperación → Planificación independiente**, introduce una fecha futura, selecciona el punto y su altitud MSL, confirma la referencia y pulsa **Generar predicción**. El popup usa los parámetros visibles en Recuperación, muestra errores de validación/proveedor y solo cierra al generar correctamente o al cancelarlo. La planificación manual no exige un paquete GPS; sí requiere conexión con la estación local y predictor habilitado. Después puedes cambiar las velocidades en Recuperación y usar **Recalcular predicción**, respetando la cadencia.

La planificación independiente admite un sitio diferente al de la misión. Declarar MSL corresponde a la referencia introducida por el operador; no realiza conversión de datum ni verifica por sí sola el terreno. Cerrar o cancelar el popup sin generar no solicita una predicción. La demo conserva identificación y cálculo simulados; un resultado real mantiene `source=tawhiri`.

## Contrato y persistencia

La ruta existente `POST /api/v1/missions/{id}/predictions` acepta en `planned` los campos opcionales `launch` (`Position`) y `launchAltitudeReference="MSL"`, además de fecha futura y los tres parámetros previos. Se envían juntos. Si se omiten ambos, conserva el origen persistente. En `ascending` están prohibidos. Los rangos y ejemplos están en [el contrato HTTP/WebSocket](../protocols/frontend-api-v1.md#predicción).

El objetivo absoluto de planificación es la altitud del origen elegido más el objetivo relativo: con origen manual de 2000 m y objetivo relativo de 15000 m, el cambio de fase solicitado es 17000 m MSL. En continuación GPS, el objetivo sigue referido al lanzamiento persistente de misión. El contexto y los parámetros guardados permiten reconstruir el origen manual; no se cambia la configuración persistente de la misión para conseguirlo.

La habilitación global entrega permisos locales y CSRF aunque el datum del origen de misión sea desconocido; cada consulta valida la referencia del origen que realmente utiliza. Persistencia previa al WebSocket, última respuesta válida, separación de 60 s, timeout total de 10 s y manejo de errores mantienen el contrato existente. No se añaden telecomandos ni predicciones en reproducción histórica.

## Verificación y pendientes

| Comprobación de esta ampliación | Estado |
| --- | --- |
| Suite del backend | `90 passed, 43 skipped, 1 warning` en 20,91 s, comunicados por la raíz. No estaba configurada la base exclusiva de pruebas; las integraciones PostgreSQL se omitieron. |
| Origen manual MSL y objetivo absoluto | Cubiertos por pruebas unitarias nuevas con almacenamiento y proveedor sintéticos, incluidas entre las 90 satisfactorias. |
| Misión sin modificaciones y contexto persistido en PostgreSQL | Prueba añadida; ejecución pendiente por falta de `SATLINK_TEST_DATABASE_URL`. Las pruebas omitidas no acreditan persistencia. |
| Compatibilidad con origen persistente y rechazo de origen manual en `ascending` | Cubiertos por las unitarias nuevas; integración PostgreSQL pendiente. |
| Frontend: pruebas | Ejecución final `40 passed, 0 failed` en 514,9 ms. Incluye cuatro casos nuevos de origen manual, validación, transporte/contexto y demo sin modificar misión/telemetría. |
| Frontend: build y lint | Ejecuciones finales de build y `npm run lint` satisfactorias después del último cambio, comunicadas por la raíz. Lint utiliza `oxlint src tests`. |
| Popup: fecha local/UTC, mapa/coordenadas, altitud MSL, generar y cancelar | Verificado en demo después de reiniciar Vite fuera del aislamiento que bloqueaba sockets. Generar cerró el popup; clic/arrastre actualizaron coordenadas sin cambiar altitud y cancelar mantuvo el resultado. |
| Velocidades y recálculo en Recuperación conservando el escenario | Verificado en demo: ascenso de 5 a 5,1 m/s cambió el aterrizaje estimado, conservando origen, fecha y lanzamiento oficial. |
| Consulta real del origen independiente | Pendiente de evidencia específica de esta ampliación. La comparación inicial del motor con SondeHub queda identificada en su entrega anterior. |
| Precisión física, enlace RF y actuación de firmware | Pendiente de hardware/vuelo; ninguna prueba local los acredita. |

El recorrido visual usó origen manual 21,5°, −101,5° y altitud 2300 m MSL. La fecha seleccionada fue el 7 de octubre de 2026 a las 21:01 en `America/Mexico_City`, convertida a `2026-10-08T03:01:00Z`. Generar produjo un objetivo absoluto de 17300 m. El [popup con mapa](../evidence/prediction-planning/planning-map-demo.png) y el [contexto del resultado simulado](../evidence/prediction-planning/planning-result-demo.png) conservan esa evidencia.

Al recalcular con ascenso de 5 a 5,1 m/s, el aterrizaje simulado cambió de 21,60062°, −101,23957° a 21,59763°, −101,24279°. El origen y la fecha elegidos permanecieron iguales; el lanzamiento oficial siguió en 21,88535°, −102,29167°. La selección mediante clic y arrastre mantuvo la altitud de 2300 m; cancelar conservó el resultado anterior. El mapa del popup cargó cartografía. Recuperación mostró fallos intermitentes de mosaicos, conservando coordenadas y ruta. Estos resultados verifican la interacción con datos simulados, sin acreditar Tawhiri real ni vuelo.
