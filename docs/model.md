# Modelo de ruteo eléctrico

**Vigente:** `scip-routes` implementa (25)–(29) del PDF sin H;
ver [maestro por rutas, pricing y demostraciones](dantzig-wolfe.md).
El texto siguiente documenta la referencia posicional Pyomo (1)–(24),
seleccionable explícitamente con `auto`, `gurobi`, `scip` o `gcg`.

La fuente matemática es [`modelamiento.pdf`](../modelamiento.pdf). El módulo
`src/ev_routing/model.py` implementa sus dominios, ecuaciones (1)–(15) y objetivo
lexicográfico (16) directamente en Pyomo. No utiliza un TSP sobre una matriz de
caminos entre clientes: la entrada contiene una **red vial dirigida de tramos
elementales**, y cada variable `x[i, j, k, r]` selecciona un tramo.

Esto describe la versión base. La [variante opcional entre servicios](service-graph.md)
reutiliza las ecuaciones sobre otro grafo, con caminos fijos no negativos.
Allí un movimiento cuenta un traslado entre servicios. No es equivalente a
la formulación vial con su `H`; su procedencia y certificados lo identifican.

## Parámetros, conjuntos y representación

`build_model(instance)` recibe un `ProblemInstance` ya validado. Conserva todos
sus nodos y arcos y añade únicamente `(depot, depot)`, con consumo cero, para
completar posiciones o mantener un vehículo inactivo.

| PDF | Entrada o componente Pyomo |
|---|---|
| \(V,A,C,F,K\) | `V`, `A`, `C`, `F`, `K` |
| \(F_k\) | `F_compatible[k]`, obtenido de `instance.chargers_for(k)` |
| \(H\) | `parameters.movement_limit`, componente `H` |
| \(R=\{0,\ldots,H\}\) | `R` |
| \(R^-=\{0,\ldots,H-1\}\) | `R_moves` |
| \(B\) | `parameters.battery_capacity_kwh`, componente `B` |
| \(\underline b\) | `parameters.reserve_kwh`, componente `reserve` |
| \(b^{ini}\) | `initial_energy = initial_soc * battery_capacity_kwh` |
| \(e_{ij}\) | `Arc.energy_kwh`, componente `e[i, j]` |
| \(M=B+\max_{(i,j)\in A}|e_{ij}|\) | `M`, calculado incluyendo el arco artificial |

El escenario oficial usa dos vehículos y `initial_soc=0.6`. Los contratos
permiten cambiar cantidad de vehículos y SoC para escenarios identificados
explícitamente; no son modificaciones que deba decidir un LLM de tuning.
Todos los vehículos comparten capacidad, reserva y SoC inicial. La
compatibilidad de estaciones sí puede especificarse por vehículo.

`H` cuenta **movimientos**, no segundos. Los índices de los vehículos no
sincronizan sus relojes. Reducir `H`, eliminar calles o sustituir la red por
caminos prefijados puede restringir el conjunto factible. Un certificado del
solver sólo corresponde a la instancia y al `H` efectivamente resueltos.

## Variables y correspondencia de ecuaciones

Las binarias `y`, `z`, `x`, `a` y `gamma` corresponden a las del PDF.
`b[k,r]` es batería al llegar y `b_departure[k,r]` representa
\(\bar b_{kr}\), batería al salir después de cargar. Ambas están en
`[reserve, B]`. `q` es no negativa; `u`, `E` y `E_total` son reales sin
restricción de signo. Las energías se expresan en kWh.

| Ecuación | Componentes | Significado |
|---|---|---|
| (1) | `eq01_location` | Un nodo ocupado por vehículo y posición. |
| (2) | `eq02_start`, `eq02_return` | Inicio y posición final en el depósito. |
| (3) | `eq03_departure` | Un arco sale del nodo ocupado. |
| (4) | `eq04_arrival` | Ese arco llega al nodo de la siguiente posición. |
| (5) | `eq05_service_location` | Entregar requiere estar en el cliente. |
| (6) | `eq06_unique_delivery` | Cada entrega se cuenta una sola vez entre todos. |
| (7) | `eq07_initial_battery`, `eq07_initial_charge` | Energía inicial fijada y recarga inicial cero. |
| (8) | `eq08_charge_balance` | Batería de salida = llegada + carga. |
| (9) | Dominio de `q`, `eq09_charge_capacity` | Carga no negativa sin superar capacidad. |
| (10) | `eq10_compatible_charge` | Sólo se carga en una estación compatible. |
| (11) | `eq11_unsaturated_battery` | Energía posterior al tramo antes de saturar. |
| (12) | `eq12_below_unsaturated`, `eq12_below_capacity` | Llegada acotada por `u` y por `B`. |
| (13) | `eq13_uncapped_branch`, `eq13_capped_branch` | Linealización exacta de `min(u, B)`. |
| (14) | `eq14_effective_energy` | Consumo neto efectivo de cada movimiento. |
| (15) | `eq15_total_energy` | Suma de los consumos efectivos. |
| (16) | `deliveries_objective`, `energy_objective`, `served_count_constraint` | Dos fases con cumplimiento fijado en la segunda. |

