"""Comandos de preparación y resolución reproducibles, sin UI y sin LLM.

``prepare`` combina nodos, calles y estimaciones en un JSON autosuficiente.
``run`` resuelve exactamente ese JSON; no cambia sus parámetros físicos.
La descarga de calles solo ocurre si el usuario pasa ``--download-network``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Sequence

from ev_routing.config import load_config
from ev_routing.contracts import Operations, ProblemInstance, SolverConfig
from ev_routing.energy import fit_distance_rate, integrate_eved_csv
from ev_routing.heuristics import (
    InitialSolution,
    analyze_horizon,
    build_greedy_start,
    build_initial_solution,
)
from ev_routing.inputs import load_instance, load_routing_nodes, save_instance
from ev_routing.network import build_osm_instance
from ev_routing.operations import travel_seconds
from ev_routing.pipeline import run_instance
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.search_policy import BedrockConfig, SearchConfig
from ev_routing.service_graph import (
    PathArchive,
    build_service_graph,
    check_service_context,
    fingerprint,
)


def _movement_limit(value: str) -> int | str:
    if value in {"auto", "none"}:
        return value
    try:
        limit = int(value)
        if limit > 0:
            return limit
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Usar none (sin H), auto heredado o un entero positivo.")


def build_parser() -> argparse.ArgumentParser:
    """Describir las operaciones; no mezclar H con un límite de segundos."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="CSV + calles + energía -> instancia JSON")
    prepare.add_argument("--nodes", required=True, type=Path)
    prepare.add_argument("--graphml", required=True, type=Path, help="Caché vial OSMnx local")
    prepare.add_argument("--download-network", action="store_true")
    prepare.add_argument(
        "--network-profile",
        choices=["drive", "delivery"],
        default="drive",
        help="delivery incluye calles de servicio y pasillos de estacionamiento",
    )
    prepare.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    prepare.add_argument("--max-snap-distance-m", type=float, default=100.0)
    prepare.add_argument("--config", type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--name", default="routing-instance")
    prepare.add_argument("--visit-id", action="append", default=None)
    chargers = prepare.add_mutually_exclusive_group()
    chargers.add_argument("--charger-id", action="append", default=None)
    chargers.add_argument("--no-chargers", action="store_true")
    energy = prepare.add_mutually_exclusive_group(required=True)
    energy.add_argument("--eved", type=Path, help="Calibrar referencia descriptiva con EV")
    energy.add_argument("--energy-rate", type=float, help="Consumo asumido, kWh/km")
    prepare.add_argument("--energy-cache", type=Path)
    prepare.add_argument("--max-gap-seconds", type=float, default=10.0)

    service = commands.add_parser(
        "service-graph", help="Preprocesar caminos: Dijkstra seguro o perfiles de batería y tiempo"
    )
    service.add_argument("--road-instance", required=True, type=Path)
    service.add_argument(
        "--service-movements", default="none", type=_movement_limit,
        help="none prepara para rutas sin H; auto o un entero conservan el formato posicional heredado",
    )
    service.add_argument("--output", required=True, type=Path)
    service.add_argument("--path-archive", required=True, type=Path)
    service.add_argument("--config", type=Path, help="Aplicar operations; no cambiar batería ni flota")
    service.add_argument("--reuse-instance", type=Path, help="Reutilizar un grafo de Dijkstra existente")
    service.add_argument("--reuse-path-archive", type=Path, help="Archivo de sus caminos originales")
    service.add_argument("--cache-directory", type=Path, help="Caché por red, escenario y versión")
    service.add_argument(
        "--max-pair-expansions", type=int, default=64,
        help="Máximo trabajo entrada×salida por intersección; conservar las más costosas",
    )
    service.add_argument(
        "--preprocessing-seconds", type=float, default=10,
        help="Presupuesto blando de contracción; al agotarlo se conserva el grafo restante",
    )

    run = commands.add_parser("run", help="Resolver instancia JSON y comprobar resultado")
    run.add_argument("--instance", required=True, type=Path)
    run.add_argument("--config", type=Path, help="Solo se utiliza la sección solver")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--solver", choices=["scip-routes", "auto", "gurobi", "scip", "gcg"])
    run.add_argument("--time-limit-seconds", type=float)
    run.add_argument("--threads", type=int)
    run.add_argument("--seed", type=int)
    run.add_argument("--tee", action="store_true", help="Mostrar salida nativa del solver")
    run.add_argument("--road-instance", type=Path, help="Red original para auditar la variante")
    run.add_argument("--path-archive", type=Path, help="Caminos de la variante de servicios")
    run.add_argument(
        "--initial-solution", type=Path, help="Incumbente validable vinculado al snapshot exacto"
    )
    run.add_argument("--search-policy", choices=["standard", "deterministic", "adaptive"])
    run.add_argument("--bedrock-model", default=os.getenv("BEDROCK_MODEL_ID"))
    run.add_argument("--bedrock-fast-model", default=os.getenv("BEDROCK_FAST_MODEL_ID"),
                     help="Modelo Bedrock de menor latencia para decisiones durante la búsqueda")
    run.add_argument("--aws-region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    run.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE", "hackathon"))
    run.add_argument("--llm-max-calls", type=int, default=4)
    run.add_argument("--llm-timeout-seconds", type=float, default=8)
    run.add_argument("--llm-fast-timeout-seconds", type=float, default=8)
    run.add_argument("--llm-instance-context-bytes", type=int, default=45000,
                     help="Presupuesto de la instancia enviada; si no cabe se declara el recorte")
    run.add_argument("--llm-max-input-bytes", type=int, default=180000)
    run.add_argument("--no-tree-control", action="store_true",
                     help="Ablación: desactivar callbacks de control, conservando pricing")
    run.add_argument("--llm-max-output-tokens", type=int, default=2048)
    run.add_argument("--llm-reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"],
                     help="Esfuerzo Anthropic; exige un modelo compatible con output_config")
    run.add_argument("--llm-time-fraction", type=float, default=.25)
    run.add_argument("--decision-interval-seconds", type=float, default=15)
    run.add_argument("--solver-log-directory", type=Path)
    run.add_argument("--show-llm-trace", action="store_true",
                     help="Mostrar decisiones y cambios del orquestador sin H")
    return parser


