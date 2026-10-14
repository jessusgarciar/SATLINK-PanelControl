# SATLINK-PanelControl

Repositorio de dos apps independientes: **ORBITIUM** y una segunda misión con nombre pendiente.

`Orbitium/` y `Pendiente/` tienen cada una su propio frontend React/TypeScript, backend FastAPI, migraciones, pruebas, variables de entorno, documentación y scripts. El backend y las funcionalidades son iguales; cambian la identidad, el dispositivo y la paleta del frontend. ORBITIUM conserva su tema oscuro; Pendiente utiliza la paleta clara solicitada.

## Aplicaciones

| Carpeta | Interfaz | Frontend local | Backend local | Base de desarrollo |
| --- | --- | --- | --- | --- |
| [Orbitium](Orbitium/README.md) | ORBITIUM | http://127.0.0.1:5173 | http://127.0.0.1:8000 | satlink_dev (existente) |
| [Pendiente](Pendiente/README.md) | Pendiente | http://127.0.0.1:5174 | http://127.0.0.1:8001 | system_dev |

Las apps se pueden ejecutar simultáneamente en terminales diferentes. Cada una consume únicamente su backend y su base; sus historiales y predicciones no se mezclan. Se mantiene el contrato SATLINK y los nombres de variables `SATLINK_*` en ambos backends.

## Arranque desde la raíz

Con dependencias instaladas y los entornos locales preparados:

```powershell
.\scripts\start-dev.ps1 -App Orbitium -NoBrowser
.\scripts\start-dev.ps1 -App Pendiente -NoBrowser
```

Sin `-App`, inicia Orbitium. Sin `-NoBrowser`, abre la webapp elegida. La demostración conserva telemetría simulada y consultas manuales a Tawhiri con datos de ejemplo. Para ORBITIUM real: `.\scripts\start-dev.ps1 -App Orbitium -Mode Live`.

También puedes entrar a cada carpeta y ejecutar su propio `scripts/start-dev.ps1`. Los comandos de instalación y pruebas de cada README parten de la carpeta de esa aplicación.

El PostgreSQL portátil permanece en `.local/postgresql` como herramienta local del repositorio; las bases son distintas. El lanzador crea la base seleccionada si falta y aplica sus migraciones. Los logs de frontend/backend quedan en `<app>/.local/dev-logs`. Ctrl+C detiene el frontend y backend de esa terminal; PostgreSQL permanece activo para la otra aplicación. Para detenerlo cuando ambas estén cerradas:

```powershell
.\.local\postgresql\pgsql\bin\pg_ctl.exe -D .\.local\postgresql\data -m fast -w stop
```

## Configuración y dispositivo pendiente

Cada aplicación conserva `frontend/.env.example`, `backend/.env.example` y `backend/mission.example.json`. Sus copias privadas `.env`, `.env.local`, `mission.local.json` y `prediction-settings.local.json` se excluyen de Git.

ORBITIUM conserva su configuración local existente. En Pendiente, DevEUI, Application ID, broker, credenciales y parámetros físicos quedan pendientes. MQTT permanece deshabilitado y el modo Live exige completar y validar la configuración.
