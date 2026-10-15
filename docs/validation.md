# Verificación de la rama `modelamiento`

Ejecución local del 15 de octubre de 2026 (UTC), Python 3.12, Pyomo 6.10.1,
Gurobi 13.0.3 y SCIP 9.2.4. Los resultados describen esta implementación y
estos ensayos; no acreditan rendimiento en la instancia completa del concurso.

## Suite automatizada

**349 pruebas aprobadas, 0 fallos, 0 errores y 0 omitidas.**
Cobertura de líneas: **96.1 %** (1049 de 1092 sentencias).
Los informes locales están en `artifacts/tests/final.xml` y
`artifacts/tests/coverage.json`, fuera de Git.

| Área | Casos |
|---|---:|
| Configuración y contratos | 103 |
| Lectura de datos, energía y red | 54 |
| Modelo Pyomo y oráculos independientes | 50 |
| Adaptador Gurobi/SCIP y certificados | 32 |
| Validador independiente y métricas | 65 |
| CLI y pipeline | 37 |
| Esqueleto de tuning desactivado | 8 |

Se comprueban recarga repetida, regeneración saturada, déficit antes de
regeneración, vuelta intermedia al depósito, entregas únicas, clientes
inaccesibles, flotas parametrizadas y límites de movimientos. Los oráculos
enumeran caminatas diminutas con hipótesis de exactitud documentadas en
`docs/model.md`, sin reutilizar las restricciones Pyomo.

Las pruebas de fallos del solver simulan licencia ausente/insuficiente,
timeouts con y sin incumbente, errores de segunda fase y cotas incompletas.
Además hay ejecuciones reales con Gurobi y SCIP. La cobertura mide líneas
ejecutadas: no demuestra corrección para todas las instancias posibles.

Reproducir:

```bash
uv sync --locked
uv run pytest --cov=ev_routing --cov-report=term-missing \
  --cov-report=json:artifacts/tests/coverage.json \
  --junitxml=artifacts/tests/final.xml
uv run ruff check src tests
```

## CLI con ejemplos sintéticos

Se ejecutó cada ejemplo con ambos backends, con igual óptimo y validación
independiente satisfactoria:

| Ejemplo | Entregas | Energía neta | Recarga a batería |
|---|---:|---:|---:|
| `examples/toy_recharge.json` | 2/2 | 14 kWh | 9 kWh |
| `examples/toy_regeneration.json` | 1/1 | 2 kWh | 0 kWh |

En el segundo caso, sumar los consumos nominales de arcos daría −1 kWh:
sería incorrecto porque 3 kWh regenerados se descartan por saturación.
Los dos solvers producen el consumo efectivo correcto.

```bash
uv run ev-routing run --instance examples/toy_recharge.json \
  --solver gurobi --output artifacts/examples/toy_recharge-gurobi.json
uv run ev-routing run --instance examples/toy_recharge.json \
  --solver scip --output artifacts/examples/toy_recharge-scip.json
uv run ev-routing run --instance examples/toy_regeneration.json \
  --solver gurobi --output artifacts/examples/toy_regeneration-gurobi.json
uv run ev-routing run --instance examples/toy_regeneration.json \
  --solver scip --output artifacts/examples/toy_regeneration-scip.json
```

## Ensayo con datos locales y calles de Ann Arbor

Se integró `data/eVED_EV.csv` usando intervalos reales y excluyendo huecos
mayores a 10 segundos: 476308 filas, 504 viajes, 475223 intervalos válidos y
581 huecos excluidos. La razón descriptiva fue
366.975683 kWh / 2340.835385 km = **0.1567712473 kWh/km**.
No se utilizó la instancia `evaluation` para escoger ese coeficiente.
No es una evaluación predictiva fuera de muestra.

Se preparó una red vial OSM dirigida sin simplificar para el depósito y el
cliente V13 de `competition_routing_nodes.csv`, sin cargadores:
935 nodos y 1921 arcos, incluyendo accesos supuestos de 15.09 m y 7.93 m.
El snapshot local es
`artifacts/instances/ann-arbor-one-customer.json`.
El viaje requiere al menos 41 movimientos de ida y 41 de vuelta; por ello
`H=30` no permite esa entrega, aunque haya energía suficiente.

Para resolver un juguete acotado se conservó el subgrafo inducido por la unión
de los caminos de mínimo número de movimientos de ida y vuelta, y se fijó
`H=82`, con los dos vehículos. **Esta restricción es exclusiva del ensayo;
el pipeline de producción no recorta automáticamente la red.**
La selección y su alcance constan en `provenance.toy_scope`.

Gurobi probó ambas fases: **1/1 entrega**, **0.6008965368 kWh**,
**3.832951176 km**, sin recargas, con batería mínima de **13.79910346 kWh**.
El comprobador independiente aceptó el resultado. El tiempo medido de
resolución, incluida construcción, fue 1.254 s en esta ejecución;
no se presenta como benchmark ni ahorro frente a otro método.

Los artefactos locales permiten repetir exactamente el problema ya preparado:

```bash
uv run ev-routing run \
  --instance artifacts/instances/ann-arbor-restricted-toy.json \
  --time-limit-seconds 30 \
  --output artifacts/results/ann-arbor-restricted-toy.json
```

La optimalidad corresponde solo al subgrafo, `H` y estimador usados.
No se ha resuelto ni evaluado el rendimiento de la instancia completa de
81 ubicaciones de servicio. Los datos originales, GraphML y resultados
grandes permanecen locales; los ejemplos sintéticos sí viajan con el repo.
