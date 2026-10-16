# ZMD Mobility · Webapp

Interfaz HTML/CSS/JavaScript para planificar una flota eléctrica de reparto, desarrollada por ZMD Mobility. Tiene dos pantallas, Inicio y Plan, con cabecera y navegación compartidas. No requiere paquetes JavaScript ni compilación.

La rama `main` conecta la interfaz con el **motor nativo de Daniel (`ev_routing`)**
mediante el API 3.0. Desde la raíz del repositorio:

```sh
uv sync --locked --extra dw
AWS_PROFILE=hackathon uv run --locked --extra dw python -m backend.local_server --port 4294
```

Abrir `http://127.0.0.1:4294/` y elegir **Cargar y calcular**. El CSV se envía a
`/prepare` para que el backend construya la instancia; después se envía la
ProblemInstance 1.0/1.1 canónica a `/solve`. La selección **Calles del servidor** usa el GraphML indicado con `--graphml` y
preprocesamiento con expansión vial; la selección geodésica es sintética.
La UI no estima energía ni construye arcos. Configuración y comandos completos
en [la guía de integración](../docs/webapp-integration.md).

También se puede cargar directamente un **JSON nativo ProblemInstance 1.0/1.1**.
Sus arcos, parámetros, operaciones, compatibilidad de cargadores y procedencia
se conservan sin cambios. Los campos físicos se bloquean en el formulario;
se pueden modificar presupuesto, gap energético, política de búsqueda y semilla. Para cambiar la instancia,
editar el JSON y volver a cargarlo. Los formatos antiguos de preparación y
el API beta 2 no se admiten.

Para JSON elemental, la descarga de instancia conserva el JSON nativo. Para
preparación vial entrega la entrada de nodos y supuestos para reconstruirla
con el GraphML del servidor. La ejecución completa conserva ambos contratos. **Descargar
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

## Panel de cálculo y recuperación

**Instancia** permite seleccionar un archivo o crear un caso sintético con la cantidad
escogida de clientes y cargadores (hasta 200 ubicaciones en total). El signo `?`
explica el formato por mouse, teclado y toque. El caso sintético selecciona una red
por distancia; sus líneas discontinuas son aproximaciones, no calles.

**Cargar caso histórico** carga `competition_routing_nodes.csv` o
`evaluation_routing_nodes.csv` junto con `eVED_EV.csv` desde `data/` del servidor,
sin pedir una carga manual del histórico. Reutiliza el perfil cuando su contenido
ya está cargado. Conserva las coordenadas
de Ann Arbor, Michigan, incluido el depósito en 42.27708, −83.76281 en los archivos
actuales. Los CSV originales siguen fuera del directorio público. El mapa usa
esas ubicaciones y el mismo estilo cartográfico del ejemplo; no se traslada el caso
a Santiago. El selector no utiliza resultados de evaluación para calibrar.

**Simular una variante de este caso** mantiene el depósito y el histórico elegido,
y permite cambiar el número de clientes y cargadores. Si no hay un histórico
seleccionado, usa el eléctrico del servidor. Al reducir cantidades selecciona
ubicaciones originales; al aumentarlas incorpora intersecciones únicas conectadas
al depósito dentro del área de los clientes originales. La semilla permite repetir
la selección. Añadir ubicaciones requiere el GraphML local. Los cargadores nuevos
son supuestos explícitos: J1772/CHAdeMO, dos puertos y máximo nominal de 50 kW;
esa cifra no representa potencia efectiva. La simulación admite hasta 200 servicios.
Las rutas se calculan y validan por el mismo motor, y los resultados se identifican
como simulación sobre el caso histórico.

**Consumo con históricos** admite CSV eléctricos de hasta **4 GiB** y JSON de
hasta **256 MiB**. La carga transmite el archivo directamente a disco temporal;
el navegador no lo convierte a texto ni lo guarda en su almacenamiento.
Sin instancia, un histórico válido carga automáticamente el caso de la hackatón
seleccionado. Puedes ajustar vehículos, batería y reserva antes de calcular.
También puedes combinar el histórico con un CSV propio de ubicaciones. La
calibración usa calles con evidencia suficiente; el resto conserva el consumo
supuesto y la interfaz informa la cobertura. Los CSV de combustión e híbridos no
se convierten en mediciones eléctricas del Leaf.

Al cargar el caso se proponen capacidad útil de 24 kWh, reserva de 2,4 kWh y
consumo de respaldo de 0,2 kWh/km solo donde el formulario está vacío. Son
supuestos editables, no mediciones ni exigencias del desafío. Se conservan los
valores ya ingresados. El escenario oficial indica dos vehículos y SoC de 60 %.

