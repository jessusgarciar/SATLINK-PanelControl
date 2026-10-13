# system: misión con nombre pendiente

Esta webapp es una copia de ORBITIUM con frontend claro. Usa frontend 5174, backend 8001 y base system_dev. El backend conserva la misma lógica, API, migraciones y protocolo PICARO FULL de 19 bytes; su compatibilidad con el nuevo dispositivo deberá confirmarse.

DevEUI y Application ID permanecen como REEMPLAZAR_DEVEUI y REEMPLAZAR_APPLICATION_ID. Los datos de lanzamiento, tasas nominales, watchdog y antigüedad máxima quedan sin definir. No se copió el dispositivo real de ORBITIUM. MQTT está deshabilitado y no se configuraron broker ni credenciales.

Desde Pendiente: `./scripts/start-dev.ps1 -NoBrowser` inicia la demostración. Para habilitar Live, completa backend/mission.local.json con datos confirmados y configura backend/.env. La validación actual rechaza los marcadores y valores pendientes.

Las demos y pruebas mantienen sus valores sintéticos, identificados como ejemplos. La documentación y evidencia técnica copiadas describen el desarrollo anterior; no prueban vuelos, datos físicos ni conexión del nuevo dispositivo.
