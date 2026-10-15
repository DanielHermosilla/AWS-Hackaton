# Revisión de la base elegida · 15-10-2026

Chrome 155, en navegador local. Alcance: combinar los materiales de Cristal con Esencial y corregir las superposiciones del mapa móvil. No certifica el motor ni toda la accesibilidad del producto.

**23 comprobaciones aprobadas** en [verification.json](verification.json):

- Tamaños de tarjetas, automóviles y controles frente a Esencial en 1440, 900, 701, 390 y 319 px.
- En los tres anchos de escritorio, posiciones, padding y tamaños de texto también coinciden con la referencia medida.
- Sin desbordamiento horizontal en esos anchos. Capturas finales de [escritorio](base-1440.png), [390 px](base-390.png) y [319 px](base-319.png).
- Cristal en controles: blur de 18 px; contenido y cifras sobre blanco opaco.
- Selección C3/recarga, cruce al Auto 2 desde V5, regreso a BASE conservando su índice, cierre y recuperación de foco.
- Pestañas con teclado y diálogo de procedencia con Escape.
- Sesenta estaciones registradas al activar su capa; dos recargas del ejemplo con ambos vehículos visibles.
- Reducción de transparencia, contraste reforzado, colores forzados y movimiento reducido.
- Dieciocho hashes originales de la ronda 2 coinciden. No se modificaron las variantes históricas.
- Sin excepciones JavaScript ni respuestas HTTP ≥400 durante las comprobaciones.

**Revisión independiente: 18 casos de cámara y 12 de foco móvil aprobados.** A 319, 390 y 1440 px, los 23 marcadores completos quedan libres de controles en el encuadre inicial; C3, las dos ocurrencias de BASE y el cruce a V5 pasan. El clic directo entre vehículos conserva la cámara. La leyenda y la atribución no se superponen.

La primera pasada identificó que seleccionar desde la lista móvil dejaba el mapa fuera del viewport. Se corrigió en `plan.js`: al seleccionar se muestra el mapa y se enfoca Cerrar detalle; cerrar o Escape recupera la fila visible. La segunda pasada probó 12 combinaciones de C3/BASE salida/BASE regreso × clic/Enter × 319/390, todas aprobadas, incluyendo filas reemplazadas al cambiar de vehículo. No quedan hallazgos abiertos dentro de este alcance.

Evidencia: [cámara inicial](independent-camera.json), [cierre de foco/scroll](independent-mobile-focus.json) y [detalle final a 319 px](detail-319.png). El `passIncludingViewport:false` del primer JSON registra el hallazgo original; la segunda pasada comprueba su resolución. En algunas capturas de la revisión de cámara apareció un aviso de carga parcial del proveedor, con rutas y marcadores presentes; esa revisión no certifica la conectividad del proveedor.

Durante la preparación del arnés se corrigieron dos expectativas de la prueba, sin cambios de producto asociados: el número de cargadores usados depende del vehículo seleccionado, y el índice 4 debe acompañarse del ID de vehículo cuando se muestran ambos recorridos. El informe final conserva únicamente comprobaciones ejecutadas con esas precondiciones correctas.

## Autoría y Kiro

La geometría y comportamiento inicial provienen de Esencial, checkpoint `142e737`. Codex integró el material de Cristal, corrigió el encuadre/selección móvil y realizó la verificación. No se atribuye este código a Opus.

El intento nuevo y exclusivo de Kiro confirmó **`claude-opus-5.5`, esfuerzo `max`**, pero no produjo texto ni CSS. Se canceló tras **255 s** sin progreso de implementación, se reconcilió como `aborted` y quedó sin runner activo ni prompts sin resolver. El coste no fue informado.

Estado privado de continuidad: `/Users/caballero/.codex/zmd-collaboration/sessions/opus-selected-base/`. El nuevo chat debe usar su propio estado y comprobar los aportes efectivos de Opus, como exige el reparto autorizado por Diego.
