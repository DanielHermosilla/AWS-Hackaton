# Ejecutar todas las ubicaciones del PPTX

**Flujo vigente:** `service-graph` prepara por defecto con
`--service-movements none`; `run` usa `scip-routes`, sin elegir H.
Los caminos, hashes y auditoría vial descritos aquí se mantienen.
Las descripciones de H y ensayos posicionales siguientes son la referencia
anterior. Ver [maestro sin H y resultados actuales](dantzig-wolfe.md).

La instancia de competición tiene un depósito, 20 locales y 60 cargadores,
con dos vehículos. Esas **81 ubicaciones** se conservan completas.
El CSV no incluye las calles entre ellas: la preparación local con OSM produjo
106.746 nodos y 211.725 arcos. Con `H=200` calles por vehículo, la plantilla
del PDF generaría 127.610.712 binarias. No es una ejecución apropiada para
probar rápidamente en un portátil.

## Variante explícita entre servicios

`ev-routing service-graph` conserva cada ubicación de servicio y calcula,
para cada par ordenado alcanzable, un camino de energía mínima sobre la
red vial dirigida. Usa `scipy.sparse.csgraph.dijkstra` sobre una matriz dispersa
CSR, con `energy_kwh` como peso. Ejecuta una búsqueda por depósito, cliente o
cargador, nunca una búsqueda por cada esquina. Los servicios aislados
permanecen en la instancia; no se inventa conectividad. Los caminos quedan
en un archivo separado vinculado a los snapshots mediante SHA-256.

El solver recibe solamente depósito, clientes y cargadores. Cada arco representa
un camino vial completo y conserva la suma de su energía y distancia; las esquinas
quedan en el archivo de caminos para expandir y comprobar la solución.
La matriz conserva explícitamente las calles de energía cero. Los predecesores
se calculan para un origen por vez, de modo que no se almacena una matriz
`número_de_servicios × número_de_nodos_viales` ni todos los caminos a las esquinas.
La distancia acumulada se informa, pero no se utiliza como peso de Dijkstra.

La misma plantilla Pyomo recibe este grafo, pero **su interpretación cambia**:

- `H` cuenta traslados entre servicios; cada traslado puede contener muchas calles.
- Se permite elegir y repetir ubicaciones y cargar parcialmente en estaciones
  compatibles. Pasar por un cliente o cargador dentro de un camino no activa
  una entrega o recarga.
- Se mantienen flota, batería inicial, capacidad, reserva, compatibilidad,
  retorno y prioridad lexicográfica. Por defecto no hay ventanas, jornada ni
  obligación de usar ambos vehículos. `--config` permite activar las
  [extensiones operacionales](operations.md), guardadas en el snapshot.
- Solo se admiten energías de calle **no negativas**. El estimador descriptivo
  kWh/km actual cumple esa condición. Las entradas con regeneración se rechazan:
  agregar su energía podría ocultar un déficit intermedio o saturación.

**No es una reformulación equivalente del modelo vial del PDF.** Fijar un
camino por par y cambiar la unidad de `H` modifica el conjunto representado.
Una prueba de optimalidad y sus gaps corresponden al grafo de servicios,
sus caminos disponibles y su límite de traslados.
No se afirma optimalidad en todas las calles con el `H` original.
La formulación base y el comando `run` sobre una red elemental siguen disponibles.

### Adaptación del preprocesamiento de `codex/optimizacion-contraida`

Referencia inspeccionada: commit `2bac3ead47576a96de8175f38626ba647232b24c`
de `DanielHermosilla/AWS-Hackaton`, rama `codex/optimizacion-contraida`.
En este checkout la rama se obtiene desde `origin`; no hay un remoto `upstream`
configurado.

- `src/evrp/caminos.py`, funciones `_csr` y `scipy_multi`: construcción de la
  adyacencia dispersa y Dijkstra para recuperar caminos entre servicios.
- `src/evrp/red.py`, métodos `preparar` y `_resolver_caminos`: separación entre
  preparación vial y cálculo de caminos.
