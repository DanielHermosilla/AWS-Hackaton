# Revisión independiente — ronda 2

15-10-2026. Inspección inicial a las 02:52 UTC; comprobación posterior del lote a las 03:31 UTC; **cierre final tras las recapturas y ajustes de las 03:34 UTC**. Revisor independiente del autor. Se inspeccionaron las doce capturas actuales de 1440/390/319 px, la fuente corregida y la evidencia de confirmación. No se modificó la implementación.

Fuentes de criterio: `PRODUCT.md` y `docs/CONTEXTO.md` de este checkout; skill `zmd-ui-qa`; `craft-floor.md`. Los acuerdos de Diego y el feedback del 14–15 de octubre son el brief. Los JSON de QA de los autores son evidencia complementaria, no una aprobación independiente.

## 1. Disposición: ship, alcance acotado

**PASS: los tres hallazgos originales y los dos ajustes visuales de 319 px están resueltos. Las propuestas pueden presentarse a Diego.** La temática eléctrica y la diferenciación están presentes; las capturas corresponden y cargaron. Este cierre no declara elegida una interfaz ni certifica el motor o la accesibilidad completa.

La cartografía está cargada en las doce imágenes: hay calles, etiquetas geográficas, geometrías por vehículo, marcadores y atribución. No hay pantallas en blanco ni mensajes de carga pendientes. La nueva cámara mantiene el encuadre al redimensionar y Mapa cabe a 319 px. **En las recapturas finales, V14 se ve completo por encima de la atribución en despacho, energía y recorrido a 390/319 px; en Energía a 319 px se lee completo «Nissan Leaf 2013» y la ilustración tiene espacio propio.**

## 2. Hallazgos originales, estado posterior y prueba

| Fix original | Estado posterior | Evidencia |
|---|---|---|
| Encuadre tras resize | **Resolved** | `shared/map.js:124` vuelve a encuadrar sólo en modo `fit`; `confirmation.json` confirma `ResponsiveFitKeepsV14`, 561/542,5 px |
| Vehículo coherente entre lista, detalle y ruta | **Resolved** | `mapa/app.js:12` llama a `vehicle()` cuando cambia la ruta; `CrossVehicleSelectionConsistent` pasa Auto 1 → V5/Auto 2 |
| Seis textos funcionales con contraste insuficiente | **Resolved** | Colores computados en Chrome a 319 px y relaciones posteriores ≥4,5:1 |

Medición posterior de los textos originales, usando los fondos efectivos:

| Texto | Color actual / fondo | Relación actual |
|---|---|---:|
| SoC del timeline | `#526f85` / blanco | 5,29:1 |
| SoC sobre el paso activo | `#526f85` / `#eef5fb` | 4,81:1 |
| Editar batería y seleccionar fila | `#596853` / blanco | 5,95:1 |
| Motor no ejecutado | `#64725d` / blanco | 5,11:1 |
| Validación pendiente | `#5f7080` / blanco | 5,10:1 |
| Seleccionar punto del gráfico | `#53675a` / `#f8faf7` | 5,79:1 |

### Ajuste visual de encuadre a 319 px — Resolved

**Resolved.** `shared/map.js:61` reserva al menos 80 px de padding inferior cuando el contenedor del mapa mide menos de 700 px. Las nueve recapturas finales de despacho, energía y recorrido muestran V14 visible. `mobile-fixes.json` informa `nodeAttributionOverlap:false` en las nueve combinaciones de 1440/390/319 px.

La medición anterior se conserva para explicar la corrección: el marcador estaba dentro del viewport, pero debajo de la atribución de 44 px. Se midió después de una navegación fresca, esperando posición estable. `independent-confirmation-probe.json` conserva los rectángulos y colores previos.

| Dirección, 319 px | V14, intervalo vertical | Atribución, intervalo vertical | Observado |
|---|---:|---:|---|
| Recorrido | 529,5–558,5 px | 523–567 px | Superposición |
| Energía | 1496,3–1525,3 px | 1503,8–1547,8 px | Superposición |
| Despacho | 1324,4–1353,4 px | 1340,9–1384,9 px | Superposición |
| Mapa | 437,5–466,5 px | 486–530 px | Sin superposición |

La atribución sigue visible en las capturas finales. La corrección preserva espacio tanto para ese texto como para el marcador, sin modificar coordenadas ni ocultar los créditos.

