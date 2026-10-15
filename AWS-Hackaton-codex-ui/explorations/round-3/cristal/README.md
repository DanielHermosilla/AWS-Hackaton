# Cristal

Variante 3 de la ronda de diseño de ZMD Mobility, consultora para el desafío de CASE. Encargo de Diego, 15-10-2026. Parte de la opción 1 de `round-2/mapa` y conserva su distribución: flota a la izquierda, mapa dominante, resumen sobre las calles y detalle de parada.

El material translúcido aparece en los controles del mapa y sus botones de zoom. Las tarjetas, las cifras, el selector de pestañas y los detalles tienen bases opacas. Se usan tipografía del sistema, bordes suaves y un medidor rectangular de batería que acompaña el porcentaje de regreso.

La navegación frecuente tiene feedback inmediato de presión, selección y foco. El movimiento de cámara pertenece al helper compartido y respeta la preferencia de movimiento reducido. No se necesita la biblioteca Motion para esta variante.

Los datos, las secuencias y los valores energéticos son los mismos del ejemplo existente. Esta pantalla no aporta resultados del motor ni valida factibilidad, disponibilidad, ahorro u optimalidad.

## Código y pruebas

`index.html`, `app.js` y `style.css` consumen exclusivamente los helpers de `../shared/`. Para abrirla con el servidor local: `/round-3/cristal/`.

Prueba final: **15 de octubre de 2026, 01:28 America/Santiago / 04:28 UTC**. Chrome real con Playwright y WebGL mediante SwiftShader. Las capturas esperan la bandera compartida `data-map-ready`, establecida después del primer estado idle con rutas y encuadre.

`qa-results.json` registra **16 comprobaciones aprobadas**, sin errores de JavaScript:

- Vista 1440×900 sin desbordamiento, con ambos botones «Explorar recorrido» completos.
- Controles translúcidos y tarjetas/cifras opacas.
- Exploración por teclado con foco en la secuencia.
- Click real en V16, que selecciona parada 10 de Auto 1.
- Click real en V5, que cambia de Auto 1 a Auto 2 y sincroniza selección.
- BASE preservada por índice: salida y regreso son paradas distintas.
- Cierre del detalle y del diálogo con restauración de foco.
- Pestañas con flechas y Home/End.
- Control de sesenta cargadores, con las dos recargas del ejemplo conservadas.
- Preferencias de transparencia reducida, más contraste y colores forzados, emuladas por CDP y verificadas mediante `matchMedia` y estilos calculados.
- Vistas 390 y 319 px sin desbordamiento horizontal, con movimiento reducido, retorno a BASE y batería legible.
- Paradas libres de solapamientos con resumen, controles, leyenda y atribución en ambos anchos móviles.
- Integridad de los tres archivos copiados de la opción 1, comprobada con SHA-256.

Las capturas finales son `qa-desktop.png`, `qa-mobile-390.png`, `qa-mobile-319.png`, las variantes de selección y las tres de preferencias de accesibilidad. El script reproducible es `qa.cjs`; `baseline-hashes.json` conserva la referencia de integridad de la opción 1.

## Límites

El vidrio es una aproximación CSS sobria, no el material nativo de Apple. Las preferencias se probaron en Chrome mediante emulación; falta observación en dispositivos físicos y otros navegadores. El mapa necesita WebGL y conectividad para sus teselas; el helper compartido presenta su estado cuando la cartografía falla. La prueba verifica comportamiento y presentación de la interfaz, no el motor ni la validez energética de las cifras ilustrativas.
