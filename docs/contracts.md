# Contratos de datos de la integración

La fuente ejecutable es
[`src/ev_routing/contracts.py`](../src/ev_routing/contracts.py), importada sin
modificar de Daniel Hermosilla en `modelamiento@6242035`. Define los modelos
Pydantic y sus validaciones. El transporte y la proyección de la web están en
[backend/API_CONTRACT.md](../backend/API_CONTRACT.md).

`ProblemInstance` 1.0 es la entrada común de CLI y web. Contiene nodos con IDs
opacos, arcos dirigidos elementales, parámetros físicos, opciones operacionales,
compatibilidad de cargadores y procedencia. Los nodos pueden ser `base`, `visit`,
`charger` o `junction`. Las coordenadas se omiten juntas cuando no están
disponibles; no son necesarias para resolver un grafo ya definido.

Las unidades forman parte del contrato: distancia en metros, tiempos en
segundos, energía y batería en kWh, `initial_soc` como fracción entre 0 y 1.
En arcos, energía positiva consume y negativa representa regeneración potencial.
La geometría nativa usa `[latitud, longitud]` según `network.py`; el adaptador
web la convierte a GeoJSON `[longitud, latitud]`. La energía efectiva de una
solución considera saturación; no se reemplaza por la suma nominal de arcos.

`SolverConfig` separa recursos y backend de las condiciones físicas. La API
pública solo permite elegir el presupuesto de tiempo. Los valores efectivos
—`scip-routes`, un hilo, semilla cero, gap cero y política estándar sin AWS—
quedan registrados en cada ejecución.

`SolveResult` conserva `PhaseResult` por objetivo, una `Solution` opcional,
estado, solver usado, origen de la solución y alcance de optimalidad.
Cada `RouteStep` conserva llegada, recarga, salida, servicios explícitos y el
arco siguiente. `effective_arc_energy_kwh` pertenece al movimiento **saliente**.
Los índices de posición identifican ocurrencias; pasar por un cliente no
implica realizar su entrega.

`pipeline.run_instance` devuelve el JSON nativo versionado con resolución,
validación independiente, KPIs, tiempos y procedencia. El puente web conserva
ese objeto íntegro en `raw.result` y añade una proyección estable para la UI.
Sin solución, los estados y fases siguen disponibles; los KPI desconocidos no
se convierten en ceros ni en una declaración de infactibilidad.

Los ejemplos compartidos son
[`toy_recharge.json`](../examples/toy_recharge.json) y
[`toy_regeneration.json`](../examples/toy_regeneration.json).
Las pruebas de integración ejecutan esos contratos con el solver real.
El algoritmo puede evolucionar detrás del puente. Cambiar significado o campos
requeridos exige una versión nueva, pruebas de compatibilidad y una adaptación
explícita del consumidor.
