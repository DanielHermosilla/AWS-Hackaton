# Cómo leer el proyecto

Flujo vigente: **CSV/GraphML → instancia → rutas sin H → SCIP → validación → JSON**.
Pyomo/Gurobi/SCIP y GCG posicional se conservan como referencias explícitas.

| Archivo | Funciones principales / propósito |
|---|---|
| `modelamiento.pdf` | Modelo matemático que implementamos. |
| `modelamiento.tex` | Fuente editable: referencia posicional (1)–(24), maestro sin H (25)–(29) y perfiles (30)–(31). |
| `diccionario.md` | Significado y unidades de los datos eVED. |
| `config/default.json` | Parámetros físicos y recursos del solver. |
| `config/operations.example.json` | Escenario operacional ilustrativo, explícitamente parametrizado. |
| `src/ev_routing/contracts.py` | Objetos validados: `ProblemInstance`, `SolverConfig`, rutas y resultados. |
| `src/ev_routing/config.py` | `load_config`: lee configuración JSON. |
| `src/ev_routing/inputs.py` | `load_routing_nodes`, `load_instance`, `save_instance`: entradas y snapshots. |
| `src/ev_routing/energy.py` | `integrate_eved_csv`, `fit_distance_rate`: integra energía y estima kWh/km. |
| `src/ev_routing/network.py` | `build_osm_instance`, `build_instance_from_graph`: calles y accesos de servicio. |
| `src/ev_routing/service_graph.py` | `build_service_graph`: Dijkstra de SciPy/CSR entre servicios; `expand_and_validate`: auditoría de las calles originales. |
| `src/ev_routing/resource_graph.py` | `prepare_service_graph`: selecciona Dijkstra seguro o contracción con perfiles, conserva alternativas y nodos pendientes, caché por contenido. |
| `src/ev_routing/simulation.py` | Añade clientes sintéticos reproducibles en nodos viales conectados al depósito, preservando la red, energía y servicios originales. |
| `src/ev_routing/heuristics.py` | `analyze_horizon`, `build_initial_solution`, `build_greedy_start`: certificado de H cuando aplica e incumbentes validados, sin MILP. |
| `src/ev_routing/operations.py` | Margen de energía, tiempos y calendario más temprano de rutas fijas. |
| `src/ev_routing/model.py` | `build_model`, `activate_energy_phase`, `extract_solution`: ecuaciones del PDF. |
| `src/ev_routing/solve.py` | `solve_instance`: fases lexicográficas; `scip-routes` predeterminado, referencias heredadas explícitas. |
| `src/ev_routing/route_solver.py` | Maestro sin H, pricing SCIP/Farkas, cortes de ternas y reducción certificada DFJ. |
| `src/ev_routing/route_resources.py` | Etiquetas con poliedros de recursos continuos, dominancia y reconstrucción física. |
| `src/ev_routing/route_policy.py` | Esquema de acciones implementadas y prompt del orquestador. |
| `src/ev_routing/llm_head.py` | Cabeza Bedrock asíncrona, instancia física, MPS, presupuestos y decisiones vencidas. |
| `src/ev_routing/route_callbacks.py` | Eventos, branching, selección de nodos, separación compatible y sub-SCIP primal. |
| `src/ev_routing/route_pricing.py` | Potenciales del multigrafo, reparación física y cotas de completación por dual. |
| `src/ev_routing/route_hybrid.py` | ALNS, población memética, recombinación y reparación sobre nodos de pricing. |
| `src/ev_routing/route_portfolio.py`, `route_wave_schedule.py`, `route_electric_local.py` | Construcción por grupos y ventanas, asignación por oleadas y mejora eléctrica reanudable. |
| `src/ev_routing/route_hints.py` | Contexto estructural y validación de propuestas de recorridos del LLM. |
| `src/ev_routing/route_schedule.py` | Reparación primal mediante LP de recargas y horarios sobre caminos candidatos; validación física y fallback al oráculo general. |
| `src/ev_routing/route_orchestrator.py` | Referencia anterior de decisiones Bedrock entre etapas. |
| `src/ev_routing/route_heuristics.py` | Inserción, búsqueda local, ruin/repair, recarga parcial, partición y pricing heurístico. |
| `src/ev_routing/route_relaxation.py` | Cotas inferiores de asignación y tour sin recursos; no sustituye el maestro físico. |
| `src/ev_routing/scip_tuning.py` | Catálogo instalado, validación y aplicación de presets/parámetros nativos. |
| `src/ev_routing/dw.py` | `solve_dantzig_wolfe`: dos fases con GCG, recuperación y cotas originales. |
| `src/ev_routing/dw_bridge.py` | Traducción lineal Pyomo/GCG y dos particiones de restricciones. |
| `src/ev_routing/dw_callbacks.py` | Observación de pricing, selección de cortes nativos y aplicación de políticas. |
| `src/ev_routing/search_policy.py` | Contratos, política determinista y controlador adaptativo acotado. |
| `src/ev_routing/llm/bedrock.py` | Bedrock Converse, esfuerzo específico de GPT/Anthropic, perfil externo y respuestas JSON. |
| `src/ev_routing/benchmark.py` | Procesos pareados, hashes, reanudación y resúmenes CSV/JSON. |
| `src/ev_routing/synthetic_instances.py` | Redes por zonas con energía/tiempo, ventanas y testigo factible separado del solver. |
| `src/ev_routing/synthetic_benchmark.py` | Piloto sin LLM, política congelada y comparación de cuatro modos en instancias nuevas. |
| `src/ev_routing/presentation_benchmark.py`, `presentation_impact.py` | Campañas con controles locales, ablación del LLM y deltas auditables de energía, CO₂ y USD. |
| `src/ev_routing/validation.py` | `validate_solution`: reproduce recorridos y batería sin usar Pyomo. |
| `src/ev_routing/metrics.py` | `compute_metrics`: entregas, energía, recargas y distancia verificadas. |
| `src/ev_routing/pipeline.py` | `run_instance`: une resolución, validación y salida JSON. |
| `src/ev_routing/cli.py` | `main`: comandos `prepare`, `service-graph` y `run`. |
| `src/ev_routing/llm/tuning.py` | `build_tuning_request`, `propose_tuning`: esqueleto futuro, desactivado. |
| `scripts/prepare_hackathon.sh` | Prepara los datos completos; conserva el error original y no lanza el solver. |
| `scripts/run_pptx.sh` | Ejecuta todos los servicios con caminos precalculados; dos fases y auditoría vial. |
| `scripts/benchmark_dw.sh` | Benchmark sin H: estándar, determinista y adaptativo mediante Bedrock. |
| `scripts/benchmark_llm.sh` | Entrada reproducible al generador, piloto y comparación sintética. |
| `scripts/benchmark_presentation.sh` | Plan, ejecución y reporte de campañas nuevas; usa caffeinate en macOS. |
| `scripts/reproduce_benchmark_20261016.sh` | Repetición portable de la cohorte C con el commit histórico, sin cambiar de rama. |
| `scripts/test_clients.sh`, `scripts/test_routing_verbose.py` | Corrida con SCIP en vivo y decisiones LLM registradas; `--simulate-customers` permite aumentar la demanda. `test_20_clients.sh` conserva el alias original. |
| `examples/` | Dos instancias sintéticas pequeñas con óptimo conocido. |
| `tests/` | Pruebas de datos, modelo, solvers, auditoría y flujo completo. |
| `tests/oracle.py` | Enumeración independiente de casos pequeños para contrastar el MILP. |
| `docs/model.md` | Correspondencia entre ecuaciones del PDF y código Pyomo. |
| `docs/service-graph.md` | Variante para las 81 ubicaciones: supuestos, límite de traslados y certificados. |
| `docs/resource-paths.md` | Perfiles de batería, dominancia, presupuesto de compresión y alcance de equivalencia vial sin H. |
| `scripts/benchmark_resource_paths.py` | A/B de preparación y pricing, casos sintéticos y red local opcional, sin AWS. |
| `docs/heuristics.md` | H automático, condiciones de la prueba y arranque de Gurobi/SCIP. |
| `docs/solvers.md` | Licencias, fallback, tiempos y certificados por fase. |
| `docs/dantzig-wolfe.md` | Formulación descompuesta, decisiones admitidas, presupuesto y benchmark. |
| `docs/orchestration.md` | Flujo del orquestador, acciones, presupuestos y demostración de las cotas energéticas. |
| `docs/llm-head-search.md` | Integración actual, API de SCIP, trazabilidad, validación y mediciones. |
| `docs/webapp-integration.md` | Gap energético 0,5 %, GPT-5.6 Luna probado en AWS, API Python y cambios para el futuro merge con webapp. |
| `docs/performance-orchestrator.md` | Comparación medida, acceso real a modelos Bedrock, hashes y límites de la evidencia. |
| `docs/benchmark-llm.md` | Comandos, familias sintéticas, métricas y controles de la evaluación del LLM. |
| `docs/benchmarks/2026-10-16/` | PDF, gráficos, CSV y procedencia de las 436 corridas; originales masivos fuera de Git. |
| `docs/solver-repair.md` | Diagnóstico del incumplimiento, correcciones lexicográficas y mediciones entre versiones del solver. |
| `docs/llm4mip-adaptation.md` | Material reutilizado, cambios, licencia y alcance. |
| `docs/contracts.md` | Campos de entrada/salida y sus límites. |
| `docs/validation.md` | Pruebas ejecutadas, resultados y límites de los ensayos. |
| `artifacts/` | Resultados y cachés locales, fuera de Git. |

Instalación y ejemplos ejecutables: [README.md](README.md).
Reglas para colaborar: [AGENTS.md](AGENTS.md).

## Webapp integrada en main

- `backend/service.py`: contrato HTTP 3.0, validación estricta y mismo pipeline nativo.
- `backend/runtime.py`: GraphML del operador, contextos viales acotados y política GPT de Bedrock.
- `backend/daniel_adapter.py`: resultado nativo íntegro, rutas expandidas y geometría por `arc_id`.
- `backend/local_server.py`: servidor loopback, mismo origen, límites y resultados temporales.
- `webapp/`: Inicio/Plan, entrada, mapa vial, KPIs, certificados, decisiones GPT y descargas.
- `tests/test_integrated_webapp.py` y `webapp/tests/merged-engine.test.mjs`: cobertura del merge.
- `docs/webapp-integration.md`: arranque, arquitectura y límites; `docs/main-integration-validation.md`: evidencia.