- `docs/experimentos/caminos.md` y `tests/test_caminos.py`: referencia para
  comprobar energías por par. Sus tiempos y resultados no se atribuyen a esta rama.

La adaptación usa nuestros contratos `ProblemInstance`, `Arc` y `PathArchive`,
conserva IDs opacos y pares inalcanzables, y limita la memoria de Dijkstra
procesando un origen por vez. SciPy es una dependencia directa fijada en
`uv.lock`; NetworkX continúa disponible para las heurísticas de H.

Se conserva íntegramente el modelo y el adaptador **Pyomo + Gurobi/SCIP de
`modelamiento`**. No se incorporan `milp.py`, `milp_compacto.py`, heurísticas de
resolución, tuning, elevación ni el modelo energético de la rama de referencia.
Tampoco se copian su ajuste de coordenadas o su caché basada en metadatos del
archivo. La entrada sigue siendo nuestra red dirigida preparada, con su energía
y accesos registrados. Las energías negativas se rechazan en esta variante.

Verificación local del 15 de octubre de 2026, sobre el mismo snapshot vial
`928d99fb05491a93c9e71666c038e835822e31d5215842ff03399845da77cb71`:

- 106.746 nodos y 211.725 arcos viales pasan a 81 servicios y 6.006 conexiones.
  Se conservan los 20 clientes y 60 cargadores. Los 474 pares ordenados sin
  camino no se conectan artificialmente.
- Una ejecución por versión, con la instancia ya cargada y el mismo H=21:
  **44,00 s** con el preprocesador anterior de NetworkX y **1,35 s** con SciPy.
  Las 6.006 energías por par coincidieron exactamente. Se comprobaron también
  todas las secuencias y sus sumas de distancia sobre las calles originales.
  Es una comparación del preprocesamiento, no del tiempo del solver.
- La CLI eligió H=21 con certificado y produjo un testigo de 20 entregas que
  pasó tanto el checker compacto como la expansión vial. Este testigo no se
  atribuye al solver ni se declara óptimo; supera el H vial original de 200.
- `uv run --locked pytest -q`: **423 pruebas pasaron**, sin omisiones.
  `uv run --locked ruff check src tests`: sin problemas. Se verificó por SHA-256
  que modelo, solver, red, contratos, heurísticas, pipeline y validador mantienen
  su contenido previo a esta adaptación.

La comparación y las verificaciones quedan en
`artifacts/preprocessing-adaptation-2bac3ead/{comparison,validation}.json`,
con los snapshots de la prueba en esa misma carpeta, fuera de Git.

Con la red local preparada y 30 traslados por vehículo, se obtuvieron
81 nodos, 6.006 arcos y 366.722 binarias. Los 30 traslados son una elección
de este ensayo, no una regla de la hackatón.

## Comandos

Desde la raíz del repositorio, si todavía no existe `artifacts/hackathon/instance.json`:

```bash
bash scripts/prepare_hackathon.sh config/default.json
```

Para preparar los caminos y ejecutar las dos fases, con presupuesto blando
de 120 segundos y dos threads:

```bash
bash scripts/run_pptx.sh 120
```

El script se ejecuta en una shell hija: no usar `source` ni pegar su contenido
en una shell interactiva. Reutiliza la red y energía preparadas y regenera
los caminos; no descarga mapas ni llama a AWS. `HACKATHON_RUN_DIR` permite
usar otra carpeta que contenga su propio `instance.json`.

El H predeterminado ahora es `auto`: una heurística acotada verifica condiciones
que permiten un H pequeño sin cortar el óptimo. Si no alcanza el certificado,
el script se detiene antes de construir el MILP. Un segundo argumento entero
mantiene el modo manual. Ver [prueba y warm start](heuristics.md).

Los comandos genéricos equivalentes son:

