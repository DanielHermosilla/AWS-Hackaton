# H automático y arranque del solver

Este documento describe la **referencia posicional heredada**.
El flujo vigente `scip-routes` y la preparación predeterminada no eligen H;
ver [formulación por rutas](dantzig-wolfe.md).

`src/ev_routing/heuristics.py` calcula una cota pequeña de movimientos sin resolver
el MILP. Se aplica a la variante entre servicios, no al H de calles del PDF.
No usa resultados anteriores, AWS ni una búsqueda local costosa.

## Procedimiento y certificado

1. Verifica consumos no negativos y desigualdad triangular dirigida sobre todos
   los servicios. Rechaza atajos ausentes o más caros que pasar por un tercer nodo.
2. Usa `networkx.approximation.greedy_tsp` desde distintos nodos, con hasta
   32 inicios y 0,5 segundos de presupuesto blando, configurables en la función.
   Detiene la búsqueda cuando basta para la prueba.
3. Si un recorrido completo consume `U <= energía_inicial - reserva`, recomienda
   `H = clientes + 1`. Todo óptimo consume como máximo U y cada ruta consume
   energía no negativa; por tanto no necesita recargas. Los caminos mínimos
   permiten quitar paradas sin entrega sin aumentar el consumo.
4. Si además `e[i,base] + e[base,j] > e[i,j]` para todos los clientes distintos,
   unir dos rutas con entregas mejora energía. Como su consumo conjunto cabe
   en una batería inicial, un óptimo utiliza una sola ruta y ese H también
   es mínimo. No afirmar mínimo cuando hay igualdad.

La comparación energética es la del modelo actual: batería homogénea,
sin ventanas, jornada, capacidad de paquetes ni obligación de usar toda la flota.
Una extensión de esas condiciones requiere revisar o desactivar el certificado.
Certificar H no certifica óptima la energía del testigo.

La implementación desactiva tanto la recomendación como la cota estructural
cuando `operations` activa jornada, ventanas o reserva final mayor que la
reserva base. `auto` se detiene; un H explícito conserva un ensayo condicionado.
El margen energético se incorpora a pesos y testigo; las estaciones
deshabilitadas se excluyen de las compatibles antes del análisis.

Con opciones operacionales y H manual, `build_greedy_start` intenta insertar
clientes al final de los recorridos sin recargas, comprobando retorno, batería
y calendario. Puede atender solo parte de la demanda. Su presupuesto blando
es de 0,5 s; tiempo, método y entregas quedan en
`provenance.initial_solution_construction`. No certifica H ni optimalidad.
Un arranque que incumple reserva final, jornada o ventanas no se envía al solver.

Casos adicionales: sin clientes H=1 es mínimo; sin estaciones compatibles,
H=clientes+1 es suficiente aun cuando solo pueda atenderse parte de la demanda.

Si no alcanza la prueba, se devuelve `not_certified`, con motivo y presupuesto
utilizado. Bajo las hipótesis verificadas, la cota estructural
`(clientes+1)*(1+máximo de cargadores compatibles por vehículo)` es segura:
entre entregas consecutivas se pueden eliminar ciclos que repitan una estación,
ajustando su carga. Puede ser demasiado grande para el modelo por posiciones.
El modo automático no la utiliza para lanzar un MILP enorme.

## Uso

```bash
bash scripts/run_pptx.sh 120
```

El segundo argumento predeterminado es `auto`. `bash scripts/run_pptx.sh 120 30`
conserva un H manual de 30 y registra si está respaldado por el análisis.
La preparación de calles y energía debe existir previamente.

Por CLI:

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
  --time-limit-seconds 120 --threads 2 \
  --output artifacts/hackathon/service-result.json
```

Junto a `service-instance.json` se guardan:

- `service-instance.horizon.json`: prueba, H recomendado, cota estructural,
  recorrido candidato, energía, presupuesto, intentos y tiempo de heurística.
- `service-instance.start.json`: SHA-256 del snapshot y solución inicial
  con H+1 posiciones, o `solution: null` si no hay un testigo que quepa.

El análisis también queda en `provenance.horizon_selection`, con el modo,
H efectivo y distinción entre suficiente y mínimo. Si `auto` no consigue
certificado, escribe el análisis y termina con código 2 antes de construir
el MILP. Un H entero es una selección explícita; no recibe garantías falsas.

## Warm start y conservación del incumbente

Antes de resolver se valida el testigo con el checker independiente. Para
servicios se comprueba además la expansión sobre las calles. Se rechaza un
archivo de arranque que no coincida con el hash del snapshot.

Gurobi recibe el vector completo por el adaptador existente de Pyomo,
`gurobi_direct`, con `warmstart=True`. Las variables conservan sus dominios y
permanecen libres; el vector incluye batería y auxiliares de saturación.
La segunda fase recibe el mejor incumbente con el cumplimiento fijado.

El adaptador SCIPAMPL instalado informa `warm_start_capable() == False`.
No se le pasa una opción inventada ni se cambia de backend. La solución inicial
se conserva fuera del solver y puede ser el resultado si no encuentra otra mejor.

Los resultados registran:

- `initial_solution`: presencia, validación, entregas y energía del testigo.
- `solve.solution_source`: `solver` o `initial_solution`.
- Por fase, `warm_start`: `not_requested`, `submitted` o `unsupported`.
- Por fase, `incumbent_source`: `solver` o `provided_incumbent`; la segunda opción
  puede ser la heurística o el mejor incumbente de la fase anterior.
- Terminación, cota, gap y optimalidad por fase, aun si se conserva el testigo
  tras timeout o falta de solver. `submitted` no significa aceptación nativa.
- `runtime_seconds.initial_solution_validation`, separado de la validación final.

No se cambia de solver por timeout, infactibilidad o falta de soporte de arranque.
Que exista una solución inicial no autoriza declarar óptimo lexicográfico.
El tiempo de selección de H está en el análisis de preparación; su presupuesto
no se descuenta del límite de solver y debe incluirse al medir el flujo completo.
