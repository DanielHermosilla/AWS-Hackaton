# Planificación de rutas y recargas para vehículos eléctricos

La rama `main` integra la webapp y el motor eléctrico con GPT por AWS Bedrock.
**Arranque local con interfaz:**

```bash
uv sync --locked --extra dw
AWS_PROFILE=hackathon uv run --locked --extra dw python -m backend.local_server \
  --port 4294 --graphml artifacts/network/competition_delivery.graphml \
  --network-profile delivery --tee
```

Abrir `http://127.0.0.1:4294/`, cargar el CSV y elegir **Calles del servidor**.
**Cargar caso histórico** incluye las ubicaciones de Ann Arbor y `eVED_EV.csv`
del servidor en un paso. **Simular una variante de este caso** permite reducir o
añadir clientes y cargadores sobre esas calles, conservando el histórico. Puedes
ajustar vehículos, batería, reserva y margen de consumo antes de calcular.
También puedes adjuntar solo un histórico: se cargan automáticamente las
ubicaciones del caso seleccionado. Los históricos CSV admiten hasta 4 GiB;
los JSON históricos, hasta 256 MiB. Se requiere evidencia EV para calibrar
consumo eléctrico por calle; combustión e híbridos no se usan como si fueran Leaf.
El comando local encuentra `competition_delivery.graphml` en `artifacts/network/`
automáticamente si no se indica otra ruta. El GraphML debe existir; sin él se admiten JSON elementales o preparación
sintética explícita. La UI permite GPT-5.6 Luna `low` o el mismo motor sin LLM.
Se mantiene gap energético de 0,5 %, con prueba y cota por fase.
[Guía completa de integración, preparación y credenciales](docs/webapp-integration.md).


Proyecto para la hackatón AWS Breaking Barriers Chile 2026 y el desafío de CASE, Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad de Chile.

Queremos ayudar a un operador a planificar entregas sin quedarse sin batería: cargar un archivo de nodos o configurar destinos, cargadores y flota desde una interfaz, obtener rutas factibles y consultar sus resultados en un mapa y un JSON.

El escenario del desafío considera dos Nissan Leaf 2013 con un 60 % de carga inicial. Las entradas actuales contienen un depósito, 20 locales y 60 cargadores. El mismo código deberá aceptar nuevas instancias y flotas parametrizadas.

**Estado integrado:** webapp conectada al maestro por rutas **sin H**, pricing por coste reducido, ALNS, búsqueda memética y sub-SCIP de recombinación. Bedrock coordina políticas mediante inferencia asíncrona. Se conservan validación independiente y las referencias Pyomo/Gurobi/SCIP y GCG. El refinamiento local del panel, archivos y resultados está documentado en [la entrega de integración](docs/implementation/ZMD-FULL-INTEGRATION.md).

## Nuestro modelamiento

**La formulación está en [modelamiento.pdf](modelamiento.pdf).** Las ecuaciones (25)–(29) describen el maestro vigente sin H; (1)–(24) documentan la referencia Pyomo. Ambos conservan calles, servicio y recursos físicos. [docs/dantzig-wolfe.md](docs/dantzig-wolfe.md) explica la equivalencia y los límites de los certificados.

Su objetivo es lexicográfico:

$$
\text{lexmin}\left(-\sum_{i\in C}y_i,\ E_{\mathrm{total}}\right).
$$

Primero se maximiza el número de entregas factibles. Después se minimiza el consumo neto efectivo de batería manteniendo ese cumplimiento. El tiempo de cómputo se mide como rendimiento del método.

El modelo:

- Exige salida y regreso al depósito, continuidad del recorrido y batería dentro de su capacidad y reserva.
- Permite repetir calles, intersecciones y cargadores, pero atender cada cliente como máximo una vez. Pasar por un cliente no implica realizar su entrega.
- Decide recargas parciales en estaciones compatibles y representa la regeneración, incluyendo la energía que no puede almacenarse cuando la batería está llena.
- El backend predeterminado `scip-routes` no usa H ni limita visitas a cargadores. El H de snapshots antiguos solo afecta a los backends posicionales heredados.
- Supone consumos deterministas y tramos viales elementales. La versión base no incluye carga en el depósito, jornada, tiempos de servicio, capacidad de paquetes ni colas.