**Flota y supuestos** reúne vehículos, batería, reserva, consumo, margen y red.
El margen aumenta el consumo previsto por calle, incluido el calibrado con el
histórico, sin aumentar ni eliminar la regeneración. Cero conserva la estimación;
el consumo en kWh/km sigue siendo el respaldo para calles sin evidencia suficiente.
El CSV solo
aporta lugares; sus supuestos se completan en el formulario. Un JSON nativo o una
exportación completa rellena los valores presentes y conserva la configuración
física del archivo. **Parámetros del motor** configura tiempo (1–120 s), gap de
energía (0,5 % inicial), búsqueda y semilla. La fase de entregas mantiene gap cero.
El servidor permite los CPU disponibles dentro del límite de SCIP, sin un control
de recursos en la interfaz; eso no fuerza uso paralelo en todas las etapas.

**Calcular rutas** permanece disponible para explicar los datos faltantes en línea;
solo se bloquea durante una petición en curso. No requiere un checkbox adicional.
Al terminar se abre el resultado y **Ver resultados** permite consultarlo de nuevo,
incluso después de navegar. Los parámetros y borradores se conservan por pestaña;
un límite de almacenamiento muestra una advertencia sin reemplazar el borrador.

Se admiten CSV de nodos con sus cuatro columnas obligatorias, instancias nativas,
entradas de preparación y ejecuciones exportadas. Si se elige eVED como instancia,
el encabezado permite dirigirlo al control **Adjuntar histórico**. Límite de importación
de instancias: 256 MiB; de petición de instancia:
64 MiB. El almacén temporal conserva hasta cuatro resultados y 256 MiB en total.
Estos límites de bytes no garantizan memoria ni tiempo para cualquier grafo.

Para consultar únicamente el ejemplo de diseño, desde la raíz:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory webapp
```

- Inicio: `http://127.0.0.1:4173/`
- Plan: `http://127.0.0.1:4173/plan.html`

Usa HTTP: los módulos JavaScript y el mapa no funcionan abriendo el HTML como archivo.

## Pantallas

**Inicio** resume el plan seleccionado en tres paneles: medidores de batería al regreso por vehículo (con una marca para la batería de salida), entregas asignadas por vehículo y consumo por vehículo, junto con paradas de recarga y estaciones del escenario. Cada local cuenta una sola vez aunque se visite varias veces. Un vehículo sin recorrido aparece como «Sin recorrido». Los vehículos, «Ver vehículos», «Ver paradas» y el enlace de estaciones abren el Plan en esa vista.

**Plan** muestra el mapa con los recorridos, la lista de vehículos y paradas, las estaciones de carga y el detalle de cada parada. Los números compactos identifican el mismo local en mapa y lista; no representan su posición en el recorrido. Las paradas usan referencias o nombres legibles (cliente, estación, salida y regreso); los identificadores originales se conservan en los datos y las exportaciones.

La pestaña **Cargadores** lista todas las estaciones de la instancia, usadas o
no, con sus metadatos y pasos por vehículo. Conserva estaciones sin coordenadas
y distingue cero de información ausente. No consulta disponibilidad en vivo.

**Ver resumen**, disponible en ambas pantallas, reúne la ejecución y permite
imprimirla o guardarla como PDF. Usa el mismo resultado del motor; al editar,
advierte que el resumen anterior ya no corresponde al borrador. El ejemplo de
diseño se identifica como ejemplo y no genera un resultado ficticio imprimible.

En **Cargar y calcular → Editar ubicaciones**, los CSV y el caso sintético
permiten modificar referencias y coordenadas, arrastrar el marcador o elegir
un punto. Confirmar exige nueva preparación y cálculo; cancelar conserva el
original. El formulario funciona sin cartografía. La búsqueda es entre puntos
cargados, sin geocodificación externa. Un JSON nativo con grafo conserva sus
ubicaciones protegidas hasta disponer de una red preparada para esos cambios.

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
- Perfil local genérico (FL), sin cuenta ni sesión remota. Su menú abre los Ajustes (tema, superficies sólidas, movimiento reducido y nombre de la organización) y «Cerrar plan», que borra la selección guardada y conserva los ajustes.
- El tema claro es el inicial si no hay preferencia guardada. El interruptor conserva la elección en `localStorage` y la aplica antes de pintar en Inicio, Plan y salida, también al recargar. Organización, superficies sólidas y movimiento reducido se guardan junto a esa preferencia.
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
- `location-editor.js`, `location-editor.css`, `shared/location-draft.js`: edición confirmada de ubicaciones, independiente del resultado.
- `plan-summary.js`, `plan-summary.css`, `shared/plan-summary-model.js`: resumen e impresión de la ejecución.
- `shared/charger-details.js`, `charger-details.css`: ficha y lista de cargadores con sus metadatos.
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

El [contexto maestro](../docs/ZMD-MASTER-CONTEXT.md) y el
[registro de orquestación](../docs/ZMD-ORCHESTRATION.md) identifican las bases,
responsabilidades, cambios revisados y evidencia de esta implementación.