La actualización del PDF incorpora estas extensiones opcionales. La fuente
editable es `modelamiento.tex`; los detalles de configuración están en
[operations.md](operations.md).

| Ecuación | Implementación | Significado |
|---|---|---|
| (17) | `operations.arc_energy`, `chargers_for` | Margen sobre descargas nominales y estaciones deshabilitadas. |
| (18) | `eq18_final_reserve` | Reserva adicional solo en el regreso final. |
| (19) | `station_charge`, `eq19_station_charge_bound`, `eq19_station_charge_sum` | Localizar recarga con variables continuas, sin productos de variables. |
| (20) | `service_duration`, `charging_duration`, `travel_duration` | Componentes temporales en segundos. |
| (21) | `route_duration`, `eq21_duration_limit` | Jornada agregada sin relojes, si no hay ventanas. |
| (22) | `arrival_time`, `activity_start`, `eq22_*` | Relojes y espera cuando se activan ventanas. |
| (23) | `eq23_window_open`, `eq23_window_close` | Ventanas de entrega completa; grandes M derivados de la jornada. |
| (24) | Los dos objetivos originales y extensiones activas | Conserva la prioridad lexicográfica. |

Con margen, `e` y `M` se construyen con energía del escenario; `Arc.energy_kwh`
continúa nominal. El validador y la expansión aplican el mismo escenario una
sola vez. La extracción publica el calendario más temprano de las mismas
rutas y recargas; quitar espera sobrante es válido bajo tiempos constantes,
sin colas, cierres de cargadores ni consumo auxiliar durante esperas.
Se comprueba independientemente el calendario publicado.

Pasar por un cliente no activa automáticamente `y`: el servicio se decide con
`a[i,k,r]`. Se permite repetir clientes sin repetir su entrega, así como repetir
calles, intersecciones y estaciones. El modelo también permite volver al
depósito y salir nuevamente: no hay una restricción de absorción tras el primer
retorno.

El depósito no es un cargador y no se carga allí, ni al inicio ni durante
retornos intermedios. La posición terminal `H` no tiene recarga, servicio ni
movimiento de salida.

## Batería, regeneración y significado del objetivo

En cada movimiento:

\[
u_{kr}=\bar b_{kr}-\sum_{(i,j)\in A} e_{ij}x_{ijkr},
\qquad
b_{k,r+1}=\min(B,u_{kr}).
\]

`gamma=0` activa la igualdad con `u`; `gamma=1` activa la igualdad con `B`.
Si `u=B`, ambas binarias son válidas. La regeneración que no cabe en la batería
no se almacena y no reduce el consumo efectivo:

\[
E_{kr}=\bar b_{kr}-b_{k,r+1},\qquad
E_{\mathrm{total}}=\sum_{k,r}E_{kr}
=\sum_k\left(b^{ini}+\sum_rq_{kr}-b_{kH}\right).
\]

No sustituir este objetivo por `sum(e[i,j] * x[i,j,k,r])`: esa expresión
acreditaría regeneración descartada por saturación. `q` es energía incorporada
a la batería, no electricidad comprada a la red.

Los consumos son deterministas. Los tramos deben ser elementales: si un arco
oculta una descarga intermedia o efectos de saturación, debe subdividirse.
Verificar sólo el balance al final de un camino agregado no garantiza la
reserva durante el recorrido. El módulo no infiere ni modifica esos consumos.

La versión base no modela jornada, tiempos de servicio, capacidad de paquetes,
curvas o duración de carga, colas ni ocupación simultánea de puertos. La
compatibilidad habilita una estación; no representa una reserva temporal de
un conector.