### Ajuste visual del Leaf a 319 px — Resolved

**Resolved.** `energia/style.css:46` coloca la ilustración en flujo normal a ≤460 px. Las recapturas a 390/319 muestran el modelo completo y el auto debajo, sin superposición. `mobile-fixes.json` registra `carModelOverlap:false` en ambos móviles.

El mismo registro devuelve `carModelOverlap:true` para desktop energía porque compara el rectángulo completo del `span` de bloque con la ilustración. En la captura 1440 px los glifos del modelo están a la izquierda y el auto a la derecha, sin contacto visible. Esa intersección de contenedores no se trata como una colisión de texto. El fallo previo de 319 sí ocultaba glifos; quedó corregido.

Los tres hallazgos y sus medidas iniciales se conservan a continuación como historial; sus estados actuales son los de la tabla de estado.

### P2 — El encuadre completo deja de ser completo tras cambiar el ancho

**Fallida, reproducida.** `shared/map.js:109` observa el tamaño pero sólo ejecuta `map.resize()`. El encuadre se calcula en `fit()` (`shared/map.js:48`) y no vuelve a calcularse al cambiar la proporción del contenedor.

Pasos: abrir `/round-2/recorrido/` a 390×844; esperar `data-map-ready`; cambiar a 1440×900 y encuadrar; volver a 390×844. Se midió la posición estable del marcador V14, no la mera ausencia de tráfico.

| Estado | Borde inferior del mapa | Borde inferior de V14 | Resultado |
|---|---:|---:|---|
| Navegación fresca a 390×844 | 561 px | 542,5 px | Aprobada: cabe |
| 1440×900, después de encuadrar | 685 px | 640,5 px | Aprobada: cabe |
| Redimensionar de 1440 a 390 | 561 px | 603,5 px | Fallida: queda fuera |
| Pulsar encuadre en móvil | 561 px | 542,5 px | Aprobada: se recupera |

No hubo excepciones JS ni desbordamiento horizontal de página. `overflow=false` no detecta un marcador que queda fuera del viewport interno del mapa. La prueba inspeccionó `shared/map.js` con SHA-256 `de576b5ad4986f7529a731111f33cdddc4ae9a5ac513064bb90b83c8bbddd13e`.

Impacto: la comparación móvil esconde una entrega y parte del trazado. Cambio concreto: conservar un estado de cámara «encuadre completo» y recalcularlo al cambiar el tamaño mientras siga activo; conservar el centro elegido cuando haya enfoque de parada o desplazamiento manual. Recapturar energía y recorrido móvil desde navegación fresca o después del encuadre final. La prueba descarta que haga falta mover V14 o corregir las coordenadas OSRM para resolver este recorte.

### P2 — Mapa puede mezclar detalle del Auto 2 con lista y recorrido activo del Auto 1

**Fallida en la revisión de flujo de código; reproducción interactiva independiente pendiente.** `mapa/app.js:11` establece el vehículo activo al entrar desde «Explorar recorrido». `mapa/app.js:12` resuelve la parada pulsada usando `node.vehicleId`, pero no actualiza `selected`, no vuelve a renderizar la lista y no llama a `map.selectVehicle()` cuando el nodo pertenece a otro auto.

Caso concreto: explorar Auto 1 y pulsar V5 o C9 del Auto 2. Ambos nodos tienen `vehicleId: "auto-2"` en la fixture. El detalle toma el SoC del Auto 2 mientras la lista conserva las paradas del Auto 1 y `shared/map.js:58` sigue atenuando los marcadores del Auto 2 según el vehículo anterior.

Impacto: se pierde el principio «mapa, vehículo y paradas representan el mismo recorrido». Cambio concreto: al seleccionar una parada que pertenece a otro recorrido, sincronizar vehículo activo, lista y ruta antes de mostrar el detalle. No atribuir una ruta a un cargador registrado que no participe en la secuencia. Energía ya contempla explícitamente este cambio en `energia/app.js:203`.

### P2 — Parte del texto necesario para operar tiene contraste insuficiente

**Fallida, colores medidos.** Se calculó luminancia sRGB con los colores CSS reales. Para el SoC del timeline se confirmó además el color computado en Chrome: `rgb(129, 154, 172)`, tamaño 9 px. El criterio del craft floor es 4,5:1 para texto normal.

