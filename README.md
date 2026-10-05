# SATLINK Panel de Control

SATLINK es una plataforma para centralizar, supervisar y visualizar datos de telemetría de sistemas conectados. Su propósito general es ofrecer una base organizada para consultar información, observar su evolución y apoyar la operación desde una interfaz web.

El proyecto utiliza React y TypeScript con Vite en el frontend, y Python con FastAPI y PostgreSQL en el backend. Se organiza con arquitectura limpia para mantener las reglas del dominio y los casos de uso independientes de las herramientas externas.

## Estado actual

El frontend implementa el panel de telemetría, trayectoria GPS, cuatro gráficas, recuperación/predicción y bitácora de comandos, siguiendo el Figma del equipo. Incluye una demostración interactiva claramente identificada y adaptadores HTTP/WebSocket para la estación real.

El backend implementa telemetría e historial: validación del payload de 19 bytes, persistencia PostgreSQL, snapshot HTTP, historial paginado y WebSocket posterior al commit. La integración de predicción Tawhiri añade consultas de lanzamiento planeado o continuación desde GPS, persistencia de la última respuesta válida y comprobación comparativa en SondeHub. Su configuración está deshabilitada por defecto y requiere comprobar las referencias de altitud de cada misión. Esta etapa funciona en localhost, sin login y sin telecomandos. La demostración del frontend sigue separada de la estación real. Consulta la [guía de ejecución del backend](docs/setup/backend.md), el [protocolo PICARO FULL](docs/protocols/picaro-full-v1.md) y la [guía de predicción y su verificación](docs/features/prediction-tawhiri.md).

Cuenta con diagnóstico MQTT independiente del WebSocket, metadatos de dispositivo y radio, ventanas temporales, CSV completo, reproducción histórica a 1×/5×/10× y una bitácora técnica de sesión. El historial conserva sus fechas originales y queda separado del modo en vivo. 

- [Guía del frontend](frontend/README.md): ejecución, configuración y recorrido de la interfaz.
- [Arquitectura y decisiones de Figma](docs/architecture/frontend.md).
- [Entrega, validación y subida a GitHub](docs/frontend-delivery.md).

## Requisitos

- Node.js 22.12 o superior dentro de la rama 22 y npm 10. Entorno verificado: Node.js 22.18.0 y npm 10.9.3.
- Python 3.13. Entorno verificado: Python 3.13.7.
- PostgreSQL 17. Entorno verificado: PostgreSQL 17.11, instalado de forma portátil en `.local/postgresql`.

