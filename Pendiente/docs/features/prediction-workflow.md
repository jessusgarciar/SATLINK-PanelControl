# Predicción: Planificación y Ascenso

La sección Recuperación muestra dos opciones. Cada una conserva sus ajustes durante la sesión y sus dos últimos cálculos exitosos en PostgreSQL, sin nuevas tablas ni migraciones.

- **Planificación**: fecha futura, lugar y altitud editables en la misma pantalla. Parte de los valores de misión; no modifica el sitio oficial. La referencia MSL debe estar confirmada.
- **Ascenso**: usa el último GPS válido y reciente. Permite declarar explícitamente que las altitudes de lanzamiento y GPS son MSL para esta consulta; la configuración de estación no se modifica. Seleccionarlo no cambia la fase física.
- Cambiar una velocidad modifica el borrador. El mapa conserva el resultado anterior de ese modo hasta una consulta exitosa; muestra las velocidades usadas y los cambios pendientes.
- La comparación usa los dos últimos éxitos del mismo modo: separación de aterrizajes, diferencia de hora y velocidades. No atribuye todas las diferencias a una velocidad: pueden cambiar origen, hora y meteorología.
- Un intento reserva 60 segundos por misión, compartidos entre modos. La cuenta regresiva se actualiza sin recargar. Un fallo conserva la ruta previa.
- Los errores HTTP de Tawhiri conservan su código en un mensaje seguro; el backend responde 502 ante fallos HTTP externos. No reenvía cuerpos de error del proveedor.
- Los borradores sobreviven al cierre del diálogo; recargar la página restaura resultados guardados e inicia los campos desde los valores de misión. “Restaurar valores de misión” renueva una fecha ya vencida.

El dashboard y la sesión demo añaden `predictionHistory` (hasta cuatro resultados). `prediction` conserva su contrato anterior. Clientes nuevos aceptan respuestas sin historial; requieren backend actualizado para recuperar ambos modos después de recargar.

Verificación:

```powershell
cd Orbitium/frontend
npm test
npm run lint
npm run build
node --experimental-strip-types tests/prediction-ui.mjs
```

La prueba visual ejecuta Edge sin ventana, con API sintética y solicitudes externas bloqueadas; no es evidencia de un vuelo ni de recepción de hardware.

## Comparación real de velocidades

Se hicieron tres consultas reales a Tawhiri, separadas por 61 segundos, con un origen de prueba (21°, -102°, 1870 m MSL), corte a 15000 m MSL, la misma fecha de lanzamiento y el dataset `2026-10-26T18:00:00Z`. No se utilizó telemetría de dispositivo ni se guardaron estos escenarios en la misión. [Solicitudes y resultados](../evidence/prediction-workflow/velocity-comparison.json).

| Ascenso | Descenso | Separación del aterrizaje frente al caso base | Diferencia de llegada |
| --- | --- | --- | --- |
| 5 m/s | 5 m/s | Caso base | Caso base |
| 6 m/s | 5 m/s | 5,333 km | 6,062 min antes |
| 5 m/s | 8 m/s | 6,362 km | 9,391 min antes |

Estos resultados comprueban que las velocidades cambian el cálculo para este escenario y meteorología. No constituyen una regla de desplazamiento para otros vuelos.

## Tiempo de espera

El cálculo admite hasta 30 segundos en el backend, con 25 segundos por espera de lectura de Tawhiri y 5 segundos para conectar. El navegador concede 35 segundos a la consulta de predicción; otras operaciones mantienen su espera habitual. No se reintenta automáticamente. Un 504 indica que se agotó la espera local; no demuestra una cuota agotada. El bloqueo local por cadencia sigue devolviendo 429. Los registros distinguen tiempo de conexión, lectura y límite total.
