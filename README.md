# SATLINK Panel de Control

SATLINK es una plataforma para centralizar, supervisar y visualizar datos de telemetría de sistemas conectados. Su propósito general es ofrecer una base organizada para consultar información, observar su evolución y apoyar la operación desde una interfaz web.

El proyecto utiliza React y TypeScript con Vite en el frontend, y Python con FastAPI y PostgreSQL en el backend. Se organiza con arquitectura limpia para mantener las reglas del dominio y los casos de uso independientes de las herramientas externas.

## Estado inicial

Esta etapa prepara las dependencias, el entorno local y las carpetas de trabajo. El frontend conserva únicamente la plantilla generada por Vite, reubicada en la estructura indicada. El backend todavía no tiene una aplicación ejecutable. Las carpetas de arquitectura, protocolos y Scrum están disponibles para documentar el desarrollo.

El stack se revisó contra `Reporte_StackSoftware-PC-Telemetria_SATLINK.pdf`, conservado en la raíz del proyecto. No se implementaron funcionalidades, endpoints, entidades, consultas, codecs ni integraciones. No se instalaron ChirpStack, broker MQTT ni predictor local.

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

Vite indicará la dirección local del servidor. La interfaz que aparece es la plantilla de Vite. Para detenerla, usa `Ctrl+C`.

```powershell
npm run build
npm run lint
npm ls --depth=0
```

`build` verifica TypeScript y genera archivos en `dist`; `lint` revisa el código; `npm ls` muestra las versiones instaladas. `package.json` fija versiones directas y `package-lock.json` conserva la resolución completa. Leaflet tiene sus tipos en `@types/leaflet`; React Leaflet, ECharts y echarts-for-react incluyen sus propios tipos. Fetch y WebSocket son APIs nativas y no agregan paquetes.

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

Todavía no hay módulo FastAPI que ejecutar ni configuración de Alembic; las carpetas correspondientes están preparadas. En Windows, aiomqtt requerirá un bucle de eventos que soporte `add_reader` cuando se implemente su integración. Esta etapa comprobó importaciones y disponibilidad de `SelectorEventLoop`, sin conectarse a MQTT.

## PostgreSQL local

La instalación preparada escucha únicamente en `127.0.0.1:5433`, usa UTC y contiene la base vacía `satlink_dev`. La autenticación SSPI vincula la cuenta Windows que preparó el entorno con el rol local `satlink_dev`, sin guardar contraseñas. Los binarios, datos y configuración particulares de esta computadora quedan en `.local`, excluida del control de versiones.

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

Las reglas de dependencia se explican en [Arquitectura](docs/architecture/README.md). Las carpetas [Scrum](docs/scrum/README.md) guardarán backlog, documentación de sprints, reviews, retrospectivas y criterios de terminado; por ahora no contienen historias, estimaciones ni planes de sprint. `docs/protocols` se reserva para contratos de comunicación y `scripts` para herramientas futuras del equipo.

## Verificación y pendientes

La preparación del repositorio, exclusiones y pasos para revisar un commit están en [Preparación para Git](docs/setup/git.md). Las reglas se mantienen desde la raíz en `.gitignore`, `.gitattributes` y `.editorconfig`.

Las versiones instaladas y los resultados se registran en [Entorno verificado](docs/setup/environment.md). Quedan para etapas posteriores el desarrollo de la aplicación y la API, las migraciones, las integraciones y la documentación Scrum acordada por el equipo. Esta preparación no valida conexiones MQTT, Tawhiri ni tráfico de telemetría.
