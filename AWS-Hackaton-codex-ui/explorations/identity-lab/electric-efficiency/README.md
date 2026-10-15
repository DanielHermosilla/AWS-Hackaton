# Ronda nueva — electromovilidad y eficiencia

Doce marcas vectoriales originales para ZMD Mobility: seis de electromovilidad y seis de eficiencia. Son una exploración nueva; las seis direcciones anteriores permanecen separadas. No hay selección aprobada.

`manifest.json` es un array de 12 entradas: ID, nombre, familia, significado, riesgo de lectura, símbolo y logotipos claros/oscuros. Las rutas son relativas a esta carpeta. Se señalan un máximo de tres recomendaciones de diseño, sin aprobarlas.

Cada carpeta `assets/<id>/` contiene `symbol.svg`, `lockup-light.svg` y `lockup-dark.svg`. Los símbolos tienen viewBox 64×64, son monocromos, usan currentColor y contienen pocos trazados editables. Los logotipos conservan texto editable con tipografía de sistema y fondo transparente; las métricas pueden variar entre plataformas.

`qa/proof.html` sirve como hoja local de comprobación a 20, 32 y 80 px en claro y oscuro. La galería común la mantiene el integrador. La revisión no acredita exclusividad de marca.

Ronda lista para comparar (`status: ready-for-comparison`, revisión 2 en cada entrada). Se inspeccionaron la hoja de símbolos y los logotipos exportados en Chrome headless con perfil temporal: 36 SVG dentro de su viewBox, sin errores de página ni recursos remotos solicitados. Los símbolos se renderizaron a 20, 32 y 80 px sobre fondo claro y oscuro. `qa/structure.json` y `qa/verification.json` conservan comprobaciones; `qa/proof.png` y `qa/lockup-proof.png` muestran la versión revisada.

Se corrigieron tres problemas de diversidad/forma: Relevo dejó de ser una S cerrada, Reingreso pasó de una G literal a un bucle de retorno abierto y Convergencia ahora reúne las ramas en un terminal sólido. No se añadieron más variantes.

Veta, Contacto y Atajo se recomiendan para comparar por silueta, simplicidad y relación conceptual. Contacto e Impulso hacen más directa la lectura eléctrica; Impulso conserva mayor riesgo de parecer una chispa genérica. Inducción puede parecer un botón y Rotor una turbina o indicador; por eso no están recomendados. Los riesgos de cada dirección están en el manifest.

La revisión no reemplaza la elección de Diego, una prueba de reconocimiento ni la fijación de tipografía final. El contraste inverso y los tamaños observados funcionan en el navegador comprobado; no se probaron todos los medios de reproducción.