Los nodos de los CSV no constituyen por sí solos la red de calles. El comando `prepare` utiliza un GraphML de OSMnx o descarga una red dirigida sin simplificar, solo cuando se solicita. Integra eVED con intervalos reales por vehículo/viaje y obtiene una referencia descriptiva de kWh/km. Este estimador inicial **no es un predictor validado del consumo futuro** y no produce regeneración en los arcos OSM; el modelo sí admite consumos firmados y saturación en instancias JSON.

## Ejecutar

Requiere Python 3.12 o 3.13 y `uv`. Las dependencias Python, incluida la interfaz Gurobi, están fijadas en `uv.lock`. La licencia Gurobi se configura fuera del repositorio. Para el respaldo, instalar el ejecutable SCIP con soporte de lectura `.nl` y dejarlo en `PATH`; instalar únicamente un paquete Python de SCIP no satisface esa integración.

```bash
uv sync --locked
uv run ev-routing run \
  --instance examples/toy_recharge.json \
  --time-limit-seconds 30 \
  --output artifacts/toy-result.json

uv run --locked --extra dw python -m pytest -q
node --test webapp/tests/*.test.mjs
```

El ejemplo requiere dos entregas y una recarga: el óptimo consume 14 kWh netos e incorpora 9 kWh a la batería. `examples/toy_regeneration.json` tiene una entrega y óptimo de 2 kWh; comprueba que la regeneración excedente se pierde cuando la batería se llena. Son ejemplos sintéticos, no resultados del concurso.

Para fijar un backend, agregar `--solver gurobi` o `--solver scip`. El valor predeterminado `auto` habilita el respaldo. No se cambia de solver por timeout o infactibilidad. `--time-limit-seconds 60` limita el presupuesto compartido por las dos fases; es un límite blando. Los detalles de licencias, fases y certificados están en [docs/solvers.md](docs/solvers.md).

Preparar los datos locales, conservando los originales:

```bash
uv run ev-routing prepare \
  --nodes data/competition_routing_nodes.csv \
  --graphml artifacts/network/competition_delivery.graphml \
  --download-network \
  --network-profile delivery \
  --eved data/eVED_EV.csv \
  --energy-cache artifacts/energy/eved-summary.json \
  --config config/default.json \
  --output artifacts/instances/competition.json
```

Si el GraphML ya existe, se reutiliza sin descargar ni reemplazarlo. Omitir `--download-network` exige una red local. `--energy-rate 0.16` permite usar un coeficiente explícitamente supuesto en lugar de `--eved`. `--visit-id ID`, repetible, y `--charger-id ID` o `--no-chargers` permiten ensayos con subconjuntos; esa selección queda registrada.

Para las ubicaciones de la hackatón usamos `--network-profile delivery`: incluye
calles de servicio y pasillos de estacionamiento, conservando los sentidos de
circulación y excluyendo etiquetas de acceso privado/prohibido y de emergencias.
El perfil `drive` original omitía accesos necesarios y dejaba siete puntos fuera
del umbral de 100 m. No reutilizar `competition_full.graphml` como si tuviera el
nuevo perfil: la caché y el filtro quedan identificados y se valida su coincidencia.
La proximidad a la red sigue siendo un supuesto de acceso, no una verificación
de barreras, permisos condicionales ni cierres actuales.

Para preparar con logs y errores visibles, ejecutar
`bash scripts/prepare_hackathon.sh config/default.json`.
El script solo prepara: revisar el tamaño antes de lanzar el MILP.
Ejecutar los scripts mediante `bash archivo.sh`, no pegando su contenido ni con
`source`: `set -e` dentro de una shell interactiva puede terminarla ante un error.
Si falla la validación de accesos, revisar la ubicación y su conexión vial;
ampliar `MAX_SNAP_DISTANCE_M` admite accesos supuestos más largos y cambia ese
supuesto del problema.

**Antes de interpretar una corrida real**, revisar `config/default.json`: 24 kWh útiles y reserva de 2.4 kWh son supuestos de ejemplo, no requisitos acreditados por la hackatón. `movement_limit` es heredado y no restringe `scip-routes`. El grafo conserva intersecciones y tramos, y añade accesos cortos a servicios bajo un supuesto registrado. El importador rechaza accesos mayores que `--max-snap-distance-m` (100 m por defecto) y registra servicios sin retorno vial.

