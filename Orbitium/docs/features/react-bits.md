# Rediseño móvil de Orbitium con React Bits

## Alcance

Implementación exclusiva del frontend de Orbitium, basada en las preferencias acordadas y en UI UX Pro Max. Sustituye la primera prueba de iluminación por cursor y cristal en el menú. Se mantienen el contrato HTTP/WebSocket, los cálculos y la separación entre datos reales, derivados, predicciones y simulación. Pendiente no se modifica.

Se conserva JetBrains Mono local, fondo `#060A12`, superficies azul oscuro, cian `#00E5FF` y colores semánticos de estado. La nueva presentación prioriza uso táctil, jerarquía de altitud, etiquetas legibles, foco visible y acceso directo a secciones.

## Componentes y decisiones

| Componente React Bits | Integración |
| --- | --- |
| Gooey Nav | Barra inferior hasta 760 px, cuatro destinos con icono y etiqueta: Resumen, Mapa, Gráficas y Archivo. Usa los valores reales de Calm: 8 partículas, dispersión 28, oscilación 0,2, tiempo 520 ms, variación 300 ms y cohesión 0,5. Paleta oscura con selección cian. Los enlaces conservan sus fragmentos y el indicador sigue el desplazamiento. |
| Card Nav | Logo/nombre centrados y menú a la derecha. El selector de fuente, la fase y el tiempo están al inicio del desplegable, antes de las tarjetas Misión, Telemetría y Estación. Cierre con Escape, retorno del foco y cierre exterior. |
| Counter | Lectura Basic de altitud relativa, sin countdown, sin animación inicial desde cero ni controles de demo. Transición de 0,28 s, tres decimales, sin desenfoque ni rebote. Conserva el valor exacto como texto accesible. |
| Slosh Gauge | Instrumento de ascenso de solo lectura, escala lanzamiento/mitad/objetivo, marca de posición y porcentaje. Pequeña inercia sin salpicadura ni interacción de volumen. El porcentaje se limita visualmente a 0–100; la altitud numérica sigue mostrando valores por debajo o encima de la referencia. Sin lectura se muestra estado desconocido, no una altura ficticia. |
| Animated List | Bitácora técnica de solo lectura, filas planas y separadores discretos, sin marco, brillos ni selección ficticia. Se adaptaron roles de listbox/option a list/listitem y se mantuvieron fechas originales. No se mezcla con eventos físicos. |
| Glide Select | Solo el filtro secundario de ventana del archivo, tamaño táctil, colores oscuros y acento cian. El selector de fuente sigue siendo nativo. |
| Carousel | Detalles secundarios: GNSS, energía, radio, referencias de vuelo y configuración. Sin autoplay, con flechas, teclado y gesto horizontal. Los valores principales, sensores, mapa y gráficas permanecen fuera del carrusel. |
| Squish Switch | Sustituye el checkbox existente de Mapa base, conservando sus efectos y estado deshabilitado. La confirmación MSL de planificación sigue siendo checkbox. |
| Aurora | Únicamente en la cabecera, carga diferida, azul/cian, una capa, DPR 1, velocidad 0,22 e interacción de cursor desactivada. Se pausa fuera de pantalla; con movimiento reducido se desmonta y permanece el fondo estático. |

Stepper y Rubber Segment no se incorporaron. Se retiraron SpotlightCard y GlassSurface de la primera prueba.

## Código y procedencia

Se instalaron las variantes `TS-CSS` desde el [registro oficial](https://reactbits.dev/r/registry.json) mediante shadcn, el 19 de octubre de 2026. El código se conserva y adapta en `frontend/src/presentation/components/react-bits/`, con licencia MIT + Commons Clause y atribución a David Haz en `LICENSE.md`.

Composición específica de Orbitium:

- `MissionHeader.tsx`, `MissionNavigation.tsx`, `MissionSummary.tsx`, `MissionDetails.tsx` y `MissionLog.tsx`.
- `MissionIcon.tsx`: familia SVG de iconos de misión, decorativos cuando acompañan etiquetas.
- `styles/Mission.css`: paleta, jerarquía, composición responsive y adaptaciones de componentes. La interfaz reserva espacio inferior y utiliza `safe-area-inset-bottom`.
- `tests/mobile-ui.mjs`: verificación reproducible de comportamiento visual.

Adaptaciones relevantes del código de origen:

- Sincronización de referencias después del commit, sin escrituras durante el render, para pasar el lint React del proyecto.
- Aurora libera recursos gráficos sin forzar pérdida de contexto: el código original perdía el contexto al repetirse sus efectos bajo StrictMode. No se desactivó StrictMode.
- El carrusel sin vista previa lateral no añade sangrado fuera de su contenedor: se corrigió una expansión del viewport móvil de 393 a 404 px.
- Etiquetas españolas, roles de bitácora y preferencias de movimiento de Gooey Nav actualizables. La navegación detiene su trabajo pendiente al ocultar la página.
- Importaciones directas de cada icono Hugeicons en lugar del índice completo; redujo los módulos procesados por Vite de 7143 a 1138 en esta implementación.

## Dependencias

Las versiones directas quedan fijadas en `package.json` y `package-lock.json`:

- Producción: `@hugeicons/core-free-icons` 4.3.5, `@hugeicons/react` 1.1.10 y `motion` 12.43.0 (Squish Switch).
- Desarrollo: `playwright` 1.64.1.
- No se añadieron Tailwind, GSAP, Three.js ni un router.

La alias `@/*` de `tsconfig.json` permite que shadcn resuelva los destinos del registro; los componentes de aplicación continúan usando imports relativos.