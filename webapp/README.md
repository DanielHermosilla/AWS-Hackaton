# ZMD Mobility · Webapp

Interfaz estática para planificar una flota eléctrica de reparto, desarrollada por ZMD Mobility. Tiene dos pantallas, Inicio y Plan, con cabecera y navegación compartidas. No requiere instalar paquetes ni compilar.

Desde la raíz del repositorio:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory webapp
```

- Inicio: `http://127.0.0.1:4173/`
- Plan: `http://127.0.0.1:4173/plan.html`

Usa HTTP: los módulos JavaScript y el mapa no funcionan abriendo el HTML como archivo.

## Pantallas

**Inicio** resume el plan de ejemplo en tres paneles: medidores de batería al regreso por vehículo (con una marca para la batería de salida), entregas asignadas por vehículo y consumo por vehículo, junto con paradas de recarga y estaciones del escenario. Cada local cuenta una sola vez aunque se visite varias veces. Un vehículo sin recorrido aparece como «Sin recorrido». Los vehículos, «Ver vehículos», «Ver paradas» y el enlace de estaciones abren el Plan en esa vista.

**Plan** muestra el mapa con los recorridos, la lista de vehículos y paradas, las estaciones de carga y el detalle de cada parada. Los números compactos identifican el mismo local en mapa y lista; no representan su posición en el recorrido. El ID completo se conserva en la lista y en el nombre accesible del marcador.

## Controles compartidos

- Cabecera: nombre de la organización («Mi organización» por defecto), marca, botón de tema claro/oscuro y enlace al Plan. En Inicio ese enlace dice «Continuar plan» cuando hay una selección guardada.
- La etiqueta «Datos de ejemplo» abre el origen de los datos.
- Navegación Inicio/Plan en barra lateral; en móvil, en un cajón.
- Perfil local Diego Caballero (DC), sin cuenta ni sesión remota. Su menú abre los Ajustes (tema, superficies sólidas, movimiento reducido y nombre de la organización) y «Cerrar plan», que borra la selección guardada y conserva los ajustes.
- El tema es oscuro por defecto. Las preferencias se guardan en `localStorage` de este navegador, se aplican al instante y `theme.js` las aplica antes de pintar la página.
- La selección del Plan (vehículo, pestaña, parada y estaciones visibles) se guarda en `sessionStorage` de la pestaña y también se refleja en la URL del Plan.
- Se respetan el movimiento reducido del sistema y el del ajuste, el alto contraste y los colores forzados.

## Datos

- Un clon limpio usa `data/demo.synthetic.json`: puntos generados, líneas entre ellos y valores inventados. No son ubicaciones CASE ni rutas viales.
- Si existe `data/fixture.local.json`, se usa el ejemplo local preparado con las ubicaciones públicas de CASE y trazados OSRM sobre Ann Arbor. Este archivo es local e ignorado por Git. Su orden de visitas, consumo, recargas y baterías siguen siendo ilustrativos.
- Solo un **404** del archivo local activa el ejemplo sintético. Un JSON corrupto o cualquier otro error muestra un fallo de carga con opción de reintentar, sin sustituir los datos en silencio.
- La cartografía de fondo necesita internet para acceder a OpenFreeMap. La lista de paradas sigue disponible si falla el mapa. Abrir la webapp no consulta OSRM.

Las entregas son asignaciones del plan de ejemplo, no entregas completadas. Consumo, recarga y batería no son resultados del motor ni una validación energética, y la disponibilidad de estaciones no está verificada. No hay backend, autenticación, facturación, permisos, ejecución de solver, telemetría en vivo ni importador de CSV. El formato de los ejemplos es interno de diseño, no el contrato del motor.

## Código

- `index.html`, `home.js`, `home.css`: Inicio.
- `plan.html`, `plan.js`, `plan.css`, `map.js`: Plan.
- `boot.js`: crea la cabecera compartida una vez y carga el módulo de la página; muestra el error de carga si algo falla.
- `app-shell.js`, `app.css`, `material.css`: cabecera, navegación, perfil y diálogos.
- `state.js`: preferencias y selección del Plan. `home-navigation.js`: rutas a Inicio y Plan.
- `theme.js` (en `<head>`, antes de pintar) y `theme.css` (última hoja): tema global.
- `shared/`: estilos, iconos, movimiento, lectura y comprobación de la estructura de los ejemplos. Inicio y Plan comparten el recuento de locales únicos; los textos interpolados se escapan antes de renderizar.
- `salida.html`: confirmación después de cerrar el plan.

La identidad es **Batería en marcha**; sus SVG, favicons y estilos están en `assets/brand/`. La marca no representa el estado de batería.

## Dependencias y licencias

MapLibre GL JS 6.14.0 se distribuye en `vendor/maplibre/`, con su worker y licencia BSD. Motion 14.2.0 está en `vendor/motion/`, con licencia MIT, y anima el detalle del Plan; Inicio usa transiciones CSS. Las letras del logo Manrope están convertidas a curvas; se conserva su licencia SIL OFL en `assets/brand/licenses/Manrope-OFL.txt`. No se descargan bibliotecas ni fuentes de marca en ejecución.

El estilo cartográfico usa OpenFreeMap y datos de OpenStreetMap; se conserva la atribución del mapa. No se incluyen teselas, credenciales, datos originales de CASE ni cachés OSRM en el código publicable.

## Comprobación de datos

Con Node.js, desde la raíz:

```sh
node --test webapp/tests/fixture.test.mjs
```

Estas pruebas comprueban referencias, geometría y tipos usados por la interfaz; no certifican factibilidad energética ni resultados del solver.