| Texto funcional | Archivo / selector | Primer plano / fondo | Relación |
|---|---|---|---:|
| Porcentajes de batería del timeline | `recorrido/style.css:1`, `.soc-label` | `#819aac` / blanco | 2,94:1 |
| Editar batería | `despacho/style.css:93`, `.quiet-button` | `#7f8978` / blanco | 3,65:1 |
| Instrucción para seleccionar fila o punto | `despacho/style.css:155`, `.selection-neutral` | `#939f85` / blanco | 2,79:1 |
| Aviso de motor no ejecutado | `despacho/style.css:128`, `.workspace-footer` | `#9ba28f` / blanco | 2,64:1 |
| Validación del motor pendiente | `mapa/style.css:1`, `.sidebar-foot` | `#7b8997` / blanco | 3,58:1 |
| Instrucción para seleccionar punto del gráfico | `energia/style.css:25`, `.chart-hint` | `#718076` / `#f8faf7` | 3,96:1 |

La asignación de entregas en despacho (`#677d56` sobre blanco) alcanza 4,52:1; el encabezado de tabla (`#6d7a5f`) alcanza 4,57:1. No se pide oscurecerlos por preferencia estética. Tampoco se exige contraste de texto a las rutas inactivas, sombras o decoración.

Impacto: cuesta leer la batería al revisar la secuencia y encontrar una acción de configuración; además se debilitan los avisos que distinguen una demostración de un resultado validado. Cambio concreto: oscurecer esos textos dentro de sus paletas actuales, comprobar estados activo/hover y volver a medir. No es necesario cambiar la dirección cromática.

## 3. Coherencia con la dirección y el feedback

**Aprobada en las capturas.** Mapa presenta los dos Leaf y sus baterías junto al territorio; despacho relaciona entregas, asignación y batería con un mapa lateral; energía hace protagonista el perfil de SoC y la recarga; recorrido permite revisar una secuencia con batería por parada. La relación con electromovilidad se reconoce sin leer una explicación del diseñador.

| Dirección | Objeto que domina | Diferencia real |
|---|---|---|
| Mapa | Territorio y flota | Mapa grande, vehículos en un panel |
| Despacho | Preparación y entregas | Lista operacional, filtros y configuración de batería |
| Energía | Evolución de batería | Instrumento oscuro, gráfico interactivo y balance por parada |
| Recorrido | Secuencia | Timeline horizontal y reproducción por paradas |

Comparten datos, colores por vehículo e iconos, pero no son cuatro cambios de color del mismo layout. Mapa y despacho son las más próximas en contenido; la jerarquía y el modo de operar siguen siendo distintos. El móvil adapta la composición y utiliza scroll local para tarjetas, tabla o timeline. No se interpreta ese contenido deliberadamente desplazable como un desbordamiento de página.

**Aprobada la coherencia aritmética de la fixture, no la factibilidad energética.** Hay 20 visitas únicas, diez por vehículo, sin faltantes ni duplicados. Las dos secuencias tienen 13 pasos y empiezan/terminan en BASE. Con 16 kWh exclusivamente ilustrativos, los descensos entre pasos suman 8,1 y 6,2 kWh; los aumentos en C3 y C9 equivalen a 4,5 y 3,2 kWh. Los retornos de 37,5 % y 41,25 % coinciden con esos balances. Las etiquetas de ejemplo y procedencia están visibles; no se inventa ahorro, tiempo de cálculo ni seguimiento en vivo.

**Marca, alcance general aprobado para comparar.** `brand/qa/overview-light.png` contiene doce propuestas cargadas con ZMD Mobility. Baterías, enchufes, cargador y vehículo conectado sí responden al feedback. «ZMD en ruta» comunica movilidad antes que electricidad; «ZMD eléctrico» depende de un quiebre sutil de la Z. Son riesgos de lectura inmediata para la elección de Diego, no razones para descartar toda la familia. La imagen general no comprueba los dos símbolos que el autor estaba afinando ni su lectura a 20 px.

## 4. Matriz de capturas y cobertura

Las dimensiones siguientes se leyeron del encabezado PNG. Desktop se tomó en viewport 1440×900; algunas imágenes incluyen scroll completo.

