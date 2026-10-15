# Cómo leer el proyecto

Flujo vigente: **CSV/GraphML → instancia → rutas sin H → SCIP → validación → JSON**.
Pyomo/Gurobi/SCIP y GCG posicional se conservan como referencias explícitas.

| Archivo | Funciones principales / propósito |
|---|---|
| `modelamiento.pdf` | Modelo matemático que implementamos. |
| `modelamiento.tex` | Fuente editable: referencia posicional (1)–(24) y maestro sin H (25)–(29). |
| `diccionario.md` | Significado y unidades de los datos eVED. |
| `config/default.json` | Parámetros físicos y recursos del solver. |
| `config/operations.example.json` | Escenario operacional ilustrativo, explícitamente parametrizado. |
| `src/ev_routing/contracts.py` | Objetos validados: `ProblemInstance`, `SolverConfig`, rutas y resultados. |
| `src/ev_routing/config.py` | `load_config`: lee configuración JSON. |
| `src/ev_routing/inputs.py` | `load_routing_nodes`, `load_instance`, `save_instance`: entradas y snapshots. |
| `src/ev_routing/energy.py` | `integrate_eved_csv`, `fit_distance_rate`: integra energía y estima kWh/km. |
| `src/ev_routing/network.py` | `build_osm_instance`, `build_instance_from_graph`: calles y accesos de servicio. |
| `src/ev_routing/service_graph.py` | `build_service_graph`: Dijkstra de SciPy/CSR entre servicios; `expand_and_validate`: auditoría de las calles originales. |
| `src/ev_routing/simulation.py` | Añade clientes sintéticos reproducibles en nodos viales conectados al depósito, preservando la red, energía y servicios originales. |
| `src/ev_routing/heuristics.py` | `analyze_horizon`, `build_initial_solution`, `build_greedy_start`: certificado de H cuando aplica e incumbentes validados, sin MILP. |
| `src/ev_routing/operations.py` | Margen de energía, tiempos y calendario más temprano de rutas fijas. |
| `src/ev_routing/model.py` | `build_model`, `activate_energy_phase`, `extract_solution`: ecuaciones del PDF. |
| `src/ev_routing/solve.py` | `solve_instance`: dos fases; Gurobi primero, SCIP si no está disponible/licenciado. |
| `src/ev_routing/route_solver.py` | Maestro sin H, pricing SCIP/Farkas, cortes de ternas y reducción certificada DFJ. |
| `src/ev_routing/route_resources.py` | Etiquetas con poliedros de recursos continuos, dominancia y reconstrucción física. |
| `src/ev_routing/route_policy.py` | Una decisión Bedrock previa a ambas fases; acciones cerradas y fallback. |
| `src/ev_routing/dw.py` | `solve_dantzig_wolfe`: dos fases con GCG, recuperación y cotas originales. |
| `src/ev_routing/dw_bridge.py` | Traducción lineal Pyomo/GCG y dos particiones de restricciones. |
| `src/ev_routing/dw_callbacks.py` | Observación de pricing, selección de cortes nativos y aplicación de políticas. |
| `src/ev_routing/search_policy.py` | Contratos, política determinista y controlador adaptativo acotado. |
| `src/ev_routing/llm/bedrock.py` | Bedrock Converse, perfil/configuración externa y respuestas JSON. |
| `src/ev_routing/benchmark.py` | Procesos pareados, hashes, reanudación y resúmenes CSV/JSON. |
| `src/ev_routing/validation.py` | `validate_solution`: reproduce recorridos y batería sin usar Pyomo. |
| `src/ev_routing/metrics.py` | `compute_metrics`: entregas, energía, recargas y distancia verificadas. |
| `src/ev_routing/pipeline.py` | `run_instance`: une resolución, validación y salida JSON. |
| `src/ev_routing/cli.py` | `main`: comandos `prepare`, `service-graph` y `run`. |
| `src/ev_routing/llm/tuning.py` | `build_tuning_request`, `propose_tuning`: esqueleto futuro, desactivado. |
| `scripts/prepare_hackathon.sh` | Prepara los datos completos; conserva el error original y no lanza el solver. |
| `scripts/run_pptx.sh` | Ejecuta todos los servicios con caminos precalculados; dos fases y auditoría vial. |
| `scripts/benchmark_dw.sh` | Benchmark sin H: estándar, determinista y adaptativo mediante Bedrock. |
| `scripts/test_clients.sh`, `scripts/test_routing_verbose.py` | Corrida con SCIP en vivo, prompt exacto, respuesta LLM y cambios efectivos; `--simulate-customers` permite aumentar la demanda. `test_20_clients.sh` conserva el alias original. |
| `examples/` | Dos instancias sintéticas pequeñas con óptimo conocido. |
| `tests/` | Pruebas de datos, modelo, solvers, auditoría y flujo completo. |
| `tests/oracle.py` | Enumeración independiente de casos pequeños para contrastar el MILP. |
| `docs/model.md` | Correspondencia entre ecuaciones del PDF y código Pyomo. |
| `docs/service-graph.md` | Variante para las 81 ubicaciones: supuestos, límite de traslados y certificados. |
| `docs/heuristics.md` | H automático, condiciones de la prueba y arranque de Gurobi/SCIP. |
| `docs/solvers.md` | Licencias, fallback, tiempos y certificados por fase. |
| `docs/dantzig-wolfe.md` | Formulación descompuesta, decisiones admitidas, presupuesto y benchmark. |
| `docs/llm4mip-adaptation.md` | Material reutilizado, cambios, licencia y alcance. |
| `docs/contracts.md` | Campos de entrada/salida y sus límites. |
| `docs/validation.md` | Pruebas ejecutadas, resultados y límites de los ensayos. |
| `artifacts/` | Resultados y cachés locales, fuera de Git. |

Instalación y ejemplos ejecutables: [README.md](README.md).
Reglas para colaborar: [AGENTS.md](AGENTS.md).