`run` utiliza los parámetros físicos guardados en la instancia; de `--config` solo toma la sección `solver`. Así no cambia el problema después de prepararlo. La salida incluye rutas completas, energía, recargas, entregas pendientes, cotas/gaps por fase, tiempos, procedencia y comprobación de factibilidad. Sin referencia de comparación, los ahorros de tiempo y CO2e quedan en `null`.

### Probar los 20 locales y 60 cargadores completos

La preparación conserva todas las ubicaciones de servicio. Usa **Dijkstra**
cuando las energías son no negativas y no hay plazos; con regeneración o
restricciones temporales construye **perfiles de batería y alternativas**,
conservando las intersecciones que no convenga comprimir.
Nuestro maestro por rutas sin H y el pricing de SCIP eligen entre esas
conexiones. Se conservan los dos vehículos y la física de batería.
La preparación preserva el óptimo vial bajo las hipótesis verificadas;
probarlo sigue requiriendo completar la resolución de ambas fases.

```bash
# Solo si todavía no está preparada la instancia vial:
bash scripts/prepare_hackathon.sh config/default.json

# 120 segundos de presupuesto del solver; sin H:
bash scripts/run_pptx.sh 120
```

El JSON queda en `artifacts/hackathon/service-result.json` y el log en
`artifacts/hackathon/service-solve.log`. Cada resultado se expande y comprueba
calle por calle. Los perfiles representan déficits intermedios, saturación y
tiempos; no sustituyen esas condiciones por una suma energética.
Ver [preprocesamiento, caché y garantías](docs/resource-paths.md) y
[referencia de Dijkstra y ensayos anteriores](docs/service-graph.md).

Si se verifica que una ruta completa cabe en la batería inicial y la matriz
es métrica no negativa sin restricciones temporales, se aplica una reducción
exacta a tour con cortes DFJ. Los demás casos usan pricing con recursos continuos.
Ver [formulación y certificados](docs/dantzig-wolfe.md). El análisis de
[H y arranques posicionales](docs/heuristics.md) es una referencia heredada.

### Supuestos operacionales opcionales

El PDF actualizado conserva la base y añade las ecuaciones (17)–(24).
`operations` permite configurar duración de entregas, jornada, tiempo y
eficiencia de recarga, reserva al regresar, margen energético, cargadores
deshabilitados y ventanas horarias. Sus valores neutros conservan la base.
La fuente editable es [modelamiento.tex](modelamiento.tex).

Con la red vial ya preparada:

```bash
  bash scripts/run_pptx.sh 60 none config/operations.example.json
```

Los parámetros del ejemplo son **supuestos ilustrativos**: 5 minutos por
entrega, jornada de 4 horas, velocidad constante de 30 km/h donde falta tiempo,
potencia efectiva de 3 kW, eficiencia 90 %, reserva final 15 % y margen de
consumo 10 %. No provienen del PPTX ni acreditan características de los cargadores.
Las ventanas quedan desactivadas hasta introducir horarios del cliente.

La jornada y reserva final adicional se representan en las rutas factibles,
sin elegir H. Pueden impedir la reducción a un solo tour y requerir pricing.
El escenario se aplica antes de preparar: con plazos se conservan alternativas
temporales. El pricing decide servicios, espera y recarga continua.

Para reutilizar caminos del **mismo escenario**, sin recalcularlos:

```bash
HACKATHON_REUSE_SERVICE_GRAPH=1 \
  bash scripts/run_pptx.sh 60 none config/operations.example.json
```

Para cambiar de escenario con regeneración o tiempos, regenerar los perfiles.
El comando `service-graph --cache-directory DIR` reutiliza preparaciones por
contenido y configuración. Los snapshots 1.0 y sus hashes siguen admitidos;
los perfiles usan la versión 1.1. Ver [todos los parámetros,
validaciones y comandos para conservar el baseline](docs/operations.md).

## Pruebas

```bash
uv run --locked --extra dw python -m pytest -q
uv run --locked --extra dw python -m pytest --cov=ev_routing --cov-report=term-missing \
  --junitxml=artifacts/tests/results.xml
uv run ruff check src tests
```

