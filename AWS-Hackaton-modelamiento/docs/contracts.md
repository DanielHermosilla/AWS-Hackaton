# Contratos mínimos

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
`schema_version="1.0"` y `tuning.status="disabled"`. Los campos desconocidos
por falta de datos se expresan como `null`, nunca como `NaN` o un ahorro cero.

Cada ruta conserva **H+1 posiciones**, incluidas permanencias en el depósito.
La última posición no tiene recarga, arco siguiente ni consumo de movimiento.
Las entregas están en `delivered_visit_ids`; visitar físicamente el nodo no
alcanza para considerarlo atendido.

`prepare` escribe un snapshot autosuficiente del problema.
`run --config ...` utiliza solamente la sección `solver`: el escenario físico
se toma del snapshot, para evitar cambios silenciosos.

## Datos y límites

- Los CSV de nodos contienen ubicaciones de servicio, no calles.
- La energía eVED se integra por `(VehId, Trip)` y tiempo real.
- El estimador inicial usa kWh/km descriptivos de los EV históricos. No es una
  predicción de pendientes, clima o regeneración en cada calle.
- Un GraphML OSMnx suministra las calles dirigidas. Los accesos de servicio
  son conectores bidireccionales supuestos, acotados y registrados.
- Los arcos paralelos se subdividen para preservar sus alternativas. Esto
  aumenta movimientos y por tanto afecta la elección de H.
- La validez física se refiere a estas energías, accesos, red y H. No certifica
  el consumo real futuro ni la optimalidad en una red más amplia.
