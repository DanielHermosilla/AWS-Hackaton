# Revisión independiente · ronda 3

Actualizada: 15-10-2026, 01:46 America/Santiago. QA propia en Chrome headless instalado, contra `http://127.0.0.1:4173/round-3/`. No se modificó implementación ni se usó Git.

## 1. Disposición

**PASS / ship acotado para comparar las cuatro variantes.** No quedan hallazgos abiertos dentro de los casos ejecutados. Contraste de Batería, carreras de Motion y Escape del iframe están corregidos y confirmados con nuevas ejecuciones. Esta disposición no certifica toda la aplicación.

## 2. Hallazgos accionables y estado

| Prioridad | Estado | Hallazgo y prueba | Cambio concreto |
|---|---|---|---|
| P2 | Resuelto | Texto funcional del perfil abierto de Batería tenía contraste insuficiente: etiquetas y eje 3,45:1; escala SVG 2,94:1; leyenda 4,06:1; nota de límites 3,49:1. | `bateria/style.css:34`, `:39`, `:46`, `:51` ahora usan `#5f6e7c`. Chrome confirma los cinco selectores en `rgb(95,110,124)` sobre `#f9fbfd`: **5,05:1** cada uno. Captura C3 nueva inspeccionada; trazos conservados. |
| P2 | Resuelto | Activar movimiento reducido durante la entrada podía fijar opacidad 1 y después restaurar un valor intermedio sin animaciones activas. El cambio a teclado durante una salida también dejó opacidad 0,779138 y desplazamiento 1,7669 px permanentes. | `shared/motion.js:6` usa `animateMini`; `:59` completa el control antes de fijar el destino. Probe final 3/3: entrada, salida y Enter durante salida mantienen el destino correcto durante 400–1000 ms, con cero animaciones. |
| P2 | Resuelto | Con foco en `#fit` dentro del iframe, Escape no cerraba el comparador. | `gallery.js:27` conecta Escape desde el documento embebido. Confirmados tres niveles: diálogo interno primero; detalle primero; comparador cuando no hay superficie interna. Regresa foco al lanzador y se libera `src`. |

Evidencias: `independent-bateria-results.json`, confirmación final `independent-bateria-contrast.json` y `independent-bateria-profile-charge-confirmed.png`; `independent-motion-before.json`, `independent-motion-after-complete.json` y `independent-motion-probe.json`; `independent-gallery-before.json`, `independent-gallery-results.json` y `independent-gallery-return.json`.

## 3. Comportamiento y relación con la dirección

- Se mantiene el mapa de Ann Arbor como superficie principal, dos Leaf 2013, veinte entregas, dos recargas de ejemplo y los mismos datos. Los dieciocho hashes del baseline original permanecen intactos.
- Esencial compacta las tarjetas y la jerarquía. La selección Auto 1 → V5 actualiza Auto 2 en detalle, lista y mapa. BASE conserva índice 0 o 12 según la ocurrencia elegida; pulsar el pin tras seleccionar regreso no vuelve a salida. Teclado, anuncio de selección y retorno de foco comprobados.
- Batería añade perfiles dentro de las tarjetas y un perfil por parada, con escala 0–100 %. C3 índice 9 enlaza gráfica/lista/pin y muestra 22 → 50,1 %, +4,5 kWh. C9 índice 4 muestra 46 → 66 %, +3,2 kWh. BASE 0 y 12 se distinguen; Escape devuelve foco al punto exacto. Una inversión real del cierre CSS, con opacidad intermedia 0,224586, termina abierto, opacidad 1 y cero animaciones.
- Cristal limita el vidrio a controles: fondo medido `rgba(255,255,255,.88)` y blur de 18 px. Tarjetas, cifras y detalle son opacos. Emulación de transparencia reducida confirmada por `matchMedia`: controles `#f9fbfd`, blur eliminado. V16 selecciona índice 10; cruce V5 y regreso BASE de ambos autos correctos.
- El retorno por enlaces del iframe también pasa: marca del Original y «Comparar diseños» de Esencial cierran el comparador, conservan `/round-3/`, liberan el iframe y recuperan el foco correcto. Sólo se registró navegación a `about:blank`; no se cargó una galería anidada.
- Las alternativas son refinamientos cercanos de la base seleccionada, acordes al encargo de esta ronda. La elección final sigue correspondiendo a Diego.

La fixture conserva 41,25 % para Auto 2; la interfaz usa el formato vigente de un decimal, 41,3 %. Una aserción inicial del arnés pidió dos decimales y produjo un falso fallo; la evidencia de esa ejecución muestra correctamente Auto 2 / BASE / índice 12. No es un error de datos de la interfaz.

## 4. Capturas y cobertura

Todas las capturas propias se tomaron tras `data-map-ready=true` y estabilización de cámara; sus mapas y UI se inspeccionaron visualmente. Los móviles son capturas de página completa, desde viewports 390×844 y 319×859.

| Entrada | Cobertura propia | Resultado |
|---|---|---|
| Esencial | 1440×900; 900, 720 y 701 px; 390 y 319 px | Sin overflow; resumen contenido en mapa incluso cuando mide 391 px. Modelos y ambas rutas cargados. |
| Batería | 1440×900; 701, 390 y 319 px; perfil C3 con confirmación final | Sin overflow; ambas CTA visibles a 1440×900; enlaces entre perfil, paradas y mapa pasan. Cinco textos del perfil a 5,05:1. |
| Cristal | 1440×900; 900, 701, 390 y 319 px; transparencia reducida 319 px | Sin overflow; ningún centro de las 23 paradas visibles bajo controles, resumen, leyenda o atribución en móvil. |
| Comparador | Cuatro URLs/iframes a 1440; galería y Esencial embebida a 319 | Quince casos finales y dos retornos por enlace pasan. Cuatro imágenes cargadas. Cambio rápido termina en la última variante; teclado, Escape y foco confirmados. |
| Original | URL original en iframe a 1440; comparación de 18 hashes | Fuente y dependencias intactas. No se reaudita su implementación. |

Capturas: `independent-{esencial,bateria,cristal}-{1440,390,319}.png`, `independent-esencial-701.png`, `independent-cristal-reduced-transparency-319.png`, `independent-gallery-319.png` y `independent-gallery-modal-{1440,319}.png`. La comprobación visual final de los colores de Batería está en `independent-bateria-profile-charge-confirmed.png`; no se repitió la matriz de layout tras cambiar únicamente colores.

No hubo excepciones JavaScript ni respuestas HTTP ≥400 en las ejecuciones funcionales. Las cancelaciones de tiles al navegar/cambiar cámara están registradas aparte; no se cuentan como errores HTTP.

## 5. Límites y cierre

Esta revisión cubre los flujos descritos, legibilidad funcional del perfil y los anchos ejecutados. No certifica accesibilidad global, dispositivos físicos, GPS, motor, disponibilidad de cargadores ni factibilidad energética. La batería es una fixture ilustrativa, no un resultado del motor.

Confirmación final de contraste: 15-10-2026, 01:46 America/Santiago. Cinco selectores pasan y los dieciocho hashes originales siguen intactos. No quedan cambios solicitados por esta revisión. La comprobación inicial de `src` inmediatamente después de Enter se corrigió para esperar el evento `close`; el cierre real libera el iframe correctamente. Ctrl/Cmd-click no se ejecutó en la pasada acotada de retornos por enlace.
