# Historial de telemetría

## Funcionalidad

PostgreSQL conserva las muestras de una misión y sus identificadores persistentes. El panel mantiene una ventana de hasta 1200 muestras; esta ventana no limita el archivo del backend.

El historial se consulta mediante `GET /api/v1/missions/{id}/telemetry`. No se agrega una pantalla nueva: la consulta paginada queda disponible como API y conserva el tipo `Telemetry` existente.

| Parámetro | Uso |
| --- | --- |
| `from` | Inicio opcional del intervalo de recepción, con fecha RFC3339 y zona horaria. |
| `to` | Fin opcional del intervalo de recepción, con fecha RFC3339 y zona horaria. |
| `cursor` | Cursor opaco devuelto por la página anterior. No debe construirse manualmente. |
| `limit` | Tamaño de página; predeterminado 200, máximo 1200. |

La respuesta contiene `items` y `nextCursor`. Una página sin continuación devuelve `nextCursor: null`. La ordenación usa `receivedAt` y el ID como desempate para que dos muestras con la misma fecha no se pierdan entre páginas.

## Ejemplo

```http
GET /api/v1/missions/satlink-001/telemetry?limit=200
```

```json
{
  "items": [],
  "nextCursor": null
}
```

El ejemplo representa una misión existente sin muestras; no es evidencia de una consulta ejecutada. Para obtener otra página, conserva los filtros y envía el `nextCursor` recibido como `cursor` con la codificación URL correspondiente.

## Verificación

Los casos de aceptación incluyen una misión vacía, misión inexistente, aislamiento de misiones, intervalo temporal, validación de límites/fechas/cursor y paginación con timestamps iguales. El snapshot y el historial deben devolver los mismos IDs y unidades para una misma muestra.

Los resultados ejecutados están en [Verificación PICARO](picaro-verification.md). Los fixtures son sintéticos. No existe purga automática; el archivo conserva las muestras. La política operativa de retención, exportación y una interfaz para navegar el archivo quedan fuera de esta etapa. La paginación garantiza recorrido estable para un conjunto que no cambia; si llegan paquetes atrasados durante la consulta, reinicia el intervalo para incluirlos.
