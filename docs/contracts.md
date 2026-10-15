# Contratos mínimos

En `scip-routes` (backend predeterminado), `movement_limit` se conserva en
snapshots 1.0 como metadato heredado. No restringe rutas, pricing ni checker.
`formulation.movement_limit_used` es `null`; las rutas tienen longitud variable.
`solution_source="heuristic"` identifica un testigo construido por el programa
si se conserva como incumbente. La referencia posicional mantiene su contrato H+1.

`src/ev_routing/contracts.py` valida los objetos con Pydantic. Rechaza campos
desconocidos y valores numéricos no finitos.

| Objeto | Contenido y función |
|---|---|
| `Node` | ID opaco, tipo y ubicación; puede ser intersección, depósito, cliente o cargador. |
| `Arc` | Tramo dirigido elemental, energía firmada en kWh y distancia en metros. |
| `ModelParameters` | Flota, capacidad útil, reserva, SoC inicial, conectores y `movement_limit` (H). |
| `ProblemInstance` | Nodos, arcos, parámetros, compatibilidad y procedencia. Es el JSON de entrada al solver. |
| `SolverConfig` | Backend, segundos, threads, semilla y gap solicitado; no cambia el problema. |
| `PhaseResult` | Incumbente, cota, gap y terminación de una fase concreta. |
| `RouteStep` | Una posición: nodo, entrega, recarga, batería antes/después y arco siguiente. |
| `Solution` | Rutas e indicadores declarados por el solver, pendientes de validar. |
| `ValidationReport` | Comprobaciones físicas independientes y violaciones detectadas. |
| `SolveResult` | Backend efectivo/fallback, fases, solución y alcance de optimalidad. |

El JSON final de `run_instance` envuelve `SolveResult`, validación, KPIs,
configuración, procedencia, hash de instancia y tiempos. Tiene
`schema_version="1.0"`; sin política adaptativa, `tuning.status="disabled"`. Los campos desconocidos
por falta de datos se expresan como `null`, nunca como `NaN` o un ahorro cero.

En la referencia posicional, cada ruta conserva **H+1 posiciones**, incluidas
permanencias en el depósito. En `scip-routes` su longitud es variable.
La última posición no tiene recarga, arco siguiente ni consumo de movimiento.
Las entregas están en `delivered_visit_ids`; visitar físicamente el nodo no
alcanza para considerarlo atendido.

`prepare` escribe un snapshot autosuficiente del problema.
`run --config ...` utiliza solamente la sección `solver`: el escenario físico
se toma del snapshot, para evitar cambios silenciosos.

La [variante entre servicios](service-graph.md) declara
`provenance.representation.kind="service_paths_nonnegative"` y usa `Arc`
para caminos completos no negativos. Su `movement_limit` cuenta traslados
entre servicios. `PathArchive`, definido en `service_graph.py`, vincula cada
arco con su secuencia de nodos viales y las huellas de ambas instancias.
La representación registra el algoritmo de caminos, el peso `energy_kwh`,
la cantidad de orígenes y los pares ordenados de servicios inalcanzables.
Conserva todos los servicios, incluso aislados, y omite únicamente conexiones
que no existen en la red dirigida.
El pipeline exige la red original y ese archivo para resolver la variante.
La salida añade `road_validation` con la auditoría sobre calles, los recorridos
expandidos y el cumplimiento separado del `H` vial original; en el modelo base
ese campo es `null`.

La preparación de servicios añade `provenance.horizon_selection`: modo,
H efectivo, suficiencia, minimalidad y análisis de la heurística. El archivo
compañero `.start.json` contiene `InitialSolution` (hash del snapshot y
`Solution` o `null`). El hash incluye H; un arranque de otro snapshot se rechaza.
El resultado informa `initial_solution` y `solve.solution_source`. Cada fase
incluye `warm_start` (`not_requested`, `submitted`, `unsupported`) e
`incumbent_source` (`solver`, `provided_incumbent` o `null`).
Un incumbente conservado ante timeout no se atribuye al solver. Ver
[certificado de H y arranque](heuristics.md).

