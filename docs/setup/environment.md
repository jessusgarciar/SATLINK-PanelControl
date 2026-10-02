# Entorno verificado

Preparación realizada el 1 de octubre de 2026 en Windows. El reporte fuente disponible fue `Reporte_StackSoftware-PC-Telemetria_SATLINK.pdf`. No se encontraron instrucciones AGENTS.md en el proyecto ni en el directorio padre comprobado. La carpeta inicial no era un repositorio Git; esta etapa no lo inicializó.

## Herramientas

| Herramienta | Versión | Estado |
| --- | --- | --- |
| Node.js | 22.18.0 | Ya instalada. |
| npm | 10.9.3 | Ya instalado. |
| Python | 3.13.7 | Ya instalado; entorno virtual en `backend/.venv`. |
| PostgreSQL | 17.11 | Instalación portátil nueva en `.local/postgresql`. |

Docker estaba instalado pero su motor no estaba disponible; no fue necesario para preparar este entorno. Se utilizó la distribución portátil de PostgreSQL indicada en la [documentación oficial para Windows](https://www.postgresql.org/download/windows/). La versión de Node.js disponible cumple el requisito de [Vite](https://vite.dev/guide/).

## Frontend

| Dependencia | Versión |
| --- | --- |
| React / React DOM | 19.3.0 |
| TypeScript | 6.0.3 |
| Vite | 8.3.2 |
| Leaflet | 1.9.4 |
| React Leaflet | 5.0.0 |
| Apache ECharts | 6.1.0 |
| echarts-for-react | 3.0.6 |
| @types/leaflet | 1.9.22 |
| @types/react | 19.3.0 |
| @types/react-dom | 19.3.0 |

La plantilla oficial se generó con create-vite 9.2.1. Sus archivos se reubicaron en `src/app` y `src/presentation`, con ajustes de rutas. Las dependencias de React y los tipos restantes se conservan en el manifiesto y el archivo de bloqueo.

## Backend

| Dependencia | Versión |
| --- | --- |
| FastAPI | 0.142.2 |
| Uvicorn | 0.54.0 |
| Pydantic | 2.13.5 |
| aiomqtt | 2.5.1 |
| SQLAlchemy | 2.1.1 |
| psycopg / psycopg-binary | 3.3.6 |
| Alembic | 1.20.0 |
| HTTPX | 0.28.1 |

Se instalaron `uvicorn[standard]`, `SQLAlchemy[asyncio]` y `psycopg[binary]`, incluyendo sus dependencias transitivas. `requirements.lock.txt` registra el entorno completo y `requirements.txt` conserva los extras solicitados.

## Verificaciones realizadas

- Reinstalación del frontend con `npm ci` desde el archivo de bloqueo, compilación TypeScript/Vite y revisión con oxlint correctas.
- Árbol de dependencias npm sin incompatibilidades reportadas; auditoría de instalación con cero vulnerabilidades reportadas en ese momento.
- `pip check` sin dependencias rotas; importaciones de todas las bibliotecas principales correctas.
- Disponibilidad de `SelectorEventLoop.add_reader` en Python 3.13.7; no se probó una conexión MQTT ni su coexistencia con Uvicorn.
- PostgreSQL arrancó en `127.0.0.1:5433`; `pg_isready` indicó que aceptaba conexiones.
- Conexión SSPI mediante psql y psycopg a la base vacía `satlink_dev`, sin consultas de aplicación ni creación de tablas.
- PostgreSQL se detuvo al terminar, conservando el clúster y la base de desarrollo.

Las verificaciones prueban instalación y preparación básica del entorno. El frontend todavía muestra la plantilla Vite y el backend no tiene una aplicación ejecutable. La compatibilidad de integraciones, esquema y comportamiento se verificará cuando exista implementación.
