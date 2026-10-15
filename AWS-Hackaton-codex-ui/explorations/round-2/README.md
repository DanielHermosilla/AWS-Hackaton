# Ronda 2 — electromovilidad reconocible

15-10-2026. Diego rechazó las cuatro interfaces y las treinta identidades anteriores y explicó: «no tienen nada que ver con el tema». Esta ronda reemplaza la dirección visual, conservando los originales como historial. Ninguna propuesta está aprobada.

## Producto y criterio

Usuario: jefa de flota. Web de computador primero. El primer vistazo debe relacionar vehículos eléctricos, entregas, batería y recargas, con claridad y minimalismo. Cuatro experiencias distintas: territorio y flota; lista de despacho; energía por parada; recorrido secuencial. La elección final sigue siendo de Diego.

PRODUCT.md recoge los acuerdos ya respondidos; no se reabrió la entrevista. La skill impeccable aportó disciplina de composición y revisión; zmd-apple-design, zmd-map-ui y zmd-logo-creator mantienen el criterio de producto. El sorteo de exploración c154feae se ejecutó; su tercer candidato se corresponde con control energético. Las referencias ajenas al tema se descartaron por la indicación explícita de Diego. Se conserva la comparación de cuatro prototipos funcionales pedida por el usuario, sin una aprobación intermedia de moodboards.

## Ejecutar

Desde el worktree: `python3 -m http.server 4173 --bind 127.0.0.1 --directory explorations`; abrir `/round-2/`.

`shared/fixture.local.json` conserva localmente los nodos del CSV público y el ejemplo. Se ignora en Git, como los datos originales. `shared/osrm-auto-*.local.json` conserva las dos respuestas usadas para geometría. Las letras y UI no requieren datos externos; el mapa base requiere internet. El JSON local no es un contrato del motor. Para reconstruirlo en otra máquina: `python3 explorations/round-2/shared/prepare-local-fixture.py /ruta/competition_routing_nodes.csv`. Este script prepara únicamente el ejemplo público, con asignaciones escritas a mano: no es un cargador genérico de escenarios. Hace dos consultas a OSRM si faltan las respuestas locales.

## Datos y límites

- 81 ubicaciones del archivo público: 1 base, 20 locales y 60 estaciones. No hay telemetría en vivo.
- Dos asignaciones manuales para representar el diseño, no una optimización. Cada visita aparece una vez y ambas secuencias terminan en BASE.
- Geometrías consultadas una vez a OSRM por orden de paradas, guardadas localmente. Sus 35,4 y 75,1 km son distancias de esos recorridos de demostración, no mejores rutas ni distancias del motor del proyecto. Los puntos pueden quedar separados del punto vial al que OSRM los ajustó.
- Los valores de energía/batería son escritos a mano, usando 16 kWh como capacidad **exclusivamente de la fixture** para mantener aritmética coherente. No reproducen el modelo ni fijan la batería del ejercicio. Consumo ilustrativo 8,1 + 6,2 = 14,3 kWh; recarga 4,5 + 3,2 kWh.
- No se simula tiempo de cálculo, ahorro económico, reducción porcentual ni inteligencia artificial ejecutándose. Recargar en la demo no demuestra que la estación esté libre u operativa.
- Despacho invalida el ejemplo al cambiar entradas; en las otras propuestas la fixture es de solo lectura. Reproducción avanza por paradas, no por tiempo ni GPS.

## Cartografía y procedencia

MapLibre GL JS 6.14.0, BSD-3-Clause, distribución NPM vendorizada sin modificar. Se conserva LICENSE.txt. Estilo Positron y cartografía OpenFreeMap/OpenMapTiles/OpenStreetMap, con atribución visible. La instancia pública OpenFreeMap no exige API key según su README oficial consultado el 15-10. No se crearon recursos AWS, claves ni suscripciones. CARTO directo se descartó: su README actual exige clave incluso para raster.

Fuentes primarias consultadas por HTTPS:
- https://github.com/hyperknot/openfreemap
- https://maplibre.org/maplibre-gl-js/docs/
- https://registry.npmjs.org/maplibre-gl/6.14.0
- https://project-osrm.org/docs/v5.24.0/api/#route-service
- https://github.com/CartoDB/basemap-styles

Esta combinación es un soporte para explorar la UI, no el proveedor definitivo del producto. Cuando llegue el motor se dibujará su propia geometría, sin reemplazarla por OSRM a posteriori.

## Revisión de la ronda

Capturas y evidencia en `qa/`. Las cuatro vistas se probaron a 1440, 900 y 390 px; la confirmación también incluye 319 px, el ancho observado del panel del usuario. Las galerías de logos tienen sus propias pruebas en `brand/qa/`. Las cifras y geometrías de demostración no son pruebas del solver.

Una revisión independiente identificó problemas concretos: contraste de algunas etiquetas funcionales, selección de otro vehículo desde un punto del mapa y reencuadre al reducir la ventana. Las correcciones y su valoración se conservan en `qa/independent-review.md` y la evidencia de confirmación.

El detector de impeccable se ejecutó una vez con parser degradado a regex; no calculó contraste. Sólo señaló guiones repetidos dentro de la hoja de QA de símbolos pequeños. No se usa ese resultado como certificación de accesibilidad.

Autoría de esta ronda: Astra creó Mapa de flota, Recorrido por paradas, módulos compartidos y comparativa; tres agentes Sol se encargaron de Despacho, Energía y las doce identidades. Otro Sol hizo la revisión independiente con contexto nuevo. No se atribuye esta ronda a Kiro: los intentos previos de creación extensa fallaron, como documenta `docs/KIRO-Y-AGENTES.md`.

**Cierre de revisión:** el revisor independiente marcó `ship` para presentar las propuestas, limitado a cinco correcciones verificadas: reencuadre, selección coherente, seis contrastes, paradas visibles sobre atribución y texto del vehículo sin superposición en 319 px. No certifica accesibilidad global ni motor. `qa/mobile-fixes.json` usa cajas de elemento para el dibujo/texto; el falso positivo desktop de Energía se aclara con `qa/car-text-bounds.json` (cajas del texto real, sin superposición). Las cancelaciones de teselas al mover cámara fueron `net::ERR_ABORTED`, no respuestas HTTP de error.