```bash
uv run --locked ev-routing service-graph \
  --road-instance artifacts/hackathon/instance.json \
  --service-movements auto \
  --output artifacts/hackathon/service-instance.json \
  --path-archive artifacts/hackathon/service-paths.json

uv run --locked ev-routing run \
  --instance artifacts/hackathon/service-instance.json \
  --road-instance artifacts/hackathon/instance.json \
  --path-archive artifacts/hackathon/service-paths.json \
  --initial-solution artifacts/hackathon/service-instance.start.json \
  --time-limit-seconds 120 --threads 2 --tee \
  --output artifacts/hackathon/service-result.json
```

Para repetir solo la resolución, ejecutar el segundo comando. Si cambia
la red, energía, flota o límite de traslados, regenerar la instancia y caminos.
El pipeline rechaza snapshots que no coincidan con sus huellas.

El resumen JSON de `service-graph` informa tamaños antes y después,
`shortest_path_algorithm`, pares ordenados inalcanzables y
`preprocessing_seconds`. Ese tiempo incluye la construcción del grafo compacto
y su archivo de caminos en memoria; excluye lectura/escritura, análisis de H
y solver. No se guarda dentro de la huella del snapshot.

## Cómo leer el resultado

`service-result.json` conserva la solución, KPIs y certificados por fase.
El log nativo queda en `service-solve.log`. El presupuesto incluye
construcción y resolución; lectura, preparación de caminos y auditoría añaden
tiempo. Un timeout con incumbente puede dar una solución factible sin prueba
de optimalidad; no implica que la ejecución haya fallado.

Además del checker sobre servicios, `road_validation` expande los caminos
seleccionados y vuelve a comprobar cada calle, entrega, recarga y batería:

- `feasible`: comprobación física sobre las calles y energías originales.
- `road_movement_counts`: calles recorridas por vehículo, sin relleno en depósito.
- `original_road_movement_limit`: el `H` vial del snapshot original.
- `within_original_movement_limit`: si esos recorridos caben también en ese `H`.
- `routes`: posiciones de los recorridos expandidos, con baterías y entregas.

Para alojar la expansión, el checker utiliza una copia con suficientes
posiciones; no modifica la entrada. Por eso `feasible=true` junto con
`within_original_movement_limit=false` significa que las rutas respetan
calles y batería, **pero no son factibles para el H vial original**.
Si falla la comprobación física, el estado pasa a `invalid_solution`
y los KPIs que requieren una solución válida quedan suprimidos.

La energía sigue siendo una estimación descriptiva de los históricos.
La verificación no garantiza consumos reales ni valida permisos o cierres
de calles que no estén representados en los datos.

## Corrida local comprobada

El 15 de octubre de 2026 se ejecutó la instancia completa preparada con
Gurobi 13.0.3, dos threads, semilla 0, presupuesto blando de 120 segundos
y 30 traslados por vehículo. La capacidad útil de 24 kWh y reserva de 2,4 kWh
son supuestos; la energía inicial fue 14,4 kWh por vehículo.
El estimador utilizado fue 0,1567712473 kWh/km.

| Resultado | Valor |
|---|---|
| Entregas | 20/20, máximo probado en la variante |
| Energía neta de batería | 10,734136 kWh |
| Cota inferior de energía | 9,725500 kWh |
| Gap de energía | 9,3965 %; terminó por tiempo |
| Ejecución de resolución y auditoría | 126,17 s, sin preparar caminos ni leer los archivos |
| Distancia | 68,470 km |
| Vehículos utilizados / disponibles | 1 / 2 |
| Recargas | Ninguna |
| Batería mínima | 3,665864 kWh |
| Calles recorridas | 2.005 y 0, respectivamente |
| Auditoría vial y de batería | Correcta |
| Cumplimiento del H vial original de 200 | No |

La solución no está probada óptima en energía. El segundo vehículo quedó
inactivo; la formulación lo permite. Tampoco es una solución del modelo vial
con `H=200`, aunque cumpla la reserva sobre cada calle.
Los artefactos locales son `artifacts/hackathon/service-result.json`,
`service-result-summary.json` y `service-solve.log`. Estos resultados describen
una corrida concreta, no garantizan iguales tiempos o rutas al repetirla.