Los siguientes comandos se ejecutan en PowerShell desde la raíz del proyecto, salvo donde se indica otra carpeta. Las instalaciones de Node.js y Python ya estaban disponibles. En otra computadora pueden obtenerse desde [Node.js](https://nodejs.org/en/download) y [Python](https://www.python.org/downloads/windows/).

## Instalar y ejecutar el frontend

```powershell
cd frontend
npm ci
npm run dev
```

Vite indicará la dirección local del servidor. El panel inicia en modo **DEMOSTRACIÓN**, con datos de ejemplo y comandos simulados. Para detenerla, usa `Ctrl+C`.

```powershell
npm test
npm run build
npm run lint
npm ls --depth=0
```

`test` ejecuta las pruebas de dominio, controlador y transportes; `build` verifica TypeScript y genera archivos en `dist`; `lint` revisa el código; `npm ls` muestra las versiones instaladas. `package.json` fija versiones directas y `package-lock.json` conserva la resolución completa. Leaflet tiene sus tipos en `@types/leaflet`; React Leaflet, ECharts y echarts-for-react incluyen sus propios tipos. Fetch y WebSocket son APIs nativas y no agregan paquetes.

## Instalar y activar el backend

Desde la raíz, solo si el entorno virtual aún no existe:

```powershell
python -m venv backend/.venv
```

Activación e instalación reproducible:

```powershell
. ./backend/.venv/Scripts/Activate.ps1
python -m pip install -r backend/requirements.txt -c backend/requirements.lock.txt
python -m pip check
```

Si PowerShell bloquea la activación, se puede utilizar el intérprete directamente sin cambiar la política del sistema:

```powershell
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt -c backend/requirements.lock.txt
./backend/.venv/Scripts/python.exe -m pip check
```

`requirements.txt` declara dependencias directas y sus extras; `requirements.lock.txt` fija también las transitivas del entorno Windows/Python 3.13 verificado. `uvicorn[standard]` incluye soporte WebSocket, `SQLAlchemy[asyncio]` instala su soporte asíncrono y `psycopg[binary]` aporta el controlador y libpq sin compilación local. Para salir del entorno activado, ejecuta `deactivate`.

Desde `backend`, configura `.env`, ejecuta `python -m alembic upgrade head`, completa una copia local de `mission.example.json` y registra la misión con `python -m app.bootstrap.cli init-mission --file mission.local.json`. Inicia con `python -m app.bootstrap.cli serve`. La CLI configura `SelectorEventLoop` en Windows y un único proceso en `127.0.0.1`. Los valores obligatorios del ejemplo deben sustituirse por datos reales; MQTT permanece deshabilitado hasta configurarlo explícitamente.

## PostgreSQL local

La instalación preparada escucha únicamente en `127.0.0.1:5433` y usa UTC. La base `satlink_dev` se reserva a desarrollo; las pruebas usan exclusivamente una base cuyo nombre termina en `_test`. La autenticación SSPI vincula la cuenta Windows que preparó el entorno con el rol local `satlink_dev`, sin guardar contraseñas. Los binarios, datos y configuración particulares de esta computadora quedan en `.local`, excluida del control de versiones.

Para iniciar PostgreSQL desde la raíz:

```powershell
./.local/postgresql/pgsql/bin/pg_ctl.exe -D .local/postgresql/data -l .local/postgresql/server.log -w start
./.local/postgresql/pgsql/bin/pg_isready.exe -h 127.0.0.1 -p 5433
```

Para abrir la consola con la cuenta Windows autorizada:

```powershell
./.local/postgresql/pgsql/bin/psql.exe -h 127.0.0.1 -p 5433 -U satlink_dev -d satlink_dev -w
```

Para salir de la consola, usa `\q`. Para detener el servidor:

```powershell
./.local/postgresql/pgsql/bin/pg_ctl.exe -D .local/postgresql/data -m fast -w stop
```

El servidor se inició y verificó durante la preparación y se dejó detenido al terminar. No se registró un servicio de Windows ni se modificó el PATH global. La instalación en otra computadora y las comprobaciones para conservar bases existentes se explican en [Preparación de PostgreSQL](docs/setup/postgresql.md).

## Estructura

```text
SATLINK-PanelControl/
├── frontend/
│   ├── public/
│   └── src/
│       ├── app/
│       ├── domain/
│       ├── application/
│       ├── infrastructure/
│       │   ├── http/
│       │   └── websocket/
│       └── presentation/
│           ├── components/
│           ├── pages/
│           ├── hooks/
│           ├── assets/
│           └── styles/
├── backend/
│   ├── app/
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   └── repositories/
│   │   ├── application/
│   │   │   ├── use_cases/
│   │   │   └── ports/
│   │   ├── infrastructure/
│   │   │   ├── database/
│   │   │   ├── mqtt/
│   │   │   └── prediction/
│   │   ├── presentation/
│   │   │   ├── api/
│   │   │   ├── schemas/
│   │   │   └── websocket/
│   │   └── bootstrap/
│   ├── migrations/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── end_to_end/
├── docs/
│   ├── architecture/
│   │   └── decisions/
│   ├── protocols/
│   ├── setup/
│   └── scrum/
│       ├── product_backlog/
│       ├── sprints/
│       ├── reviews/
│       ├── retrospectives/
│       └── definition_of_done/
├── scripts/
└── README.md
```

El árbol muestra las carpetas de trabajo; además existen manifiestos, archivos de bloqueo, configuraciones de Vite y TypeScript, el reporte fuente y archivos `.gitkeep` para conservar directorios vacíos. `.local`, `.venv`, `node_modules` y `dist` son archivos locales excluidos.

## Organización del trabajo

`domain` aloja conceptos y contratos independientes de herramientas. `application` coordina casos de uso mediante puertos. `infrastructure` aloja adaptadores para HTTP, WebSocket, PostgreSQL, MQTT y servicios externos. `presentation` aloja las interfaces de usuario y API. `app` en el frontend y `bootstrap` en el backend componen las capas.

Las reglas de dependencia se explican en [Arquitectura](docs/architecture/README.md). Las carpetas [Scrum](docs/scrum/README.md) guardarán backlog, documentación de sprints, reviews, retrospectivas y criterios de terminado; por ahora no contienen historias, estimaciones ni planes de sprint. `docs/protocols` contiene el contrato propuesto del panel y un ejemplo de snapshot; `scripts` se reserva para herramientas del equipo.

## Verificación y pendientes

La preparación del repositorio, exclusiones y pasos para revisar un commit están en [Preparación para Git](docs/setup/git.md). Las reglas se mantienen desde la raíz en `.gitignore`, `.gitattributes` y `.editorconfig`.

Las versiones instaladas se registran en [Entorno verificado](docs/setup/environment.md). La entrega actual se documenta en [Telemetría](docs/features/telemetry.md), [Historial](docs/features/history.md) y [Verificación PICARO](docs/features/picaro-verification.md). Quedan pendientes autenticación para acceso compartido, telecomandos, predicción Tawhiri y validación con hardware. Las pruebas sintéticas no acreditan recepción de radio ni vuelo real. No se implementaron cambios de firmware.