## Datos y límites

`ProblemInstance.operations` contiene `Operations`, con defaults neutros.
`ProjectConfig.operations` permite introducirlo al preparar; el comando
`run` no lo reemplaza. Ver [campos y dependencias](operations.md).
`Arc.travel_time_seconds` es opcional; el bloque temporal exige tiempo explícito
o una velocidad asumida. Las huellas incluyen estos campos: regenerar artefactos
preparados antes de la actualización, no aceptar un arranque de otro escenario.

`RouteStep` añade llegada, inicio de actividad, salida, duración de servicio,
recarga y viaje en segundos. Sin bloque temporal quedan en `null`.
`VehicleRoute.duration_seconds` mide hasta el retorno final. El JSON incluye
`operations`, duración por vehículo, máximo y suma de duraciones, y energía de
red cuando la eficiencia está especificada. Las ventanas son de fin de servicio;
un cliente sin ventana configurada no recibe una automáticamente.


- Los CSV de nodos contienen ubicaciones de servicio, no calles.
- La energía eVED se integra por `(VehId, Trip)` y tiempo real.
- El estimador inicial usa kWh/km descriptivos de los EV históricos. No es una
  predicción de pendientes, clima o regeneración en cada calle.
- Un GraphML OSMnx suministra las calles dirigidas. Los accesos de servicio
  son conectores bidireccionales supuestos, acotados y registrados.
- `network_profile=delivery` incluye calles de servicio y pasillos de
  estacionamiento sin etiquetas explícitas de acceso privado/prohibido.
  Perfil y filtro se guardan en GraphML y procedencia; una caché de otro
  perfil no se reutiliza silenciosamente.
- Los arcos paralelos se subdividen para preservar sus alternativas. Esto
  aumenta movimientos y por tanto afecta la elección de H.
- La validez física se refiere a estas energías, accesos, red y H. No certifica
  el consumo real futuro ni la optimalidad en una red más amplia.

## Control experimental de búsqueda

`SolverConfig.solver` admite `gcg` además de los backends existentes.
`SearchConfig`, `SearchPolicy` y `BedrockConfig` están en `search_policy.py`.
Son configuración de algoritmo e inferencia, separada de `ProblemInstance`.
Rechazan campos ajenos a la lista admitida; la política adaptativa exige un
modelo explícito. Región inicial `us-east-1`, perfil inicial `hackathon`.

`SolveResult.search` es `null` para Gurobi/SCIP. En GCG contiene versión,
configuración, huellas de matrices, particiones, parámetros efectivos,
callbacks, errores, tiempos y decisiones del controlador.
`tuning` expone ese controlador con estados `disabled`, `applied`,
`partial_fallback` o `fallback`. Cada decisión tiene estado independiente;
una propuesta recibida después de terminar la fase queda `not_applied`.
Las políticas válidas persisten entre fases si no llega otra propuesta válida.

`runtime_seconds.llm` está incluido en resolución/total y puede solaparse con
el solver; no es un intervalo adicional que deba sumarse.
`solve.search.phases[].native_optimize_seconds` mide la llamada nativa a GCG.
Una decisión aplicada no demuestra aceleración. Ver [benchmark y
certificados](dantzig-wolfe.md).

En el motor por rutas, `solve.search.controller` registra las decisiones por
evento, estados `adaptive`, `partial_fallback`, `fallback` o `disabled`, uso,
tiempo y campos inactivos. `solve.search.phases` identifica cada etapa con
`restricted_pool`; su cota nativa nunca acredita el maestro completo.
`first_full_delivery_seconds` identifica el primer testigo de servicio completo
y `energy_relaxation` documenta una cota energética independiente, su alcance
y su margen numérico. `native_parameter_changes` contiene cambios ejecutados
en SCIP, incluidos presets. Ver [orquestación](orchestration.md).
