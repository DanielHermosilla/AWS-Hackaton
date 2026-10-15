# ZMD Mobility · Webapp

Interfaz HTML/CSS/JavaScript para planificar una flota eléctrica de reparto, desarrollada por ZMD Mobility. Tiene dos pantallas, Inicio y Plan, con cabecera y navegación compartidas. No requiere paquetes JavaScript ni compilación.

Esta rama conecta la interfaz con el **motor nativo de Daniel (`ev_routing`)**
mediante el API 3.0. Desde la raíz del repositorio:

```sh
uv sync --locked
uv run --locked python -m backend.local_server --port 4294
```

Abrir `http://127.0.0.1:4294/` y elegir **Cargar y calcular**. El CSV se envía a
`/prepare` para que el backend construya la instancia; después se envía la
ProblemInstance 1.0 canónica a `/solve`. La preparación por distancia es una
aproximación no vial explícita. La UI no estima energía ni construye arcos.

También se puede cargar directamente un **JSON nativo ProblemInstance 1.0**.
Sus arcos, parámetros, operaciones, compatibilidad de cargadores y procedencia
se conservan sin cambios. Los campos físicos se bloquean en el formulario;
solo se puede modificar el presupuesto del solver. Para cambiar la instancia,
editar el JSON y volver a cargarlo. Los formatos antiguos de preparación y
el API beta 2 no se admiten.

La descarga de instancia entrega un JSON nativo reutilizable. **Descargar
ejecución completa** conserva el envoltorio API 3.0 y los objetos originales del
motor. **Descargar resultado nativo** entrega directamente el `RunResult` 1.0
íntegro de Daniel, incluidos los campos que la UI no representa. Ese resultado
no contiene los nodos y arcos: para recalcular se necesita la instancia o la
descarga de ejecución completa.
Los nodos nativos sin coordenadas permanecen en la lista: no se generan
ubicaciones ni trazados ficticios. Un resultado sin solución mantiene métricas
desconocidas y sus fases, sin convertirlo en cero entregas o infactibilidad
probada. El servidor temporal conserva hasta cuatro resultados y estos expiran
al reiniciarlo. Ver [el contrato y sus límites](../docs/integration-beta.md).

Para consultar únicamente el ejemplo de diseño, desde la raíz:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory webapp
```

- Inicio: `http://127.0.0.1:4173/`
- Plan: `http://127.0.0.1:4173/plan.html`

Usa HTTP: los módulos JavaScript y el mapa no funcionan abriendo el HTML como archivo.

## Pantallas

**Inicio** resume el plan de ejemplo en tres paneles: medidores de batería al regreso por vehículo (con una marca para la batería de salida), entregas asignadas por vehículo y consumo por vehículo, junto con paradas de recarga y estaciones del escenario. Cada local cuenta una sola vez aunque se visite varias veces. Un vehículo sin recorrido aparece como «Sin recorrido». Los vehículos, «Ver vehículos», «Ver paradas» y el enlace de estaciones abren el Plan en esa vista.

**Plan** muestra el mapa con los recorridos, la lista de vehículos y paradas, las estaciones de carga y el detalle de cada parada. Los números compactos identifican el mismo local en mapa y lista; no representan su posición en el recorrido. El ID completo se conserva en la lista y en el nombre accesible del marcador.

En modo motor, **Datos y límites de la ejecución** presenta sus KPIs, motivos de
datos no disponibles, operaciones, comprobaciones, fases, tiempos y trazabilidad.
Las paradas muestran energía prevista/efectiva hacia el siguiente nodo y tiempos
desde `t=0` cuando el motor los informa. El conteo global de recargas usa
`kpis.charging_stops`; no se infiere un contador por vehículo. Los totales de Plan
siguen visibles aunque no haya coordenadas. Los tiempos operacionales y de
cómputo se presentan por separado, sin sumar intervalos contenidos.

## Controles compartidos

