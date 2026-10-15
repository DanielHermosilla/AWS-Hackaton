# evrp-lab

Motor E-VRP "contraído" y laboratorio de experimentos para el desafío CASE (AWS Breaking Barriers Chile 2026).

El motor precalcula caminos de mínima energía sobre la red vial de OSM entre los nodos clave (base, clientes y cargadores). Luego resuelve un MILP con HiGHS en dos fases: primero maximiza las entregas y después minimiza la energía. Cada solución pasa por un validador independiente.

## Uso

```powershell
uv sync --extra ia                     # Python 3.12, dependencias fijadas (+ --extra elevacion para Copernicus)
uv run pytest -q -m "not bedrock"
```

El motor tiene dos etapas que se pueden usar por separado.

| Etapa | Qué hace | Depende de | No depende de |
|---|---|---|---|
| **1. Preparar** (preprocesamiento) | Lee la red vial, ajusta cada punto a la calle y calcula el camino de mínima energía (Dijkstra) para cada par de nodos clave | Mapa, `pipeline.red`, `pipeline.energia` (plano o pendiente), `red.*` (elevación, acceso, algoritmo) | Batería, reserva, SoC, flota, solver |
| **2. Resolver** (solver) | Aplica filtros de batería, poda y cargadores Pareto; corre la heurística, el MILP con HiGHS y el validador independiente | `flota`, `tipos_vehiculo` (B, reserva, SoC, consumo), `cargadores`, `escala`, `solver`, `asesor` | La red (ya resumida) |

### Línea de comandos

```powershell
# Etapa 1 → archivo de instancia preparada (~0,3 MB; ~0,9 MB con --geometria)
uv run evrp preparar --nodes data/competition_routing_nodes.csv --perfil ev_routing `
                     [--red osm|haversine] [--pendiente] [--elevacion eved|usgs|copernicus] [--geometria] `
                     --out results/comp.json.gz

# Etapa 2 → rutas (se puede repetir con otra batería, flota o nodos excluidos, sin volver a preparar)
uv run evrp resolver --instancia results/comp.json.gz --perfil ev_routing `
                     [--vehiculos 3] [--tiempo 30] [--excluir C6 V3] [--pendiente] --out results/comp

# Atajo: etapa 1 + 2
uv run evrp solve --nodes data/competition_routing_nodes.csv --perfil ev_routing --out results/comp
```

En la etapa 2, `--pendiente` debe coincidir con lo usado al preparar; si no, se produce un error. Con terreno plano se puede cambiar el consumo por km al resolver: el camino de mínima energía es el de menor distancia para cualquier consumo.

### Python

```python
import evrp

# Etapa 1
prep: evrp.InstanciaPreparada = evrp.preparar(
    nodos="data/competition_routing_nodes.csv",   # CSV oficial
    config=None,                                   # dict de sobrescritura o ruta a un YAML
    perfiles=["ev_routing"],                       # "eved" | "ev_routing"
    geometria=False)                               # True: guarda los puntos (lat, lon) de cada camino
prep.guardar("results/comp.json.gz")               # .json o .json.gz
prep = evrp.InstanciaPreparada.cargar("results/comp.json.gz")
prep.resumen()                                     # nodos, pares, red, energía, procedencia
prep.a_red()                                       # objeto Red (tramos(i, j), geometria(i, j)) para otros modelos

# Etapa 2
res: evrp.Resultado = evrp.resolver_preparada(
    preparada=prep,                                # o la ruta del archivo
    config={"flota": [{"tipo": "leaf2013", "cantidad": 3}]},
    perfiles=["ev_routing"],
    salida=None,                                   # directorio para routes.json, kpis.json, ...
    excluir=["C6"])                                # nodos a ignorar
res.rutas      # {"1": ["BASE", "V3", ..., "BASE"], ...}
res.kpis       # factible, entregas, energia_total_kwh, km_total, red, solver, tiempo_computo_s
res.detalle    # por vehículo: batería al llegar y al salir, recarga y energía de cada tramo

# Atajo
res = evrp.resolver("data/competition_routing_nodes.csv", perfiles=["eved"])
```

### Formato de la instancia preparada (`evrp.instancia_preparada/1`)

JSON, opcionalmente comprimido con gzip:

```json
{
  "esquema": "evrp.instancia_preparada/1",
  "origen":  {"archivo": "...csv", "sha256_16": "...", "evrp": "0.3.0", "tiempo_s": 5.1},
  "red":     {"tipo": "osm", "vial": true, "grafo": "...graphml", "elevacion": "ninguna", "tiempos": {}},
  "energia_caminos": {"usar_pendiente": false, "consumo_kwh_km": 0.1568, "masa_kg": 1590, "eta_traccion": 0.9, "eta_regeneracion": 0.6},
  "nodos":   [{"id": "BASE", "tipo": "base", "lat": 42.27, "lon": -83.76, "fila": 0, "conectores": [], "puertos": null, "potencia_kw": null, "direccion": "", "operador": ""}],
  "tramos":  {"BASE|V1": [[km, dh_m], [km, dh_m]]},
  "geometrias": {"BASE|V1": [[lat, lon]]}
}
```

`tramos["i|j"]` es la secuencia de tramos elementales del camino i→j, con su largo en km y su desnivel en m. Con eso cualquier modelo puede recalcular la energía con su propio consumo, y usar la instancia como un grafo pequeño de nodos clave. Por ejemplo, el modelo del PDF usaría estos pares como sus "tramos elementales".

- Perfiles de supuestos (`src/evrp/perfiles/`):
  - `eved`: 16 kWh útiles medidos en eVED.
  - `ev_routing`: 24 kWh, los supuestos de la rama `modelamiento` de AWS-Hackaton.
- Mapa vial empaquetado: `src/evrp/assets/osm/ann_arbor_drive.graphml.gz`. Permite correr sin internet. Si los nodos quedan fuera del mapa, intenta descargarlo. La línea recta solo se usa si se activa `red.respaldo_linea_recta`.
- Datos del desafío: copiarlos a `data/`. Esa carpeta está fuera de git.

## Estructura

| Ruta | Contenido |
|---|---|
| `src/evrp/` | Motor: datos, red, energía, instancia contraída, heurística, MILP, validador, pipeline, API (`resolver`, `Motor`) y asesor de IA. |
| `arena/` | Comparación neutral entre motores y solvers. No modifica el código de ninguno. |
| `docs/` | Notas propias, evaluaciones pendientes y resultados de experimentos. |
| `externos/` | Repos de terceros clonados para la arena. Fuera de git. |
