# Entrega del frontend SATLINK

Fecha: 2 de octubre de 2026. Base del repositorio: `1bff7bc58cd196c161195fcdb8224e63af2809be`. Rama local de trabajo: `feat/satlink-mission-dashboard`.

## Contenido

- Dashboard adaptable con indicadores de misión, seis sensores, mapa GPS, altitud relativa y cuatro gráficas.
- Recuperación a pantalla completa con trayectoria medida, escenario/predicción, parámetros y coordenadas copiables.
- Controles de baliza, PING, estado, telemetría y liberación con confirmación; bitácora de estados y evidencias.
- Demostración explícita, pausa de señal y detección de datos antiguos.
- Adaptadores Fetch/WebSocket con validación, permisos del cliente, CSRF, idempotencia, reconexión y conservación de lecturas.
- Contrato propuesto de FastAPI, ejemplo JSON, documentación de arquitectura y 17 pruebas automatizadas.

Se implementaron los diseños móviles de Figma `7:1097`, `7:797` y `7:1936`. La composición de escritorio adapta esas mismas secciones. La tipografía JetBrains Mono y su licencia se incluyen localmente. No se añadieron dependencias de producción.

## Probar la entrega

Extrae `SATLINK-Frontend.zip` y abre una terminal dentro de `SATLINK-PanelControl`:

```sh
cd frontend
npm ci
npm run dev
```

Usa Node 22.18 o posterior dentro de la rama 22 y npm 10. El panel abre en demostración. No necesitas instalar Python, PostgreSQL ni FastAPI para revisar esa interfaz. Consulta el [recorrido y configuración](../frontend/README.md).

La carpeta `capturas/` del ZIP contiene capturas de navegador de escritorio y móvil. En esas capturas se bloqueó intencionalmente la cartografía externa para verificar la conservación de rutas y el aviso de indisponibilidad. El código utiliza el proveedor configurado cuando está disponible.

## Validación realizada

| Comprobación                                  | Resultado                                                                                                     |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Node 22.18.0 / npm 10.9.3                     | Ejecución, pruebas y compilación correctas                                                                    |
| Pruebas de dominio, controlador y transportes | 17 casos correctos                                                                                            |
| TypeScript estricto y build de Vite           | Correctos                                                                                                     |
| Oxlint y `git diff --check`                   | Correctos                                                                                                     |
| Chromium: 320, 393, 768, 1024 y 1440 px       | Sin desbordamiento horizontal ni recorte del indicador de altitud                                             |
| Recuperación                                  | Rangos, recálculo, desplazamiento, cierre con Escape y restitución del foco verificados                       |
| Comandos de demostración                      | Transiciones, confirmación de liberación, evento independiente y bloqueo de duplicados verificados            |
| Señal antigua y reanudación                   | Datos retenidos, comandos bloqueados y posterior recuperación verificados                                     |
| Backend no disponible                         | Error explícito, sin conversión automática a demostración                                                     |
| Build de producción con API/WS de prueba      | Snapshot, muestras, permisos, CSRF, idempotencia y fallo del predictor verificados con respuestas controladas |

Se corrigieron durante la revisión una importación CommonJS incompatible de ECharts, el tamaño inicial del mapa dentro del diálogo, el orden del CSS de Leaflet, el recorte móvil de altitud y la limpieza de suscripciones después de reintentar.

La advertencia de Vite sobre el módulo de ECharts de aproximadamente 540 kB minificados / 183 kB gzip sigue visible. La librería se carga bajo demanda; la advertencia no bloquea el build.

Estas comprobaciones se realizaron en Chromium. No constituyen pruebas de hardware, vuelo, radio, Tawhiri, sesión real de FastAPI ni validación de otros navegadores.

## Subir los cambios al repositorio

La entrega inicial se distribuyó como ZIP porque la cuenta conectada no tenía escritura. El 2 de octubre de 2026 se confirmó `push: true` para `SantiiagoDS3`, pero el conector de ChatGPT rechazó la creación del primer blob con `403: Resource not accessible by integration`. No se publicaron commits, ramas ni pull requests. La cuenta colaboradora puede subir los cambios mediante Git desde su computadora siguiendo estos pasos.

### Aplicar el parche en una copia nueva

El ZIP incluye `satlink-frontend.patch`, que contiene los cambios de código, documentación y recursos binarios frente al commit base. Deja ese archivo en una carpeta y ejecuta allí:

```sh
git clone https://github.com/jessusgarciar/SATLINK-PanelControl.git
cd SATLINK-PanelControl
git switch -c feat/satlink-mission-dashboard
git apply --check ../satlink-frontend.patch
git apply ../satlink-frontend.patch
cd frontend
npm ci
npm test
npm run lint
npm run build
cd ..
git status --short
git diff --check
git add README.md frontend docs/architecture/frontend.md docs/protocols/frontend-api-v1.md docs/protocols/dashboard.example.json docs/frontend-delivery.md
git commit -m "feat: implementar panel de misión SATLINK"
git push -u origin feat/satlink-mission-dashboard
```

En GitHub abre **Compare & pull request**, selecciona `main` como destino y revisa los cambios con el equipo. No es necesario reemplazar `main` directamente.

Si `git apply --check` falla, el repositorio cambió desde la base: detente y resuelve los archivos señalados antes de aplicar el parche. No uses `reset --hard` ni sobrescribas cambios del equipo. También puedes comparar los archivos con la carpeta completa incluida en el ZIP.

### Si tu cuenta no tiene escritura

Crea un fork desde GitHub. Aplica el mismo parche a un clon de tu fork y publica allí la rama; después abre un pull request hacia `jessusgarciar/SATLINK-PanelControl:main`. Otra opción es solicitar al propietario que te agregue como colaborador. Conceder lectura al conector no concede escritura al repositorio.

## Pendiente para la estación real

Implementar y acordar el [contrato HTTP/WebSocket](protocols/frontend-api-v1.md), sesión/roles, validación de comandos e idempotencia en backend, integración ChirpStack/MQTT, persistencia y servicio de predicción. El frontend ya está preparado para ese contrato, pero el repositorio base no contenía esos servicios ejecutables.

El cálculo de demostración usa vientos constantes y no sirve para planear un vuelo real. La predicción operativa se solicita exclusivamente al backend. El watchdog y los mecanismos físicos de liberación permanecen en firmware.
