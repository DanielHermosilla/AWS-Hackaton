# Energía del recorrido

Propuesta de interfaz para ZMD Mobility, consultora del desafío de CASE. Encargo de Diego, 14–15 de octubre de 2026. Esta exploración presenta un puesto de control de batería: dos Nissan Leaf 2013, gráfico de estado de carga por paradas y mapa de la misma secuencia.

El perfil tiene la mayor jerarquía visual. Cada recarga conecta verticalmente la batería de entrada con la de salida; seleccionar un punto muestra su detalle y selecciona la ubicación correspondiente. La selección también funciona desde la secuencia y los marcadores del mapa.

La pantalla consume `../shared/data.js`, `map.js`, `base.css` e `icons.js`. El conjunto compartido aporta coordenadas públicas, geometría vial de demostración y cifras energéticas ilustrativas. La interfaz declara ese origen y conserva valores desconocidos como `—`. La capacidad de 16 kWh pertenece exclusivamente al ejemplo. No se presenta disponibilidad de cargadores, ahorro, optimalidad ni factibilidad energética.

Para abrirla con el servidor local existente: `/round-2/energia/`. El enlace de retorno apunta a `/round-2/`.

## Verificación

Prueba final: **15-10-2026 02:33 UTC / 14-10-2026 23:33 America/Santiago**. Chrome real con Playwright; cartografía cargada antes de las capturas.

Las doce comprobaciones de `qa.cjs` pasaron:

- Dos Leaf visibles, salida al 60 %, veinte entregas y regreso a BASE.
- Recarga representada como incremento vertical de SoC.
- Cambio de vehículo con Enter y conservación del foco.
- Flechas, Home y End en el gráfico; detalle, lista y mapa sincronizados.
- Selección de paradas con Espacio sin pérdida de foco.
- Click real sobre **Local 16 / V16**, que selecciona la parada 10 de Auto 1.
- BASE repetida: seleccionar su marcador conserva el retorno si ya estaba activo.
- Diálogo de procedencia: Escape cierra y devuelve foco.
- Sesenta cargadores visibles bajo el control; una estación externa a la secuencia no recibe batería ni disponibilidad inventadas.
- Vista de 1440 px sin desbordamiento horizontal.
- Vista de 390 px, retorno a BASE y movimiento reducido, sin desbordamiento horizontal.
- Entrada, salida, recarga, consumo y SoC final nulos muestran `—`.

No hubo errores de JavaScript. Las solicitudes observadas se limitaron al servidor local y `tiles.openfreemap.org`. El integrador corrigió la propagación de los clicks de marcadores en el helper compartido; esta pantalla conserva además una guarda para que reactivar la línea del vehículo actual no reinicie la parada seleccionada.

Evidencia:

- `qa-results.json`: resultado reproducible de la prueba.
- `qa-desktop.png`: captura completa de 1440 px.
- `qa-mobile.png`: captura completa de 390 px con movimiento reducido.
- `qa.cjs`: prueba ejecutable; requiere el servidor local en el puerto 4173 y el runtime Playwright indicado en su cabecera.

La prueba verifica la interfaz. No ejecuta el motor de Daniel/Lucas ni certifica las cifras del ejemplo.
