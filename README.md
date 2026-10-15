# evrp-lab

Motor E-VRP "contraído" y laboratorio de experimentos para el desafío CASE (AWS Breaking Barriers Chile 2026).

El motor precalcula caminos de mínima energía sobre la red vial de OSM entre los nodos clave (base, clientes y cargadores). Luego resuelve un MILP con HiGHS en dos fases: primero maximiza las entregas y después minimiza la energía. Cada solución pasa por un validador independiente.

## Uso

```powershell
uv sync --extra ia                     # Python 3.12, dependencias fijadas
uv run evrp solve --nodes data/competition_routing_nodes.csv --perfil ev_routing --out results/comp
uv run pytest -q
```

Como módulo:

```python
from evrp import resolver
res = resolver("data/competition_routing_nodes.csv", perfiles=["eved"])
res.rutas, res.kpis
```

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
