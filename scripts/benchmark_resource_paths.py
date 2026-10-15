"""A/B reproducible: red vial, perfiles, Dijkstra aplicable y caché.

No descarga mapas, no llama a AWS y no aprende de evaluation. Los corredores
son sintéticos; --road-instance permite medir una red local por separado.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from time import monotonic, perf_counter

from research_service_paths import make_window_instance

from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    Operations,
    ProblemInstance,
    SolverConfig,
)
from ev_routing.inputs import load_instance
from ev_routing.pipeline import run_instance
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.route_resources import RouteOracle, assemble_solution
from ev_routing.service_graph import build_service_graph, expand_and_validate, fingerprint
from ev_routing.validation import validate_solution


def corridor(segments=80):
    nodes = [Node(node_id="0", node_type="base"), Node(node_id="C", node_type="visit")]
    arcs = []
    for name, energies, seconds in [
        ("slow", [-.25, .25] * (segments // 2), 10),
        ("fast", [.025] * segments, 1),
    ]:
        walk = ["0", *[f"{name}_{i}" for i in range(segments - 1)], "C"]
        nodes.extend(Node(node_id=i, node_type="junction") for i in walk[1:-1])
        arcs.extend(Arc(
            from_node_id=a, to_node_id=b, energy_kwh=e, distance_m=20,
            travel_time_seconds=seconds,
        ) for a, b, e in zip(walk, walk[1:], energies))
    arcs.append(Arc(from_node_id="C", to_node_id="0", energy_kwh=1, travel_time_seconds=30))
    return ProblemInstance(
        name=f"synthetic-parallel-corridors-{segments}", nodes=nodes, arcs=arcs,
        parameters=ModelParameters(vehicle_count=1, battery_capacity_kwh=10, reserve_kwh=1),
        operations=Operations(
            max_route_seconds=120, use_customer_time_windows=True,
            customer_time_windows={"C": {"open_seconds": 0, "close_seconds": 90}},
        ),
    )


def oracle_run(instance):
    started = perf_counter()
    oracle = RouteOracle(instance, instance.vehicle_ids[0])
    oracle.exhaust(monotonic() + 10)
    if not oracle.complete:
        raise RuntimeError("Oráculo interrumpido: no publicar una comparación de óptimos")
    mask, route = min(oracle.routes.items(), key=lambda pair: (
        -pair[0].bit_count(), pair[1].net_energy_kwh,
    ))
    solution = assemble_solution(instance, [route])
    report = validate_solution(instance, solution, enforce_movement_limit=False)
    if not report.feasible:
        raise RuntimeError(report.violations)
    return {
        "seconds": perf_counter() - started, "expanded_labels": oracle.expanded,
        "deliveries": mask.bit_count(), "energy_kwh": route.net_energy_kwh,
        "complete": oracle.complete,
    }, solution


def synthetic(road, repeats):
    full, reduced, preparation, total = [], [], [], []
    for _ in range(repeats):
        baseline, _ = oracle_run(road)
        full.append(baseline)
        start = perf_counter()
        compact, archive = prepare_service_graph(road)
        preparation.append(perf_counter() - start)
        measured, solution = oracle_run(compact)
        _, report, _ = expand_and_validate(compact, road, archive, solution, without_h=True)
        assert report.feasible, report.violations
        total.append(perf_counter() - start)
        assert baseline["deliveries"] == measured["deliveries"]
        assert abs(baseline["energy_kwh"] - measured["energy_kwh"]) < 1e-6
        reduced.append(measured)
    return {
        "name": road.name, "kind": "synthetic", "repeats": repeats,
        "road_nodes": len(road.nodes), "road_arcs": len(road.arcs),
        "compact_nodes": len(compact.nodes), "compact_arcs": len(compact.arcs),
        "road_oracle": full, "profile_oracle": reduced,
        "preparation_seconds": preparation, "total_profile_seconds": total,
        "median_road_seconds": median(r["seconds"] for r in full),
        "median_profile_total_seconds": median(total),
        "scope": "Pricing exhaustivo de un vehículo; no tiempo del maestro SCIP.",
    }


def real_road(path, repeats, cache, solver_seconds):
    road = load_instance(path)
    report = {"kind": "local_road", "path": str(path), "input_sha256": fingerprint(road),
              "nodes": len(road.nodes), "arcs": len(road.arcs), "repeats": repeats}
    measured = {"legacy_dijkstra": [], "auto": [], "cache_hit": []}
    report["preparation_seconds"] = measured
    for method in measured:
        if method == "cache_hit":
            started = perf_counter()
            prepare_service_graph(road, cache_directory=cache)
            report["cache_population_seconds"] = perf_counter() - started
        for _ in range(repeats):
            started = perf_counter()
            if method == "legacy_dijkstra":
                compact, archive = build_service_graph(road, road.parameters.movement_limit)
            else:
                compact, archive = prepare_service_graph(
                    road, cache_directory=cache if method == "cache_hit" else None,
                )
            measured[method].append(perf_counter() - started)
            if method == "cache_hit":
                assert compact.provenance["preprocessing_cache"]["hit"]
            print(json.dumps({"method": method, "sample": len(measured[method]),
                              "seconds": measured[method][-1]}), flush=True)
            (cache.parent / "benchmark-progress.json").write_text(json.dumps(report, indent=2))
            if method == "legacy_dijkstra":
                expected = {(a.from_node_id, a.to_node_id): a.energy_kwh for a in compact.arcs}
            else:
                assert {(a.from_node_id, a.to_node_id): a.energy_kwh for a in compact.arcs} == expected
            if method == "auto" and solver_seconds:
                result = run_instance(
                    compact, SolverConfig(time_limit_seconds=solver_seconds),
                    road_instance=road, path_archive=archive,
                )
                report["scip"] = {
                    "status": result["status"], "deliveries": result["kpis"]["served_deliveries"],
                    "energy_kwh": result["kpis"]["net_battery_energy_kwh"],
                    "runtime_seconds": result["runtime_seconds"],
                    "road_valid": result["road_validation"]["feasible"],
                    "optimal": result["solve"]["lexicographic_optimal"],
                }
                solver_seconds = 0  # Una sola ejecución, presupuesto explícito.
    report["cache_note"] = "Todas las muestras de cache_hit reutilizan; la preparación de caché se informa aparte."
    report["compact_nodes"], report["compact_arcs"] = len(compact.nodes), len(compact.arcs)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--road-instance", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--solver-seconds", type=float, default=0)
    parser.add_argument("--output", type=Path, default=Path("artifacts/resource-graph/benchmark.json"))
    args = parser.parse_args()
    if args.repeats < 1 or args.solver_seconds < 0:
        parser.error("Presupuestos y repeticiones inválidos")
    code = Path(__file__).resolve().parents[1] / "src/ev_routing"
    code_hash = hashlib.sha256()
    for path in sorted(code.rglob("*.py")):
        code_hash.update(path.relative_to(code).as_posix().encode())
        code_hash.update(path.read_bytes())
    result = {"code_sha256": code_hash.hexdigest(), "synthetic": [synthetic(case, args.repeats) for case in (
        make_window_instance(), corridor(8), corridor(80),
    )]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if args.road_instance:
        result["local_road"] = real_road(
            args.road_instance, args.repeats, args.output.parent / "cache", args.solver_seconds,
        )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