Las pruebas habituales no descargan mapas ni llaman a AWS. Incluyen integración energética, errores de datos, calles dirigidas, oráculos que enumeran recorridos pequeños, dos solvers, fallos de licencia, timeouts, manipulación de rutas para probar el validador y CLI completa. Los casos con solver se omiten si ninguno está disponible; revisar los `skipped` antes de interpretar una ejecución como validación del MILP. Para pruebas sin solver: `uv run pytest -m "not solver"`.

Resultados medidos y alcance de los ensayos: [docs/validation.md](docs/validation.md).

## Dantzig–Wolfe y LLM mediante AWS

`--solver scip-routes` utiliza un maestro por rutas sin H y pricing continuo.
El LLM decide antes de buscar y a partir de eventos del árbol, LP, pricing,
incumbentes y heurísticas. Controla opciones de algoritmo y
un catálogo de parámetros nativos verificados. El presupuesto predeterminado
es de hasta cuatro llamadas y un 25 % del tiempo global para inferencia.
Los callbacks ejecutan la política local mientras la inferencia avanza en otro
hilo. El motor conserva control de los certificados y el checker valida la física.
Ver [implementación, API de SCIP, mediciones y límites](docs/llm-head-search.md).
La fase energética se detiene al alcanzar un gap global de **0,5 %**
(`--energy-relative-gap 0.005`); las entregas mantienen su prioridad.
El modelo predeterminado de la CLI es **GPT-5.6 Luna**, con razonamiento `low`.
Se verificó una respuesta real con `hackathon`/`us-east-1` en 4,76 s,
aplicada durante la búsqueda a los 5,06 s.
GPT-6 Luna queda fuera de la lista de modelos permitidos de ese perfil.
Ante errores de AWS se registra fallback y continúa la política local.
La [guía de conexión con webapp](docs/webapp-integration.md) explica arquitectura,
autenticación, resultados y conexión HTTP ya integrada en `main`.
La mejora histórica de 2/40 a 40/40 corresponde al motor anterior; no acredita
una mejora adicional de esta rama ni del LLM.

Para resolver una instancia preparada con control asíncrono:

```bash
uv run --locked --extra dw ev-routing run --instance artifacts/service-instance.json \
  --road-instance artifacts/instance.json --path-archive artifacts/service-paths.json \
  --solver scip-routes --search-policy adaptive --time-limit-seconds 120 \
  --energy-relative-gap 0.005 \
  --bedrock-model us.openai.gpt-5.6-luna \
  --llm-timeout-seconds 8 \
  --llm-reasoning-effort low --llm-max-output-tokens 2048 \
  --llm-instance-context-bytes 8000 \
  --llm-max-calls 2 --llm-time-fraction .5 --decision-interval-seconds 15 \
  --solver-log-directory artifacts/solve/native --output artifacts/solve/result.json
```

Los modelos y presupuestos son configurables. `--llm-instance-context-bytes`
controla cuánto grafo se envía; todo recorte se declara. El grafo completo, el
catálogo de SCIP y los maestros `.mps` se exportan al directorio de logs.
Un `.mps` restringido no contiene la familia implícita de rutas futuras.

```bash
uv sync --locked --extra dw
# Modelo probado con el perfil hackathon:
export BEDROCK_MODEL_ID='us.openai.gpt-5.6-luna'
bash scripts/benchmark_dw.sh \
  --instance examples/toy_recharge.json \
  --bedrock-model "$BEDROCK_MODEL_ID" \
  --aws-region us-east-1 --aws-profile hackathon \
  --llm-reasoning-effort low --llm-max-output-tokens 2048 \
  --llm-max-calls 3 --llm-timeout-seconds 25 --llm-time-fraction .5 \
  --time-limit-seconds 120 --threads 1 --seeds 0 \
  --output-dir artifacts/benchmark-dw-toy
```

Ejecuta las tres políticas en procesos separados y genera `summary.csv`,
`summary.json`, manifiesto, resultados y logs. `us-east-1` y `hackathon` son
valores iniciales configurables; no se guardan credenciales.
Ejecutar el `export` en la misma terminal antes del benchmark. También se puede
pasar el identificador directamente: `--bedrock-model us.openai.gpt-5.6-luna`.
Para los servicios del concurso hay que añadir red original, archivo de caminos
y, opcionalmente, el arranque compartido.