## API y certificados

- `build_model(instance) -> ConcreteModel`: construye el modelo con
  `deliveries_objective` activo y `energy_objective` desactivado.
- `activate_energy_phase(model, served_count) -> None`: desactiva el objetivo
  de entregas, activa el de energía y fija `served_count` mediante una igualdad.
  Rechaza conteos no enteros o fuera de `[0, number_of_customers]`.
- `extract_solution(model, instance) -> Solution`: extrae todas las posiciones,
  incluida la llegada terminal y permanencias en el depósito. Rechaza valores
  ausentes/no finitos, binarias fraccionarias y reconstrucciones sin ubicación
  o arco único. No sustituye al validador independiente.

`served_count` es una expresión pública con `sum(y[i])`. La igualdad de la
segunda fase es `served_count_constraint`, cuyo parámetro mutable es
`served_count_target`. Activar esa igualdad no demuestra que el cumplimiento
sea máximo: eso depende de las cotas y la terminación de la primera fase.
Cuando se fija sólo un incumbente no certificado, la segunda fase es una
mejora energética condicionada a ese cumplimiento.

No se mezclan gaps de las dos fases ni se presenta el tiempo de cómputo como
una variable de la función objetivo. La selección y ejecución del solver,
el presupuesto y los certificados pertenecen a `solve.py`.

## Verificación

`tests/test_model.py` comprueba dimensiones y dominios, recorridos construidos
a mano, entregas separadas del tránsito, retorno intermedio, compatibilidad,
recarga prohibida en depósito, saturación, déficit intermedio, nodos aislados
y extracción. Las pruebas con solver comparan ambas fases con óptimos
obtenidos por un enumerador de caminatas y niveles de carga independiente de
Pyomo (`tests/oracle.py`), limitado a fixtures pequeñas bajo las hipótesis de
exactitud descritas a continuación.
Buscan Gurobi y después SCIP; si ninguno puede resolver, se omiten únicamente
esas pruebas y queda registrado el motivo.

La batería de pruebas también incluye 18 redes dirigidas generadas con semillas
fijas: 12 con energías enteras y posibles recargas, y 6 sin recarga con energías
fraccionarias. En cada una compara el máximo de entregas y luego el mínimo de
energía, y somete los incumbentes de **ambas fases** al validador independiente.
Otros casos fuerzan dos visitas a un cliente con una sola entrega, retorno
intermedio al depósito, dos recargas positivas en la misma estación, asignación
entre vehículos y cambios de factibilidad al variar `H`. También comprueban
saturación justo en capacidad, reserva justo al regresar, déficit antes de
regeneración y una recarga fraccionaria óptima con datos enteros. Un ciclo de ganancia
energética artificial comprueba que el modelo finito respeta `H` y la capacidad;
no se presenta como una predicción física de una calle real.

El oráculo entero no aproxima las cargas continuas del MILP mediante una
cuadrícula arbitraria. Para una caminata y sus ramas de saturación fijadas,
se elimina `q` y quedan restricciones de diferencias entre baterías, además
de cotas y fijaciones. Con capacidad, reserva, energía inicial y consumos
enteros, esa matriz de diferencias tiene vértices enteros; existe una solución
óptima entera en cada rama factible. La unión finita de caminatas y ramas
conserva al menos un óptimo entero. Por eso enumerar esos niveles es exacto
para las fixtures admitidas, aunque otras soluciones óptimas puedan tener
recargas fraccionarias. El oráculo rechaza entradas no enteras en vez de
redondearlas silenciosamente.

El oráculo sin recarga usa `Fraction` para evaluar exactamente los decimales de
las fixtures y rechaza estaciones habilitadas; ignorarlas cambiaría el problema.
Ninguno de los dos oráculos usa Pyomo, valores auxiliares del modelo o su solver.

Para calcular el máximo servicio de cada combinación de caminatas, el oráculo
toma la unión de los clientes encontrados: en la versión base una entrega no
consume energía, tiempo ni capacidad adicional y puede asignarse a una sola
de sus visitas. Esta reducción preserva los dos óptimos. No obliga a entregar
cada vez que se pasa por un cliente; esa separación se comprueba también con
recorridos explícitos y con un cliente de articulación visitado dos veces.
