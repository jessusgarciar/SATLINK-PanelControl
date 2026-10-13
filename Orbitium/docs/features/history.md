# Historial de telemetría

## Funcionalidad

PostgreSQL conserva las muestras de una misión y sus identificadores persistentes. El panel mantiene una ventana de hasta 1200 muestras; esta ventana no limita el archivo del backend.

El historial se consulta mediante `GET /api/v1/missions/{id}/telemetry`. La consulta paginada conserva el tipo `Telemetry` y sigue disponible como API.

La adaptación del Ejercicio 10 agrega controles de ventana y reproducción histórica al dashboard, además de exportación CSV. La API paginada sigue disponible; la reproducción consulta el archivo sin modificarlo. Los detalles de diagnóstico y modos están en [Dashboard y conexión ChirpStack](dashboard-chirpstack.md).

| Parámetro | Uso |
| --- | --- |
| `from` | Inicio opcional del intervalo de recepción, con fecha RFC3339 y zona horaria. |
| `to` | Fin opcional del intervalo de recepción, con fecha RFC3339 y zona horaria. |
| `cursor` | Cursor opaco devuelto por la página anterior. No debe construirse manualmente. |
| `limit` | Tamaño de página; predeterminado 200, máximo 1200. |

La respuesta contiene `items` y `nextCursor`. Una página sin continuación devuelve `nextCursor: null`. La ordenación usa `receivedAt` y el ID como desempate para que dos muestras con la misma fecha no se pierdan entre páginas.

## Ventanas y exportación

`GET /api/v1/missions/{id}/telemetry/window` acepta los filtros `from` y `to` y responde `{from, to, total, series, track}`. Sin inicio consulta todo el archivo; sin fin fija `to` en la hora de consulta. `series` contiene hasta 600 muestras para las gráficas y `track` hasta 500 puntos para la trayectoria. `total` cuenta todas las muestras del intervalo, incluidas las que no se dibujan. El panel ofrece 15 minutos, 1 hora, 6 horas, 24 horas y todo el historial.

`GET /api/v1/missions/{id}/telemetry/export.csv` entrega todas las filas del mismo intervalo, sin reducción visual. Incluye telemetría, dispositivo, radio y trazabilidad de origen. Utiliza el `from`/`to` devuelto por la ventana para exportar el mismo corte temporal; pedir otro `to` incorpora otro conjunto de muestras. No se convierte un valor desconocido en cero.

La reproducción fija sus límites al abrir, pagina el historial con hasta 1200 muestras visibles más una página pendiente de hasta 200 y conserva los timestamps originales a velocidades 1×, 5× o 10×. Durante ella se desactiva el stream en vivo y no se habilitan comandos ni predicción. Volver al modo en vivo solicita el estado actual.

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

Los resultados ejecutados, están en [Verificación PICARO](picaro-verification.md). Los fixtures son sintéticos. No existe purga automática; el archivo conserva las muestras. La política operativa de retención y la importación de CSV quedan fuera de esta etapa. La paginación garantiza recorrido estable para un conjunto que no cambia; si llegan paquetes atrasados durante la consulta, reinicia el intervalo para incluirlos.