- Cabecera: nombre de la organización («Mi organización» por defecto), marca, botón de tema claro/oscuro y enlace al Plan. En Inicio ese enlace dice «Continuar plan» cuando hay una selección guardada.
- La etiqueta «Datos de ejemplo» abre el origen de los datos.
- Navegación Inicio/Plan en barra lateral; en móvil, en un cajón.
- Perfil local Diego Caballero (DC), sin cuenta ni sesión remota. Su menú abre los Ajustes (tema, superficies sólidas, movimiento reducido y nombre de la organización) y «Cerrar plan», que borra la selección guardada y conserva los ajustes.
- Cada documento inicia en tema claro, también al recargar o navegar entre Inicio y Plan, aunque el sistema o una preferencia antigua indiquen oscuro. El interruptor permite cambiar el tema durante la página abierta; esa elección queda solo en memoria. El nombre de organización, las superficies sólidas y el movimiento reducido siguen guardándose en `localStorage`. El HTML y `theme.js` establecen el tema claro antes de pintar.
- La selección del Plan (vehículo, pestaña, parada y estaciones visibles) se guarda en `sessionStorage` de la pestaña y también se refleja en la URL del Plan.
- Se respetan el movimiento reducido del sistema y el del ajuste, el alto contraste y los colores forzados.

## Datos

- Un clon limpio usa `data/demo.synthetic.json`: puntos generados, líneas entre ellos y valores inventados. No son ubicaciones CASE ni rutas viales.
- Si existe `data/fixture.local.json`, se usa el ejemplo local preparado con las ubicaciones públicas de CASE y trazados OSRM sobre Ann Arbor. Este archivo es local e ignorado por Git. Su orden de visitas, consumo, recargas y baterías siguen siendo ilustrativos.
- Solo un **404** del archivo local activa el ejemplo sintético. Un JSON corrupto o cualquier otro error muestra un fallo de carga con opción de reintentar, sin sustituir los datos en silencio.
- La cartografía de fondo necesita internet para acceder a OpenFreeMap. La lista de paradas sigue disponible si falla el mapa. Abrir la webapp no consulta OSRM.

En modo ejemplo, las entregas, consumo, recarga y batería siguen siendo ilustrativos.
En modo motor, se presenta el resultado nativo identificado de Daniel con su alcance de
validación, servicio explícito y supuestos. Editar marca el resultado anterior;
un fallo nunca activa el ejemplo como reemplazo. «Dejar de esperar» no cancela el
solver. No hay autenticación, facturación, permisos ni telemetría en vivo.
El formato del ejemplo continúa separado del contrato HTTP beta.

## Código

- `index.html`, `home.js`, `home.css`: Inicio.
- `plan.html`, `plan.js`, `plan.css`, `map.js`: Plan.
- `boot.js`: crea la cabecera compartida una vez y carga el módulo de la página; muestra el error de carga si algo falla.
- `app-shell.js`, `app.css`, `material.css`: cabecera, navegación, perfil y diálogos.
- `state.js`: preferencias y selección del Plan. `home-navigation.js`: rutas a Inicio y Plan.
- `theme.js` (en `<head>`, antes de pintar) y `theme.css` (última hoja): tema global.
- `shared/`: estilos, iconos, movimiento, lectura y comprobación de la estructura de los ejemplos. Inicio y Plan comparten el recuento de locales únicos; los textos interpolados se escapan antes de renderizar.
- `run-panel.js`, `run-panel.css`: carga, revisión, estado y descarga de ejecuciones.
- `shared/solver-input.js`, `solver-client.js`, `solver-adapter.js`: entrada, transporte y presentación versionada del motor; pruebas en `tests/`.
- `salida.html`: confirmación después de cerrar el plan.

La identidad es **Batería en marcha**; sus SVG, favicons y estilos están en `assets/brand/`. La marca no representa el estado de batería.

## Dependencias y licencias

MapLibre GL JS 6.14.0 se distribuye en `vendor/maplibre/`, con su worker y licencia BSD. Motion 14.2.0 está en `vendor/motion/`, con licencia MIT, y anima el detalle del Plan; Inicio usa transiciones CSS. Las letras del logo Manrope están convertidas a curvas; se conserva su licencia SIL OFL en `assets/brand/licenses/Manrope-OFL.txt`. No se descargan bibliotecas ni fuentes de marca en ejecución.

El estilo cartográfico usa OpenFreeMap y datos de OpenStreetMap; se conserva la atribución del mapa. No se incluyen teselas, credenciales, datos originales de CASE ni cachés OSRM en el código publicable.

## Comprobación de datos

Con Node.js, desde la raíz:

```sh
node --test webapp/tests/*.test.mjs
```

Estas pruebas comprueban referencias, unidades, estados y tipos usados por la
interfaz; no certifican factibilidad energética. La guía beta incluye las pruebas
Python con HTTP y el solver nativo; cada evidencia declara su alcance.
