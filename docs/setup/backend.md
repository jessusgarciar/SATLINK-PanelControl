# Ejecutar el backend de telemetría

Esta etapa permite recibir telemetría del Ejercicio 09, persistirla en PostgreSQL, consultar el historial y actualizar el panel por WebSocket. El servicio es de lectura para el operador y se ejecuta únicamente en localhost, sin login inicial. No habilita telecomandos ni predicción.

## Preparar el entorno

Usa Python 3.13 y PostgreSQL 17. Desde la raíz, crea el entorno virtual si aún no existe:

```powershell
python -m venv backend/.venv
. ./backend/.venv/Scripts/Activate.ps1
cd backend
python -m pip install -r requirements-dev.txt -c requirements.lock.txt -c requirements-dev.lock.txt
python -m pip check
```

Si PowerShell impide activar el entorno, utiliza `./backend/.venv/Scripts/python.exe` desde la raíz o `./.venv/Scripts/python.exe` desde `backend` como sustituto de `python`. No hace falta cambiar la política del sistema. Para una instalación sin herramientas de pruebas, instala `requirements.txt` con `requirements.lock.txt`.

Los requisitos directos y los archivos de bloqueo fijan las versiones del proyecto. PostgreSQL local y su autenticación SSPI se describen en [Preparación de PostgreSQL](postgresql.md).

## Configurar y migrar

Desde `backend`, copia `.env.example` a `.env` y revisa los valores antes de iniciar:

```powershell
Copy-Item .env.example .env
python -m alembic upgrade head
```

| Variable | Uso |
| --- | --- |
| `SATLINK_DATABASE_URL` | URL de SQLAlchemy con controlador psycopg para la base de aplicación. |
| `SATLINK_MQTT_ENABLED` | `false` de forma predeterminada; activa explícitamente la recepción MQTT con `true`. |
| `SATLINK_MQTT_HOST`, `SATLINK_MQTT_PORT` | Broker MQTT de ChirpStack. |
| `SATLINK_MQTT_USERNAME`, `SATLINK_MQTT_PASSWORD` | Credenciales del broker cuando correspondan. |
| `SATLINK_MQTT_TLS` | Activa TLS para la conexión MQTT. |
| `SATLINK_CHIRPSTACK_SOURCE` | Identificador del origen de ChirpStack; predeterminado `chirpstack-local`. Debe coincidir con la misión. |

`.env` contiene configuración local y no debe versionarse. Ninguna credencial pertenece a variables públicas `VITE_*`. El ejemplo no configura por sí solo un broker ni un dispositivo físico.

## Registrar una misión e iniciar

Revisa `mission.example.json` y guarda una copia `mission.local.json` con el identificador de misión, origen de lanzamiento y asociación a la aplicación/dispositivo reales. El origen ChirpStack, `applicationId` y DevEUI identifican la fuente autorizada. El ejemplo contiene `null` y marcadores deliberadamente inválidos: exige completar coordenadas, altitud, tasas nominales, watchdog y umbral de antigüedad. No contiene una misión de demostración lista para registrar. `mission.local.json` queda excluido de Git.

Desde `backend`:

```powershell
Copy-Item mission.example.json mission.local.json
# Completar mission.local.json con la configuración real antes del siguiente comando.
python -m app.bootstrap.cli init-mission --file mission.local.json
python -m app.bootstrap.cli serve
```

La misión debe existir antes de recibir su telemetría. La altura de lanzamiento es persistente y se expresa en metros sobre el nivel del mar. No se toma el primer uplink como origen ni se reutilizan muestras de demostración para inicializarla.

El arranque mediante la CLI configura el bucle de eventos de Windows necesario para aiomqtt. Conserva este punto de entrada para ejecutar conjuntamente FastAPI y la recepción MQTT.

## Conectar el panel

En `frontend/.env.local`, utiliza la configuración de [la guía del frontend](../../frontend/README.md#conectar-fastapi), con `VITE_MISSION_ID` igual al ID registrado y el proxy dirigido a `http://127.0.0.1:8000`. Reinicia Vite tras cambiar variables.

La estación real muestra telemetría y trayectoria. Los permisos `canCommand` y `canPredict` permanecen en `false`; las rutas POST de comandos y predicción están fuera de esta entrega. La ausencia de paquetes deja los datos previos visibles con su antigüedad; no activa la demostración.

## Pruebas y diagnóstico

Desde `backend`:

```powershell
python -m pytest
```

Las pruebas que requieren PostgreSQL usan `SATLINK_TEST_DATABASE_URL`. Debe apuntar a una base exclusiva cuyo nombre termine en `_test`; no se permite ejecutar esas pruebas contra la base de la misión. Las tablas de aplicación de esa base se vacían entre pruebas; nunca reutilices una base con datos que quieras conservar. Sin esa variable se omiten explícitamente las pruebas PostgreSQL. Ejemplo con el clúster local, una vez creada una base exclusiva:

```powershell
$env:SATLINK_TEST_DATABASE_URL='postgresql+psycopg://satlink_dev@127.0.0.1:5433/satlink_picaro_test'
python -m pytest -q
```

Con SSPI debes ejecutar bajo la identidad Windows autorizada. Las pruebas y los fixtures utilizan entradas sintéticas y no acreditan un enlace de radio. La CLI y las pruebas asíncronas usan SelectorEventLoop; no inicies el backend con un launcher que cambie ese bucle a Proactor en Windows. El TestClient produce una advertencia de deprecación por HTTPX con Starlette 1.7; se mantienen las versiones fijadas, sin instalar HTTPX2.

El servidor usa un único proceso y puerto 8000 (ajustable con `SATLINK_PORT`). `SATLINK_ALLOWED_ORIGINS` admite una lista separada por comas de orígenes localhost explícitos; actualízala si Vite cambia de puerto. El broker puede ser remoto aunque la API solo escuche localmente. `SATLINK_MQTT_CLIENT_ID` debe ser estable y exclusivo para esta estación.

Para revisar el funcionamiento, consulta el [contrato HTTP/WebSocket](../protocols/frontend-api-v1.md), el [protocolo del Ejercicio 09](../protocols/picaro-full-v1.md) y las entregas de [telemetría](../features/telemetry.md) e [historial](../features/history.md). Un fallo de PostgreSQL no debe producir una muestra publicada sin persistencia; un fallo de MQTT conserva lo ya guardado y permite reintentar la conexión.

El acceso compartido o el despliegue fuera de localhost requieren una etapa posterior de autenticación, autorización, TLS y revisión del origen WebSocket.
