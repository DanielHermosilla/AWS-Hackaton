# Cómo leer el proyecto

Flujo: **CSV/GraphML → instancia JSON → Pyomo → Gurobi/SCIP → verificación → JSON**.
No hay llamadas al LLM.

| Archivo | Funciones principales / propósito |
|---|---|
| `modelamiento.pdf` | Modelo matemático que implementamos. |
| `diccionario.md` | Significado y unidades de los datos eVED. |
| `config/default.json` | Parámetros físicos y recursos del solver. |
| `src/ev_routing/contracts.py` | Objetos validados: `ProblemInstance`, `SolverConfig`, rutas y resultados. |
| `src/ev_routing/config.py` | `load_config`: lee configuración JSON. |
| `src/ev_routing/inputs.py` | `load_routing_nodes`, `load_instance`, `save_instance`: entradas y snapshots. |
| `src/ev_routing/energy.py` | `integrate_eved_csv`, `fit_distance_rate`: integra energía y estima kWh/km. |
| `src/ev_routing/network.py` | `build_osm_instance`, `build_instance_from_graph`: calles y accesos de servicio. |
| `src/ev_routing/model.py` | `build_model`, `activate_energy_phase`, `extract_solution`: ecuaciones del PDF. |
| `src/ev_routing/solve.py` | `solve_instance`: dos fases; Gurobi primero, SCIP si no está disponible/licenciado. |
| `src/ev_routing/validation.py` | `validate_solution`: reproduce recorridos y batería sin usar Pyomo. |
| `src/ev_routing/metrics.py` | `compute_metrics`: entregas, energía, recargas y distancia verificadas. |
| `src/ev_routing/pipeline.py` | `run_instance`: une resolución, validación y salida JSON. |
| `src/ev_routing/cli.py` | `main`: comandos `prepare` y `run`. |
| `src/ev_routing/llm/tuning.py` | `build_tuning_request`, `propose_tuning`: esqueleto futuro, desactivado. |
| `examples/` | Dos instancias sintéticas pequeñas con óptimo conocido. |
| `tests/` | Pruebas de datos, modelo, solvers, auditoría y flujo completo. |
| `tests/oracle.py` | Enumeración independiente de casos pequeños para contrastar el MILP. |
| `docs/model.md` | Correspondencia entre ecuaciones del PDF y código Pyomo. |
| `docs/solvers.md` | Licencias, fallback, tiempos y certificados por fase. |
| `docs/contracts.md` | Campos de entrada/salida y sus límites. |
| `docs/validation.md` | Pruebas ejecutadas, resultados y límites de los ensayos. |
| `artifacts/` | Resultados y cachés locales, fuera de Git. |

Instalación y ejemplos ejecutables: [README.md](README.md).
Reglas para colaborar: [AGENTS.md](AGENTS.md).