Ver [comando completo, políticas, callbacks y límites](docs/dantzig-wolfe.md)
y [procedencia de la adaptación de LLM4MIP](docs/llm4mip-adaptation.md).
El adaptador Gurobi/SCIP y el antiguo `llm/tuning.py::propose_tuning` permanecen
sin llamadas a AWS.

### Ensayo visible con clientes y 60 estaciones

Con los archivos de `artifacts/hackathon/` ya preparados:

```bash
bash scripts/test_clients.sh \
  --energy-relative-gap 0.005 --bedrock-model us.openai.gpt-5.6-luna \
  --llm-reasoning-effort low --llm-max-output-tokens 2048 \
  --llm-max-calls 2 --llm-timeout-seconds 8 --llm-time-fraction .5 \
  --time-limit-seconds 120 --threads 1 --seed 0
```

La instancia predeterminada contiene **20 clientes y 60 estaciones**.
El script usa `scip-routes`, sin H, y comprueba que se conservan 60 estaciones.
`scripts/test_20_clients.sh` sigue disponible como alias.
Muestra los logs de SCIP, las respuestas finales del LLM al recibirlas y,
por separado, la aceptación/rechazo, cambios antes/después y campos inactivos.
Cada solicitud y respuesta se conserva en `logs/decisions/`.
El máximo predeterminado es de cuatro llamadas Bedrock; se controla con
`--llm-max-calls`, `--llm-time-fraction` y `--llm-timeout-seconds`.
Región/perfil iniciales: `us-east-1`/`hackathon`; se pueden cambiar con
`--aws-region`/`--aws-profile`. El modelo también admite `BEDROCK_MODEL_ID`.

Cada ejecución crea un directorio nuevo en `artifacts/test-20c-60s/`, o el
directorio vacío indicado mediante `--output-dir`. Conserva:

- `run.log`: salida íntegra de SCIP, respuestas y decisiones mostradas.
- `logs/*.scip.log`: logs nativos por fase y etapa.
- `logs/decisions/NN/llm-request.json`: cuerpo exacto de Converse.
- `logs/decisions/NN/llm-response.json`: respuesta y tokens, incluso si
  el JSON fue rechazado.
- `logs/llm-decision.json`: propuesta, configuración anterior, cambios efectivos,
  parámetros no aplicables al algoritmo elegido y estado de aceptación/fallback.
- `result.json` y `run-config.json`: solución, auditoría vial, configuración y hashes.

Aceptar una propuesta no implica cambiar parámetros: se indica explícitamente
cuando coincide con la configuración previa. Las opciones ajenas al algoritmo
elegido no se presentan como cambios aplicados. Si la cota de entregas se obtiene
por un testigo completo, solo la fase energética necesita un log nativo SCIP.
Los logs se muestran sin resumir para conservar la evidencia exacta.
`--search-policy standard` permite la misma corrida sin AWS.
`--help` muestra las opciones para otras rutas de archivos y arranque opcional.

Para simular **40 clientes totales** (los 20 originales más 20 sintéticos):

```bash
bash scripts/test_clients.sh \
  --simulate-customers 40 --simulation-seed 0 \
  --energy-relative-gap 0.005 --bedrock-model us.openai.gpt-5.6-luna \
  --aws-region us-east-1 --aws-profile hackathon \
  --llm-reasoning-effort low --llm-max-output-tokens 2048 \
  --llm-max-calls 2 --llm-timeout-seconds 8 --llm-time-fraction .5 \
  --time-limit-seconds 120 --threads 1 --seed 0
```

`--simulate-customers N` admite otros totales mayores que la demanda de la red
fuente. Selecciona nodos viales existentes sin reemplazo, dentro del rectángulo
geográfico de los clientes originales y con conexión dirigida de ida y vuelta
al depósito. El muestreo es uniforme por nodo elegible: **no representa domicilios
ni una distribución observada de demanda**. Los originales y los 60 cargadores
se conservan, al igual que calles, energías, flota y batería. Los nuevos clientes
usan el tiempo de servicio común y no reciben ventanas inventadas.

### Desde archivos originales locales, con SCIP y LLM en vivo

Usar un directorio nuevo evita reutilizar instancias, energía integrada y caminos.
El GraphML es la descarga vial original; esta variante no vuelve a consultar OSM.
Las rutas absolutas siguientes corresponden a los datos de este equipo:

