# Planificación de rutas y recargas para vehículos eléctricos

Proyecto para la hackatón AWS Breaking Barriers Chile 2026 y el desafío de CASE, Centro de Aceleración Sostenible de Electromovilidad de la FCFM de la Universidad de Chile.

Queremos ayudar a un operador a planificar entregas sin quedarse sin batería: cargar un archivo de nodos o configurar destinos, cargadores y flota desde una interfaz, obtener rutas factibles y consultar sus resultados en un mapa y un JSON.

El escenario del desafío considera dos Nissan Leaf 2013 con un 60 % de carga inicial. Las entradas actuales contienen un depósito, 20 locales y 60 cargadores. El mismo código deberá aceptar nuevas instancias y flotas parametrizadas.

**Estado de la rama `modelamiento`:** flujo CLI con maestro por rutas **sin H** y SCIP/PySCIPOpt, verificación independiente y JSON. La política adaptativa consulta Bedrock una vez antes de ambas fases. Pyomo/Gurobi/SCIP y GCG posicional se conservan como referencias explícitas. La UI queda pendiente.

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
  --output artifacts/toy_recharge.json
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

Para una primera ejecución en un portátil, incorporamos una **variante opcional
sobre las 81 ubicaciones de servicio**, conectadas mediante caminos viales
de mínima energía precalculados con Dijkstra de SciPy. Se adapta únicamente el
preprocesamiento de `codex/optimizacion-contraida`; el modelo de optimización
es nuestro maestro por rutas sin H. El solver recibe depósito,
clientes y cargadores, y la validación recupera las calles de cada conexión.
Conserva los dos vehículos y las restricciones de batería.
La optimalidad corresponde a los caminos fijos disponibles, sin límite de traslados.

```bash
# Solo si todavía no está preparada la instancia vial:
bash scripts/prepare_hackathon.sh config/default.json

# 120 segundos de presupuesto del solver; sin H:
bash scripts/run_pptx.sh 120
```

El JSON queda en `artifacts/hackathon/service-result.json` y el log en
`artifacts/hackathon/service-solve.log`. Cada resultado se expande y comprueba
calle por calle. Solo se admite energía no negativa; no se oculta regeneración
sumándola dentro de caminos. Ver [alcance, comandos y lectura del resultado](docs/service-graph.md),
incluida la distinción entre factibilidad física y cumplimiento del `H` vial original.

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
Los caminos permanecen fijos; las restricciones temporales no habilitan
automáticamente caminos alternativos más rápidos.

Para reutilizar caminos generados con esta versión, sin ejecutar Dijkstra:

```bash
HACKATHON_REUSE_SERVICE_GRAPH=1 \
  bash scripts/run_pptx.sh 60 none config/operations.example.json
```

Al actualizar desde contratos antiguos, regenerar una vez los artefactos:
las nuevas opciones forman parte del hash. Ver [todos los parámetros,
validaciones y comandos para conservar el baseline](docs/operations.md).

## Pruebas

```bash
uv run pytest -q
uv run pytest --cov=ev_routing --cov-report=term-missing \
  --junitxml=artifacts/tests/results.xml
uv run ruff check src tests
```

Las pruebas habituales no descargan mapas ni llaman a AWS. Incluyen integración energética, errores de datos, calles dirigidas, oráculos que enumeran recorridos pequeños, dos solvers, fallos de licencia, timeouts, manipulación de rutas para probar el validador y CLI completa. Los casos con solver se omiten si ninguno está disponible; revisar los `skipped` antes de interpretar una ejecución como validación del MILP. Para pruebas sin solver: `uv run pytest -m "not solver"`.

Resultados medidos y alcance de los ensayos: [docs/validation.md](docs/validation.md).

## Dantzig–Wolfe y LLM mediante AWS

`--solver scip-routes` utiliza un maestro por rutas sin H y pricing continuo.
El LLM toma una decisión estratégica antes de ambas fases: cortes compatibles,
lotes y branching. Los callbacks de pricing son locales. El motor conserva
control de los certificados y el checker valida toda la física.

```bash
uv sync --locked --extra dw
# Ejemplo probado con el perfil hackathon; se puede indicar otro modelo:
export BEDROCK_MODEL_ID='us.amazon.nova-micro-v1:0'
bash scripts/benchmark_dw.sh \
  --instance examples/toy_recharge.json \
  --bedrock-model "$BEDROCK_MODEL_ID" \
  --aws-region us-east-1 --aws-profile hackathon \
  --time-limit-seconds 60 --threads 1 --seeds 0 \
  --output-dir artifacts/benchmark-dw-toy
```

Ejecuta las tres políticas en procesos separados y genera `summary.csv`,
`summary.json`, manifiesto, resultados y logs. `us-east-1` y `hackathon` son
valores iniciales configurables; no se fija un modelo ni se guardan credenciales.
Ejecutar el `export` en la misma terminal antes del benchmark. También se puede
pasar el identificador directamente: `--bedrock-model us.amazon.nova-micro-v1:0`.
Para los servicios del concurso hay que añadir red original, archivo de caminos
y, opcionalmente, el arranque compartido.

Ver [comando completo, políticas, callbacks y límites](docs/dantzig-wolfe.md)
y [procedencia de la adaptación de LLM4MIP](docs/llm4mip-adaptation.md).
El adaptador Gurobi/SCIP y el antiguo `llm/tuning.py::propose_tuning` permanecen
sin llamadas a AWS.

Priorizamos código simple, modular y bibliotecas existentes. [STRUCTURE.md](STRUCTURE.md) explica brevemente cada archivo y sus funciones. Los equipos trabajan en ramas y worktrees separados; la integración objetivo del proyecto es `master`.

Documentos de referencia:

- [modelamiento.pdf](modelamiento.pdf): formulación matemática implementada.
- [data/presentation.pptx](data/presentation.pptx): enunciado, reglas y KPI de la hackatón, distribuido localmente.
- [diccionario.md](diccionario.md): diccionario de los históricos eVED.
- [AGENTS.md](AGENTS.md): arquitectura, contratos, reglas de implementación y trabajo en paralelo.