| Captura | Dimensiones PNG | Correspondencia y estado visible | Cartografía | Disposición |
|---|---:|---|---|---|
| `qa/mapa-desktop.png` | 1440×900 | Mapa + dos tarjetas Leaf; ambos recorridos | Cargada | Aprobada en este alcance |
| `qa/mapa-mobile.png` | 390×1102 | Mapa primero; tarjetas en scroll horizontal | Cargada | Aprobada en este alcance |
| `qa/despacho-desktop.png` | 1440×901 | Plan de ejemplo abierto, tabla y mapa lateral | Cargada | Aprobada en este alcance |
| `qa/despacho-mobile.png` | 390×1529 | Mismo plan; tabla con scroll interno, V14 visible | Cargada | Aprobada en este alcance |
| `qa/energia-desktop.png` | 1440×1125 | Auto 1, C3 seleccionada; 22 % → 50,1 % | Cargada | Aprobada en este alcance |
| `qa/energia-mobile.png` | 390×1757 | Mismo Auto 1/C3; modelo y V14 visibles | Cargada | Aprobada en este alcance |
| `qa/recorrido-desktop.png` | 1440×900 | Auto 1, salida de base, paso 1 de 13, 60 % | Cargada | Aprobada en este alcance |
| `qa/recorrido-mobile.png` | 390×975 | Mismo paso; V14 visible sobre atribución | Cargada | Aprobada en este alcance |
| `qa/mapa-user-319.png` | 319×1102 | Resumen refluye y no desborda; V14 visible | Cargada | Aprobada en este alcance |
| `qa/despacho-user-319.png` | 319×1542 | Entregas, baterías y V14 visibles | Cargada | Aprobada en este alcance |
| `qa/energia-user-319.png` | 319×1836 | Perfil y cifras legibles; modelo y V14 visibles | Cargada | Aprobada en este alcance |
| `qa/recorrido-user-319.png` | 319×991 | Batería/timeline legibles; V14 visible | Cargada | Aprobada en este alcance |

Los nombres y contenidos de las doce imágenes coinciden. No se sustituyeron por `energia/qa-initial-desktop.png`. La energía selecciona C3 desde el código al iniciar: no es una captura accidental de otra pantalla. La altura 1125 de desktop energía debe declararse como full-page para no confundirla con una composición completa dentro de 900 px.

Cobertura independiente: inspección visual de 12/12 imágenes actuales, lectura de las correcciones, seis contrastes originales medidos, reproducción inicial de cámara en 390/1440 y comprobación acotada posterior de los rectángulos a 319 px. `confirmation.json` acredita los dos checks de bugs; `delivery.json` registra cuatro enlaces/imágenes cargados en galería a 1440/319 y `map319Overflow:false`, posterior al fallo a 319 conservado en `confirmation.json`. `mobile-fixes.json` comprueba las nueve vistas afectadas sin desbordamiento ni V14 sobre la atribución. No se atribuyen estos checks del integrador al revisor. Las pruebas a 900 px y la cobertura completa de teclado siguen procediendo del QA de autor.

## 5. Límites y cambios concretos

La revisión evalúa prototipos sintéticos. No hay motor conectado ni resultado para comparar con una ejecución. El balance ilustrativo no comprueba compatibilidad de cargadores, consumo real ni factibilidad en cada tramo. No se revisaron rondas anteriores, AWS, presupuesto ni una arquitectura futura.

El informe no certifica accesibilidad completa. Hay controles nativos y foco visible en el CSS; energía implementa flechas/Home/End en el gráfico y recupera foco tras renderizar; despacho implementa flechas en tabs y filas; recorrido devuelve foco al item del timeline y al cambio de vehículo. Estos hechos de código y el QA de autor no sustituyen un recorrido de teclado independiente completo. El cambio de ruta por selección de nodo tiene corrección y prueba de confirmación.

`confirmation.json` identifica los requests fallidos de tiles como `net::ERR_ABORTED`. Las doce imágenes y la comprobación posterior tienen cartografía cargada; no hay evidencia de errores HTTP del proveedor en ese registro. Esto no demuestra una recuperación ante una caída de red.

Cierre:

1. Los tres fixes originales están **Resolved**.
2. Los ajustes de atribución y modelo del Leaf a 319 px están **Resolved**; las capturas afectadas se actualizaron.
3. No queda trabajo requerido dentro de este alcance de revisión.
4. Presentar las cuatro alternativas y la marca como propuestas para decisión de Diego. No llamar «seleccionada», «factible» u «optimizada» a la demostración.