```bash
EVRP_DATA=/Users/daniel/AWS-Amazon
EVRP_RUN="$PWD/artifacts/desde-cero-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$EVRP_RUN"

uv run --locked --extra dw ev-routing prepare \
  --nodes "$EVRP_DATA/data/competition_routing_nodes.csv" \
  --graphml "$EVRP_DATA/artifacts/network/competition_delivery.graphml" \
  --network-profile delivery --eved "$EVRP_DATA/data/eVED_EV.csv" \
  --energy-cache "$EVRP_RUN/eved-summary.json" --config config/default.json \
  --output "$EVRP_RUN/instance.json"

bash scripts/test_clients.sh \
  --road-instance "$EVRP_RUN/instance.json" \
  --simulate-customers 40 --simulation-seed 0 \
  --search-policy adaptive --time-limit-seconds 120 \
  --energy-relative-gap 0.005 --bedrock-model us.openai.gpt-5.6-luna \
  --llm-reasoning-effort low --llm-max-output-tokens 2048 \
  --llm-timeout-seconds 8 \
  --llm-instance-context-bytes 8000 --llm-max-calls 2 \
  --llm-time-fraction .5 --decision-interval-seconds 15 \
  --aws-profile hackathon --aws-region us-east-1 \
  --output-dir "$EVRP_RUN/run"
```

El script activa `--tee --show-llm-trace` y conserva la salida completa.
No pasar estos logs por `distill`: se necesita salida exacta para inspeccionarlos.
Para incluir una descarga nueva, cambiar `--graphml` por
`"$EVRP_RUN/network.graphml"` y agregar `--download-network` al comando `prepare`.
La latencia de OSM es adicional y no se ha medido en este ensayo.

Medición histórica del 15 de octubre de 2026, anterior a la parada en 0,5 %:
CSV + eVED sin caché + GraphML local hasta
instancia vial, **16,318 s**; simulación a 40 clientes y preparación de caminos,
**9,448 s**; SCIP estándar con presupuesto de 15 s, **15,001 s**. Incluyendo
procesos, hashes, lectura/escritura y validación vial, **45,329 s** en total.
Resultado: 40/40, 14,56660712 kWh, gap energético final 0,2838 %.
Es el tiempo de una corrida completa, no el primer instante de ese gap.
La estimación anterior de aproximadamente **150 s** correspondía a buscar
cierre exacto con presupuesto adaptativo de 120 s, no al nuevo criterio de 0,5 %.
No se ha repetido aquí toda la preparación desde cero con la nueva configuración.
Evidencia local: `artifacts/llm-head/cold-local-20261015/`.

La semilla de ubicaciones (`--simulation-seed`) es independiente de la semilla
del solver (`--seed`). La misma red, total y semilla generan los mismos clientes.
El preprocesamiento prepara caminos para los nuevos servicios, sin descargar
mapas, y escribe copias en `artifacts/test-40c-60s/<ejecución>/` (o el total elegido):
`instance.json`, `service-instance.json`, `service-paths.json` y `simulation.json`,
además de los logs y resultados anteriores. El informe de simulación identifica
los clientes añadidos, semilla, área, candidatos y hash de la red fuente.

La preparación y escritura tienen su propio tiempo en `run-config.json`; el
presupuesto de resolución se aplica después. Tener conexión vial no garantiza
que puedan atenderse todos con la batería disponible; se informa el cumplimiento
y la prueba de optimalidad que alcance el solver. Para resolver de nuevo sin
simular ni preparar caminos, omitir `--simulate-customers` y pasar esos tres
snapshots mediante `--road-instance`, `--instance` y `--path-archive`.
No combinar la simulación con un arranque de la instancia original.

Priorizamos código simple, modular y bibliotecas existentes. [STRUCTURE.md](STRUCTURE.md) explica brevemente cada archivo y sus funciones. Los equipos trabajan en ramas y worktrees separados; la integración vigente conserva `main` y la historia de sus ramas.

Documentos de referencia:

- [modelamiento.pdf](modelamiento.pdf): formulación matemática implementada.
- [data/presentation.pptx](data/presentation.pptx): enunciado, reglas y KPI de la hackatón, distribuido localmente.
- [diccionario.md](diccionario.md): diccionario de los históricos eVED.
- [AGENTS.md](AGENTS.md): arquitectura, contratos, reglas de implementación y trabajo en paralelo.
