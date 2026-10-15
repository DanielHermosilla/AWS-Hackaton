# ZMD Mobility — exploración de identidad

Seis propuestas originales de símbolo: Cauce, Acople, Umbral, Tríada, Órbita y Módulo. CASE identifica al cliente del desafío; esta identidad corresponde a ZMD Mobility.

Abrir `index.html` directamente en un navegador. No requiere build, dependencias, cuenta, red ni datos del motor. Los controles alternan fondo claro/oscuro y escala de 20/32/80 px. Destacar un concepto es una acción temporal de comparación, sin aprobación ni persistencia.

`manifest.json` enumera los conceptos y las rutas relativas. Cada carpeta `assets/<concepto>/` contiene un símbolo `symbol.svg` y dos logotipos horizontales `lockup-light.svg` / `lockup-dark.svg`, todos transparentes y editables. El símbolo usa `currentColor`; las variantes de logotipo fijan un color por defecto. Se pueden ajustar trazados y texto con un editor SVG.

Los logotipos conservan texto editable con tipografía de sistema y fallback. El ancho y la forma de las letras pueden variar entre sistemas; un activo de marca definitivo necesitará fijar la tipografía o preparar trazados manteniendo una fuente editable y su licencia. No se realizó búsqueda de marcas registradas ni se promete exclusividad.

Comprobaciones realizadas con Chrome headless y un perfil temporal limpio: galería a 1440, 390 y 320 px; controles de fondo y tamaño; destacar/deseleccionar; activación con Enter y paso de foco con Tab. Los 18 SVG se comprobaron como XML y en el navegador: contenido/texto dentro de viewBox, sin raster, scripts o recursos externos. No se observaron errores de consola, solicitudes remotas ni desbordamiento horizontal en los tamaños revisados. `qa/verification.json` conserva la evidencia; `qa/asset-proof.html` / `.png` comparan los activos exportados sobre claro y oscuro. También hay capturas desktop/mobile.

Revisión visual: se amplió el vacío central de Tríada porque el primer trazado se comprimía a 20 px. La versión actual distingue sus planos, pero sigue siendo la geometría más sensible al tamaño. Cauce y Acople ofrecen una lectura de flujo/sistema más inmediata. Umbral puede recordar acceso o resguardo; Órbita puede parecer un indicador de estado; Módulo permite una lectura D/E poco directa para ZMD. Estas asociaciones son límites de los conceptos, no identidades elegidas. Los ejemplos de cabecera son muestras de uso y no una pantalla operativa.

La revisión no incluye lector de pantalla, otros navegadores, impresión, bordado ni una búsqueda de marcas. Un vector válido y las comprobaciones anteriores no sustituyen la elección y refinamiento de una identidad definitiva.
