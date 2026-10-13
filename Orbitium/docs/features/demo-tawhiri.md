# Demostración del frontend con Tawhiri real

La demostración existente conserva su animación, sensores, historial visual y comandos ficticios en el navegador. Solo las consultas manuales de predicción pasan al backend y al proveedor Tawhiri. No se agregó un simulador de vuelo al backend ni se insertan paquetes simulados como recepción ChirpStack.

## Ejecución

Desde la raíz, ejecuta `.\scripts\start-dev.ps1`. Requiere las dependencias existentes de frontend/backend, PostgreSQL portátil y `backend/.env` con una URL `postgresql+psycopg` para localhost:5433. Comprueba puertos 8000 y 5173, inicia la base cuando hace falta, aplica migraciones, espera ambos servidores y abre el navegador. `-NoBrowser` evita abrirlo.

El lanzador aplica únicamente al proceso `SATLINK_DEMO_PREDICTION_ENABLED=true`, `SATLINK_MQTT_ENABLED=false`, `VITE_DATA_SOURCE=demo` y `VITE_DEMO_PREDICTION=tawhiri`; restaura sus variables al terminar y no sustituye `.env`, la misión física ni sus referencias. Los registros están en `.local/dev-logs`. `Ctrl+C` cierra sus servidores y detiene PostgreSQL únicamente si lo inició. Si otro servidor ocupa un puerto, pide detenerlo en lugar de reemplazarlo.

Para iniciar componentes por separado, habilita `SATLINK_DEMO_PREDICTION_ENABLED=true` en el backend y `VITE_DEMO_PREDICTION=tawhiri` en el frontend. Ambas opciones vienen deshabilitadas en los ejemplos. El permiso `SATLINK_PREDICTION_ENABLED` de la estación física permanece independiente.

### Logs en la misma terminal

El lanzador muestra los mensajes de los componentes durante el arranque y mientras permanece abierto. `[BD]` identifica PostgreSQL; `[BACKEND]` identifica solicitudes HTTP; `[BACKEND · STDERR]` muestra el registro del servidor y del proveedor; `[FRONTEND]` y `[FRONTEND · STDERR]` muestran Vite y sus avisos. `STDERR` indica el canal de salida: puede contener mensajes informativos, no solo errores. La preparación de base se anuncia con `[MIGRACIONES]`.

Los archivos se conservan: frontend/backend en `.local/dev-logs`, PostgreSQL en `.local/postgresql/server.log`. Se muestran únicamente las nuevas líneas de PostgreSQL desde esta ejecución y toda la salida de los servidores que inicia el lanzador. La lectura continúa durante las comprobaciones de disponibilidad y vacía las últimas líneas al cerrar. Python se ejecuta sin buffer para que sus mensajes aparezcan oportunamente.

Verificación del cambio: arranque ejecutado con logs visibles de los tres componentes; una consulta de planificación al proveedor produjo un timeout HTTP 504 visible en la terminal, comprobando también la presentación de fallos posteriores al arranque. La compilación, pruebas y consultas exitosas registradas abajo corresponden a la entrega funcional anterior; este ajuste modifica únicamente el lanzador y su documentación.

## Recorrido

1. Abre **DEMOSTRACIÓN → Recuperación**. La etiqueta muestra **Telemetría simulada · Tawhiri real**.
2. Para planificar, elige una fecha futura o abre **Planificación independiente** y declara la altitud MSL del origen supuesto.
3. Para continuar, selecciona **Ascenso · último GPS recibido**. Se usa la posición y fecha actuales de la demo, sin guardarlas como telemetría recibida.
4. Pulsa **Consultar Tawhiri**. El mapa distingue trayectoria simulada y predicción; el resultado muestra origen, hora de cálculo y meteorología.

No se hacen consultas automáticas. Los vientos constantes quedan reservados al cálculo visual local. Muestras antiguas, descenso, aterrizaje y objetivos inferiores a la posición actual impiden recalcular con el perfil estándar. Cada intento válido consume 60 segundos reales de cadencia, incluido un fallo del proveedor; el timeout total es de 10 segundos. Ante fallo se conserva el resultado previo. Si el backend está desconectado, la animación continúa y Recuperación explica que el predictor no está disponible; **Reintentar conexión**, en Recuperación, vuelve a consultar su configuración.

La misión persistida `satlink-demo`, con origen `frontend-demo`, solo conserva consultas de predicción y su contexto. El origen inicial supuesto coincide con la demo: 21.88535°, −102.29167°, 1870 m MSL. No certifica terreno ni datum de un GPS físico. El contexto de toda respuesta de este recorrido incluye `inputSource=simulated`, incluso para planificación independiente.

## Verificación

- Backend: ejecución final completa de **141 pruebas satisfactorias**, sin omisiones, con `satlink_prediction_20261003_test`. Incluye 97 unitarias y 44 integraciones; comprueba recuperación del resultado/cadencia y ausencia de paquetes falsos en tablas de telemetría. Advertencia existente de deprecación de httpx en TestClient.
- Frontend: 43 pruebas satisfactorias, lint y build satisfactorios. Pruebas nuevas comprueban envío del GPS sin vientos, cadencia y conservación de la demo ante desconexión.
- Arranque conjunto ejecutado dos veces: PostgreSQL, API y Vite disponibles; sesión de predicción habilitada mediante el proxy del frontend. `Ctrl+C` detuvo los servidores y el PostgreSQL iniciado por el lanzador. Los servicios de verificación quedaron detenidos.
- Recorrido visual verificado: selección de ascenso y botón **Consultar Tawhiri** produjeron un resultado real desde el GPS de la demo; el mapa conservó la trayectoria simulada separada. [Captura de Recuperación](../evidence/demo-tawhiri/recovery-real.jpg).
- Consultas reales al proveedor: planificación con 75 puntos y continuación desde GPS supuesto con 73 puntos; ambas respuestas se recuperaron desde PostgreSQL y repetir inmediatamente devolvió HTTP 429. Evidencia local: `.local/dev-logs/demo-planned.json` y `demo-ascending.json`. El modelo meteorológico de ambas respuestas fue `2026-10-08T00:00:00Z`.
- El verificador manual `scripts/check-demo-prediction.py --mode planned|ascending`, ejecutado con el Python del backend y el proyecto abierto, reproduce la consulta y guarda evidencia. Respeta la cadencia antes de cambiar de caso.
