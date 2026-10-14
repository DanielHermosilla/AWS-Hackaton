# Modelo de ruteo eléctrico

La fuente matemática es [`modelamiento.pdf`](../modelamiento.pdf). El módulo
`src/ev_routing/model.py` implementa sus dominios, ecuaciones (1)–(15) y objetivo
lexicográfico (16) directamente en Pyomo. No utiliza un TSP sobre una matriz de
caminos entre clientes: la entrada contiene una **red vial dirigida de tramos
elementales**, y cada variable `x[i, j, k, r]` selecciona un tramo.

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
Pyomo (`tests/oracle.py`), limitado a fixtures pequeñas de energías enteras.
Buscan Gurobi y después SCIP; si ninguno puede resolver, se omiten únicamente
esas pruebas y queda registrado el motivo.