def _prepare(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    nodes = load_routing_nodes(args.nodes)
    visit_ids = {node.node_id for node in nodes if node.node_type == "visit"}
    charger_ids = {node.node_id for node in nodes if node.node_type == "charger"}
    for requested, known, kind in (
        (args.visit_id, visit_ids, "cliente"),
        (args.charger_id, charger_ids, "cargador"),
    ):
        unknown = set(requested or []) - known
        if unknown:
            raise ValueError(f"IDs de {kind} desconocidos: {sorted(unknown)}")
    # Los subconjuntos sirven para ensayos. Se registran para no confundirlos
    # con la instancia oficial completa de 20 entregas.
    selected = [
        node
        for node in nodes
        if node.node_type == "base"
        or (
            node.node_type == "visit"
            and (args.visit_id is None or node.node_id in args.visit_id)
        )
        or (
            node.node_type == "charger"
            and not args.no_chargers
            and (args.charger_id is None or node.node_id in args.charger_id)
        )
    ]
    if args.eved is not None:
        summary = integrate_eved_csv(
            args.eved,
            max_gap_seconds=args.max_gap_seconds,
            cache_path=args.energy_cache,
        )
        energy_model = fit_distance_rate(summary)
        rate = energy_model.kwh_per_km
        energy_provenance = energy_model.model_dump(mode="json")
    else:
        rate = args.energy_rate
        energy_provenance = {
            "kind": "user_supplied_distance_rate",
            "kwh_per_km": rate,
            "limitations": ["Coeficiente supuesto por el usuario, no calibrado con eVED."],
        }
    instance = build_osm_instance(
        selected,
        config.model,
        rate,
        graphml_path=args.graphml,
        allow_download=args.download_network,
        network_profile=args.network_profile,
        bbox=tuple(args.bbox) if args.bbox else None,
        max_snap_distance_m=args.max_snap_distance_m,
        name=args.name,
    )
    instance.provenance.update(
        routing_csv_sha256=hashlib.sha256(args.nodes.read_bytes()).hexdigest(),
        selected_visit_ids=[n.node_id for n in selected if n.node_type == "visit"],
        selected_charger_ids=[n.node_id for n in selected if n.node_type == "charger"],
        energy_model=energy_provenance,
        capacity_note="Capacidad útil y reserva configuradas; no medidas por este programa.",
    )
    instance = ProblemInstance.model_validate({**dict(instance), "operations": config.operations})
    save_instance(instance, args.output)
    print(
        json.dumps(
            {
                "instance_path": str(args.output),
                "nodes": len(instance.nodes),
                "arcs": len(instance.arcs),
                "deliveries": len(instance.customer_ids),
                "energy_kwh_per_km": rate,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance)
    values = load_config(args.config).solver.model_dump()
    for key in ("solver", "time_limit_seconds", "threads", "seed"):
        if getattr(args, key) is not None:
            values[key] = getattr(args, key)
    if args.tee:
        values["tee"] = True
    extra = {}
    if args.search_policy is not None and values["solver"] not in {"gcg", "scip-routes"}:
        raise ValueError("--search-policy requiere --solver scip-routes o gcg")
    if values["solver"] in {"gcg", "scip-routes"}:
        extra["search_config"] = SearchConfig(
            policy=args.search_policy or "standard",
            bedrock=BedrockConfig(
                model_id=args.bedrock_model, region=args.aws_region,
                profile=args.aws_profile or None, timeout_seconds=args.llm_timeout_seconds,
                max_output_tokens=args.llm_max_output_tokens,
                reasoning_effort=args.llm_reasoning_effort,
                fast_model_id=args.bedrock_fast_model,
                fast_timeout_seconds=args.llm_fast_timeout_seconds,
                max_input_bytes=args.llm_max_input_bytes,
            ),
            max_llm_calls=args.llm_max_calls,
            llm_time_fraction=args.llm_time_fraction,
            decision_interval_seconds=args.decision_interval_seconds,
            log_directory=str(args.solver_log_directory) if args.solver_log_directory else None,
            show_llm_trace=args.show_llm_trace,
            instance_context_bytes=args.llm_instance_context_bytes,
            tree_control=not args.no_tree_control,
        )
    if args.road_instance is not None:
        extra["road_instance"] = load_instance(args.road_instance)
    if args.path_archive is not None:
        extra["path_archive"] = PathArchive.model_validate_json(args.path_archive.read_text())
    if args.initial_solution is not None:
        initial = InitialSolution.model_validate_json(args.initial_solution.read_text())
        if initial.instance_sha256 != fingerprint(instance):
            raise ValueError("La solución inicial no corresponde al snapshot seleccionado")
        if initial.solution is not None:
            extra["initial_solution"] = initial.solution
    result = run_instance(
        instance, SolverConfig.model_validate(values), output_path=args.output, **extra
    )
    print(
        json.dumps(
            {
                "result_path": str(args.output),
                "status": result["status"],
                "solver": result["solve"]["used_solver"],
                "deliveries": result["kpis"]["served_deliveries"],
                "net_battery_energy_kwh": result["kpis"]["net_battery_energy_kwh"],
                "lexicographic_optimal": result["solve"]["lexicographic_optimal"],
                "movement_limit": result["formulation"]["movement_limit_used"],
                "initial_solution_provided": result["initial_solution"]["provided"],
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0 if result["kpis"]["feasible"] else 1


def _service_graph(args: argparse.Namespace) -> int:
    road = load_instance(args.road_instance)
    automatic = args.service_movements == "auto"
    without_h = args.service_movements == "none"
    preprocessing_started = time.perf_counter()
    if bool(args.reuse_instance) != bool(args.reuse_path_archive):
        raise ValueError("--reuse-instance y --reuse-path-archive deben proporcionarse juntos")
    if args.reuse_instance is not None:
        compact = load_instance(args.reuse_instance)
        archive = PathArchive.model_validate_json(args.reuse_path_archive.read_text())
        check_service_context(compact, road, archive)
    else:
        if without_h:
            compact, archive = prepare_service_graph(
                road, operations=load_config(args.config).operations if args.config else None,
                cache_directory=args.cache_directory,
                max_pair_expansions=args.max_pair_expansions,
                preprocessing_seconds=args.preprocessing_seconds,
            )
        else:
            compact, archive = build_service_graph(road, 1 if automatic else args.service_movements)
    options = load_config(args.config).operations if args.config is not None else compact.operations
    resource_paths = compact.provenance.get("representation", {}).get("kind") == "resource_paths"
    if resource_paths:
        if not without_h:
            raise ValueError("Los perfiles requieren --service-movements none y scip-routes")
        if options != compact.operations:
            raise ValueError("Cambiar el escenario requiere regenerar perfiles; usar --cache-directory")
    elif options.max_route_seconds is not None:
        compact.provenance["representation"]["road_optimum_preserved"] = False
    # Los tiempos explícitos de cada calle prevalecen sobre la velocidad asumida.
    # Completar arcos sin tiempo sobre los mismos caminos, sin ejecutar Dijkstra.
    if options.timing_enabled and not resource_paths:
        segments = {(a.from_node_id, a.to_node_id): a for a in road.arcs}
        paths = {(p.from_node_id, p.to_node_id): p.node_ids for p in archive.paths}
        completed = []
        for arc in compact.arcs:
            sequence = paths[arc.from_node_id, arc.to_node_id]
            duration = sum(
                travel_seconds(segments[pair], options) for pair in zip(sequence, sequence[1:])
            )
            completed.append(arc.model_copy(update={"travel_time_seconds": duration}))
        compact = compact.model_copy(update={"arcs": completed})
    elif args.config is not None and not resource_paths:
        # Evitar conservar tiempos derivados de la velocidad de otro escenario.
        segments = {(a.from_node_id, a.to_node_id): a for a in road.arcs}
        paths = {(p.from_node_id, p.to_node_id): p.node_ids for p in archive.paths}
        for arc in compact.arcs:
            sequence = paths[arc.from_node_id, arc.to_node_id]
            times = [segments[pair].travel_time_seconds for pair in zip(sequence, sequence[1:])]
            arc.travel_time_seconds = sum(times) if all(t is not None for t in times) else None
    compact = ProblemInstance.model_validate({**dict(compact), "operations": options})
    preprocessing_seconds = time.perf_counter() - preprocessing_started
    if without_h:
        # movement_limit permanece solo por compatibilidad con snapshots 1.0.
        # No elegirlo, certificarlo ni usarlo para construir un arranque.
        compact.provenance["horizon_selection"] = {
            "mode": "none", "effective_horizon": None, "movement_limit_used": None,
        }
        if not compact.provenance["representation"].get("road_optimum_preserved"):
            compact.provenance["representation"]["optimality_scope"] = (
                "Rutas sin H sobre los caminos fijos disponibles; no toda la red vial."
            )
        archive.service_instance_sha256 = fingerprint(compact)
        save_instance(compact, args.output)
        args.path_archive.parent.mkdir(parents=True, exist_ok=True)
        args.path_archive.write_text(archive.model_dump_json() + "\n", encoding="utf-8")
        initial_path = args.output.with_suffix(".start.json")
        initial_path.write_text(InitialSolution(
            instance_sha256=fingerprint(compact), solution=None,
        ).model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "instance_path": str(args.output), "path_archive": str(args.path_archive),
            "nodes": len(compact.nodes), "arcs": len(compact.arcs),
            "deliveries": len(compact.customer_ids), "chargers": len(compact.charger_ids),
            "vehicles": len(compact.vehicle_ids), "service_movements": None,
            "formulation": "complete_routes_without_h", "preprocessing_seconds": preprocessing_seconds,
            "reused_service_graph": args.reuse_instance is not None,
            "initial_solution_path": str(initial_path),
            "preprocessing": compact.provenance["representation"],
            "cache": compact.provenance.get("preprocessing_cache"),
        }, ensure_ascii=False))
        return 0
    analysis = analyze_horizon(compact)
    report_path = args.output.with_suffix(".horizon.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(analysis.model_dump_json(indent=2) + "\n", encoding="utf-8")
    if automatic and analysis.recommended_horizon is None:
        raise ValueError(
            f"No se certificó un H pequeño: {analysis.reason} "
            f"Cota estructural: {analysis.structural_upper_bound}. Informe: {report_path}. "
            "No se construyó el MILP. Un --service-movements entero permite un ensayo "
            "explícito, cuyo certificado quedará condicionado a ese límite."
        )
    h = analysis.recommended_horizon if automatic else args.service_movements
    compact.parameters.movement_limit = h
    certified_bound = analysis.recommended_horizon or analysis.structural_upper_bound
    compact.provenance["horizon_selection"] = {
        "mode": "auto" if automatic else "manual",
        "effective_horizon": h,
        "certified_sufficient": certified_bound is not None and h >= certified_bound,
        "certified_minimal": analysis.minimum_horizon == h,
        "analysis": analysis.model_dump(exclude={"tour"}),
    }
    archive.service_instance_sha256 = fingerprint(compact)
    initial_started = time.perf_counter()
    witness = build_initial_solution(compact, analysis.tour)
    initial_method = "horizon_witness"
    if witness is None and compact.operations != Operations():
        witness = build_greedy_start(compact)
        initial_method = "greedy_feasible_partial"
    initial_seconds = time.perf_counter() - initial_started
    compact.provenance["initial_solution_construction"] = {
        "method": initial_method, "runtime_seconds": initial_seconds,
        "delivered_count": len(witness.served_visit_ids) if witness else None,
        "certifies_horizon": False,
    }
    compact.provenance["operational_assumptions"] = {
        "travel_time_source": "road_arc_time_or_explicit_assumed_speed",
        "charging_power_source": "user_configured_effective_grid_power",
        "energy_margin_kind": "deterministic_scenario_not_probability_guarantee",
        "fixed_paths": True,
    }
    archive.service_instance_sha256 = fingerprint(compact)
    initial = InitialSolution(instance_sha256=fingerprint(compact), solution=witness)
    save_instance(compact, args.output)
    initial_path = args.output.with_suffix(".start.json")
    initial_path.write_text(initial.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args.path_archive.parent.mkdir(parents=True, exist_ok=True)
    args.path_archive.write_text(archive.model_dump_json() + "\n", encoding="utf-8")
    k, h, n, a, c = (
        compact.parameters.vehicle_count, compact.parameters.movement_limit,
        len(compact.nodes), len(compact.arcs) + 1, len(compact.customer_ids),
    )
    print(json.dumps({
        "instance_path": str(args.output), "path_archive": str(args.path_archive),
        "nodes": n, "arcs": a - 1, "deliveries": c,
        "chargers": len(compact.charger_ids), "vehicles": k,
        "service_movements": h,
        "road_nodes": len(road.nodes), "road_arcs": len(road.arcs),
        "preprocessing_seconds": preprocessing_seconds,
        "shortest_path_algorithm": compact.provenance["representation"]["shortest_path_algorithm"],
        "unreachable_ordered_service_pairs": (
            compact.provenance["representation"]["unreachable_ordered_service_pairs"]
        ),
        "binary_variables": k * (a * h + n * (h + 1) + c * h + h) + c,
        "horizon_analysis_path": str(report_path),
        "horizon_certified": compact.provenance["horizon_selection"]["certified_sufficient"],
        "heuristic_runtime_seconds": analysis.runtime_seconds,
        "initial_solution_runtime_seconds": initial_seconds,
        "reused_service_graph": args.reuse_instance is not None,
        "initial_solution_path": str(initial_path),
        "initial_solution_energy_kwh": initial.solution.net_energy_kwh if initial.solution else None,
        "optimality_scope": compact.provenance["representation"]["optimality_scope"],
    }, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Códigos: 0 resultado válido, 1 sin ruta validada, 2 entrada/ejecución errónea."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            return _prepare(args)
        if args.command == "service-graph":
            return _service_graph(args)
        return _run(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(
            json.dumps({"error": str(error), "type": type(error).__name__}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
