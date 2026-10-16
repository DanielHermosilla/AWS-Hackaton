"""Campaña auditable para el jurado; reutiliza preparación, solver y validador."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import monotonic, perf_counter
from types import SimpleNamespace

from ev_routing.benchmark import _save, _sha, _version
from ev_routing.contracts import ModelParameters, Operations, ProblemInstance, Solution
from ev_routing.inputs import load_instance, save_instance
from ev_routing.metrics import compute_metrics
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.service_graph import PathArchive, expand_and_validate, fingerprint
from ev_routing.validation import validate_solution

ROOT = Path(__file__).resolve().parents[2]


def code_identity():
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src/ev_routing").rglob("*.py")):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return {
        "git_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
        ).strip(),
        "source_sha256": digest.hexdigest(),
        "tracked_diff_sha256": hashlib.sha256(subprocess.check_output(
            ["git", "-C", str(ROOT), "diff", "HEAD", "--"],
        )).hexdigest(),
        "python": sys.version,
        "machine": platform.machine(), "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "uv_lock_sha256": _sha(ROOT / "uv.lock"),
        "versions": {n: _version(n) for n in ("pyscipopt", "numpy", "scipy", "pydantic")},
    }


def result_fingerprint(instance):
    """RunResult uses canonical sorted JSON; PathArchive has its own legacy hash."""
    return hashlib.sha256(json.dumps(
        instance.model_dump(mode="json"), sort_keys=True, allow_nan=False,
    ).encode()).hexdigest()


def make_plan(args):
    """Freeze the entire experiment before observing outcomes."""
    common = {"kind": "base", "customers": None, "vehicles": None, "parameters": {},
              "operations": {}, "scenario_seed": 0}
    cases = [{**common, "id": "base"}]
    for n in args.customers:
        for k in args.vehicles:
            for seed in args.scenario_seeds:
                cases.append({
                    **common, "id": f"scale-c{n}-v{k}-s{seed}", "kind": "generated_demand",
                    "customers": n, "vehicles": k, "scenario_seed": seed,
                })
    if args.sensitivity:
        cases.extend([
            {**common, "id": "consumption-plus25", "kind": "sensitivity",
             "operations": {"energy_margin_fraction": 0.25}},
            {**common, "id": "capacity-80percent", "kind": "sensitivity",
             "capacity_fraction": 0.8},
            {**common, "id": "initial-soc40", "kind": "sensitivity",
             "parameters": {"initial_soc": 0.4}},
            {**common, "id": "chargers-half-offline", "kind": "sensitivity",
             "charger_outage_fraction": 0.5},
        ])
    if args.scenarios:
        extra = json.loads(args.scenarios.read_text())
        cases.extend({**common, **case, "kind": "custom_scenario"} for case in extra)
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids) or any(
        not i or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in i) for i in ids
    ):
        raise ValueError("IDs únicos de escenario, solo a-z, 0-9, guion y guion bajo")
    policies = ["standard", "deterministic"] + (["adaptive"] if args.with_bedrock else [])
    inputs = {"road": {"path": str(args.road_instance.resolve()), "sha256": _sha(args.road_instance)}}
    for name in ("impact", "routing_csv"):
        path = getattr(args, name)
        if path:
            inputs[name] = {"path": str(path.resolve()), "sha256": _sha(path)}
    jobs = []
    for case in cases:
        for budget in args.budgets:
            for repetition in range(args.repetitions):
                for seed in args.seeds:
                    order = policies.copy()
                    random.Random(seed + repetition * 1_000_003).shuffle(order)
                    jobs.extend({
                        "case": case["id"], "budget": budget, "policy": policy,
                        "seed": seed, "repetition": repetition,
                    } for policy in order)
    return {
        "schema_version": "1.0", "code": code_identity(), "inputs": inputs, "cases": cases,
        "jobs": jobs, "threads": args.threads, "energy_relative_gap": args.energy_relative_gap,
        "bedrock_model": args.bedrock_model, "aws_region": args.aws_region,
        "aws_profile": args.aws_profile, "llm_max_calls": args.llm_max_calls,
        "llm_timeout_seconds": args.llm_timeout_seconds, "llm_time_fraction": 0.25,
        "llm_reasoning_effort": "low", "llm_max_output_tokens": 2048,
        "llm_instance_context_bytes": 8000, "decision_interval_seconds": 15,
        "preprocessing_seconds": args.preprocessing_seconds,
        "process_grace_seconds": args.process_grace_seconds,
        "max_solver_seconds": sum(j["budget"] for j in jobs),
        "max_llm_calls": sum(j["policy"] == "adaptive" for j in jobs) * args.llm_max_calls,
        "scope": "Red fija; demanda generada y flota escaladas. Sin entrenamiento ni selección de ganadores.",
    }


def scenario_road(road, case):
    """Add distinct reachable street locations, retaining every original street."""
    n, k = case["customers"], case["vehicles"]
    nodes = road.nodes
    selected = []
    rng = random.Random(case["scenario_seed"])
    if n is not None:
        old = set(road.customer_ids)
        if n < len(old):
            selected = sorted(rng.sample(sorted(old), n))
            keep = set(selected)
            nodes = [
                node.model_copy(update={"node_type": "junction"})
                if node.node_type == "visit" and node.node_id not in keep else node
                for node in nodes
            ]
        elif n > len(old):
            import networkx as nx

            graph = nx.DiGraph()
            graph.add_edges_from((a.from_node_id, a.to_node_id) for a in road.arcs)
            reachable = nx.descendants(graph, road.depot_id) & nx.ancestors(graph, road.depot_id)
            candidates = sorted(
                node.node_id for node in nodes
                if node.node_type == "junction" and node.node_id in reachable
            )
            selected = sorted(rng.sample(candidates, n - len(old)))
            promoted = set(selected)
            nodes = [
                node.model_copy(update={"node_type": "visit"}) if node.node_id in promoted else node
                for node in nodes
            ]
    parameters = road.parameters.model_dump()
    parameters.update(case["parameters"])
    if k is not None:
        parameters["vehicle_count"] = k
        if road.compatible_chargers is not None and k != road.parameters.vehicle_count:
            raise ValueError("Flota con compatibilidad explícita: aportar otro snapshot para escalar")
    if "capacity_fraction" in case:
        parameters["battery_capacity_kwh"] *= case["capacity_fraction"]
    operations = road.operations.model_dump()
    operations.update(case["operations"])
    if "charger_outage_fraction" in case:
        compatible = sorted(set().union(*(set(road.chargers_for(v)) for v in road.vehicle_ids)))
        disabled = rng.sample(compatible, math.ceil(len(compatible) * case["charger_outage_fraction"]))
        operations["disabled_charger_ids"] = sorted(set(operations["disabled_charger_ids"]) | set(disabled))
    # Validation is deliberate: model_copy(update=...) does not validate physical parameters.
    scenario = ProblemInstance(
        schema_version=road.schema_version, name=f"{road.name}-{case['id']}", nodes=nodes,
        arcs=road.arcs, parameters=ModelParameters.model_validate(parameters),
        operations=Operations.model_validate(operations), compatible_chargers=road.compatible_chargers,
        provenance={**road.provenance, "experiment": {
            **case, "selected_node_ids": selected,
            "demand_source": "supplied" if n is None else "generated_on_existing_road_network",
            "street_network_changed": False,
        }},
    )
    return scenario


def checked_preparation(directory):
    record = directory / "preparation.json"
    if not record.exists():
        return None
    meta = json.loads(record.read_text())
    for filename, expected in meta["files_sha256"].items():
        if _sha(directory / filename) != expected:
            raise ValueError(f"Preparación alterada: {directory.name}/{filename}")
    return meta


def prepare_case(args, plan, case):
    directory = args.output_dir / "cases" / case["id"]
    record = directory / "preparation.json"
    meta = checked_preparation(directory)
    if meta is not None:
        return meta
    if _sha(args.road_instance) != plan["inputs"]["road"]["sha256"]:
        raise ValueError("La red de entrada cambió después de planificar")
    started = perf_counter()
    road = load_instance(args.road_instance)
    loaded = perf_counter()
    if case["kind"] == "base" and (
        road.parameters.vehicle_count != 2 or road.parameters.initial_soc != 0.6
        or road.operations != Operations()
    ):
        raise ValueError("El caso base exige 2 vehículos, SoC 0.6 y operations neutras")
    if road.provenance.get("representation", {}).get("kind") in {
        "resource_paths", "service_paths_nonnegative",
    }:
        raise ValueError("--road-instance exige calles originales, no caminos preprocesados")
    if args.routing_csv and road.provenance.get("routing_csv_sha256") != _sha(args.routing_csv):
        raise ValueError("El CSV y la procedencia del snapshot no coinciden")
    road = scenario_road(road, case)
    constructed = perf_counter()
    compact, archive = prepare_service_graph(road, preprocessing_seconds=args.preprocessing_seconds)
    prepared = perf_counter()
    directory.mkdir(parents=True, exist_ok=True)
    save_instance(road, directory / "road.json")
    save_instance(compact, directory / "instance.json")
    _save(directory / "paths.json", archive.model_dump(mode="json"))
    serialized = perf_counter()
    # A cheap independent baseline, never misrepresented as another team's algorithm.
    from ev_routing.route_heuristics import InsertionRoutes

    baseline_started = perf_counter()
    heuristic = InsertionRoutes(compact)
    # This heuristic treats scalar arcs only, and cannot consume resource multigraphs.
    supported = heuristic.supported and compact.schema_version == "1.0"
    solution = heuristic.seed("cheapest_insertion", 1, monotonic() + 1, seed=0) if supported else None
    heuristic_seconds = perf_counter() - baseline_started
    validation = validate_solution(compact, solution, enforce_movement_limit=False) if solution else None
    expanded = None
    if validation and validation.feasible:
        expanded, validation, _ = expand_and_validate(compact, road, archive, solution, without_h=True)
    baseline = {
        "method": "single cheapest insertion, no recharging; 1 start, 1 second soft limit",
        "supported": supported, "heuristic_seconds": heuristic_seconds,
        "validation": validation.model_dump() if validation else None,
        "kpis": compute_metrics(road, expanded, validation),
        "solution": solution.model_dump(mode="json") if solution else None,
    }
    _save(directory / "greedy.json", baseline)
    meta = {
        "case": case, "road_nodes": len(road.nodes), "road_arcs": len(road.arcs),
        "customers": len(road.customer_ids), "chargers": len(road.charger_ids),
        "vehicles": road.parameters.vehicle_count,
        "compatible_chargers": len(set().union(*(set(road.chargers_for(v)) for v in road.vehicle_ids))),
        "compact_nodes": len(compact.nodes), "compact_arcs": len(compact.arcs),
        "parameters": road.parameters.model_dump(), "operations": road.operations.model_dump(),
        "representation": compact.provenance["representation"],
        "instance_sha256": result_fingerprint(compact),
        "path_archive_instance_fingerprint": fingerprint(compact),
        "load_seconds": loaded - started, "scenario_seconds": constructed - loaded,
        "preprocessing_seconds": prepared - constructed,
        "serialization_seconds": serialized - prepared,
        "preparation_total_seconds": serialized - started,
        "energy_estimator": road.provenance.get("energy"),
        "files_sha256": {n: _sha(directory / n) for n in ("road.json", "instance.json", "paths.json", "greedy.json")},
    }
    _save(record, meta)
    return meta


def prepare_in_process(args, plan, case, timeout):
    directory = args.output_dir / "cases" / case["id"]
    meta = checked_preparation(directory)
    if meta is not None:
        return meta
    directory.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "ev_routing.evidence", "_prepare",
        "--manifest", str(args.output_dir / "manifest.json"), "--case", case["id"],
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    with (directory / "preparation.log").open("w") as log:
        try:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise ValueError(f"Preparación agotó el presupuesto global: {case['id']}") from None
    if result.returncode != 0:
        raise ValueError(f"Preparación falló: revisar {directory / 'preparation.log'}")
    return checked_preparation(directory)


def run_job(args, plan, job, timeout):
    case_dir = args.output_dir / "cases" / job["case"]
    run_dir = args.output_dir / "runs" / (
        f"{job['case']}-{job['policy']}-b{job['budget']:g}-s{job['seed']}-r{job['repetition']}"
    )
    execution_path = run_dir / "execution.json"
    if execution_path.exists():
        execution = json.loads(execution_path.read_text())
        for name, sha in execution["files_sha256"].items():
            if _sha(run_dir / name) != sha:
                raise ValueError(f"Resultado alterado: {run_dir / name}")
        return execution
    run_dir.mkdir(parents=True, exist_ok=True)
    # An interrupted job without its final record must not inherit a stale result.
    (run_dir / "result.json").unlink(missing_ok=True)
    _save(run_dir / "config.json", {"solver": {
        "solver": "scip-routes", "time_limit_seconds": job["budget"], "threads": plan["threads"],
        "seed": job["seed"], "energy_relative_gap": plan["energy_relative_gap"],
    }})
    command = [
        sys.executable, "-m", "ev_routing.cli", "run",
        "--config", str(run_dir / "config.json"),
        "--instance", str(case_dir / "instance.json"),
        "--road-instance", str(case_dir / "road.json"),
        "--path-archive", str(case_dir / "paths.json"),
        "--search-policy", job["policy"], "--output", str(run_dir / "result.json"),
        "--solver-log-directory", str(run_dir / "native"),
    ]
    if job["policy"] == "adaptive":
        command += [
            "--bedrock-model", plan["bedrock_model"], "--aws-region", plan["aws_region"],
            "--aws-profile", plan["aws_profile"], "--llm-max-calls", str(plan["llm_max_calls"]),
            "--llm-timeout-seconds", str(plan["llm_timeout_seconds"]),
            "--llm-time-fraction", str(plan["llm_time_fraction"]),
            "--llm-max-output-tokens", str(plan["llm_max_output_tokens"]),
            "--llm-reasoning-effort", plan["llm_reasoning_effort"],
            "--llm-instance-context-bytes", str(plan["llm_instance_context_bytes"]),
            "--decision-interval-seconds", str(plan["decision_interval_seconds"]),
        ]
    env = os.environ.copy()
    env.update({n: str(plan["threads"]) for n in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")})
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONHASHSEED"] = str(job["seed"])
    started = perf_counter()
    with (run_dir / "process.log").open("w") as log:
        try:
            completed = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, env=env,
                timeout=timeout, check=False,
            )
            returncode = completed.returncode
        except subprocess.TimeoutExpired:
            returncode = 124
    execution = {
        **job, "command": command, "wall_seconds": perf_counter() - started, "returncode": returncode,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_timeout_seconds": timeout,
        "files_sha256": {
            n: _sha(run_dir / n) for n in ("result.json", "config.json", "process.log")
            if (run_dir / n).exists()
        },
    }
    _save(execution_path, execution)
    return execution


def impact_metrics(row, factors):
    """Explicit counterfactual: a diesel vehicle performs the SAME physical route."""
    absent = {"tailpipe_co2_avoided_kg": None, "operational_co2_difference_kg": None,
              "impact_reason": "Faltan factores y escenario de referencia documentados."}
    if not factors or not row["feasible"] or row.get("distance_km") is None:
        return absent
    required = ("diesel_kg_co2_per_litre", "diesel_litres_per_100km", "factor_source",
                "factor_date", "consumption_assumption", "geography")
    if any(factors.get(k) is None or factors.get(k) == "" for k in required):
        return absent
    fuel, rate = factors["diesel_litres_per_100km"], factors["diesel_kg_co2_per_litre"]
    if not all(isinstance(x, (float, int)) and math.isfinite(x) and x > 0 for x in (fuel, rate)):
        raise ValueError("Los factores diésel deben ser finitos y positivos")
    tailpipe = row["distance_km"] * fuel / 100 * rate
    result = {
        **absent, "tailpipe_co2_avoided_kg": tailpipe,
        "impact_reason": "Estimación de electrificación, diésel en el MISMO recorrido; no ahorro del algoritmo ni ciclo de vida.",
    }
    grid, efficiency = factors.get("grid_kg_co2_per_kwh"), factors.get("charging_efficiency")
    energy = row.get("energy_kwh")
    if grid is not None and efficiency is not None and energy is not None and energy >= 0:
        if not factors.get("grid_source") or not factors.get("grid_date"):
            raise ValueError("El factor eléctrico requiere fuente y fecha")
        if not (math.isfinite(grid) and grid >= 0 and math.isfinite(efficiency) and 0 < efficiency <= 1):
            raise ValueError("Factor eléctrico o eficiencia inválidos")
        # Replenish ALL battery use, including initial charge. Not just en-route charging.
        result["operational_co2_difference_kg"] = tailpipe - energy / efficiency * grid
        result["impact_reason"] += " Electricidad calculada reponiendo todo el consumo de batería al SoC inicial."
    days = factors.get("equivalent_route_days_per_year")
    if days is not None:
        if not isinstance(days, int) or not 1 <= days <= 366:
            raise ValueError("Días equivalentes deben ser enteros entre 1 y 366")
        result["annual_tailpipe_co2_projection_kg"] = tailpipe * days
        result["annual_projection_days"] = days
    return result


def row_from_result(job, execution, result, meta):
    kpi, solve = result.get("kpis", {}), result.get("solve", {})
    tuning = result.get("tuning") or {}
    phases = {p["name"]: p for p in solve.get("phases", [])}
    feasible = bool(
        execution["returncode"] in (0, 1) and kpi.get("feasible")
        and (result.get("validation") or {}).get("feasible")
        and (result.get("road_validation") or {}).get("feasible")
        and result.get("instance_sha256") == meta["instance_sha256"]
    )
    row = {
        **job, "status": result.get("status", "execution_error"),
        "returncode": execution["returncode"], "feasible": feasible,
        "deliveries": kpi.get("served_deliveries") if feasible else None,
        "energy_kwh": kpi.get("net_battery_energy_kwh") if feasible else None,
        "distance_km": kpi.get("distance_km") if feasible else None,
        "charging_stops": kpi.get("charging_stops") if feasible else None,
        "minimum_battery_kwh": kpi.get("minimum_battery_kwh") if feasible else None,
        "operational_duration_seconds": kpi.get("operational_duration_seconds") if feasible else None,
        "wall_seconds": execution["wall_seconds"],
        "pipeline_seconds": result.get("runtime_seconds", {}).get("total"),
        "resolution_seconds": result.get("runtime_seconds", {}).get("resolution_including_model"),
        "preparation_seconds": meta["preparation_total_seconds"],
        "cold_total_seconds": meta["preparation_total_seconds"] + execution["wall_seconds"],
        "lexicographic_optimal": bool(feasible and solve.get("lexicographic_optimal")),
        "customers": meta["customers"], "vehicles": meta["vehicles"],
        "road_nodes": meta["road_nodes"], "road_arcs": meta["road_arcs"],
        "instance_sha256": meta["instance_sha256"],
        "llm_status": tuning.get("status"), "llm_calls": tuning.get("calls", 0),
        "llm_algorithm_changes": tuning.get("decisions_changing_algorithm", 0),
        "llm_applied": tuning.get("applied_decisions", 0),
        "llm_seconds": result.get("runtime_seconds", {}).get("llm"),
    }
    row["llm_effective"] = job["policy"] == "adaptive" and row["llm_algorithm_changes"] > 0
    for name in ("deliveries", "energy"):
        phase = phases.get(name, {})
        for field in ("incumbent", "best_bound", "relative_gap", "proven_optimal", "termination_condition"):
            row[f"{name}_{field}"] = phase.get(field)
    for token in ("inputTokens", "outputTokens"):
        values = [(d.get("usage") or {}).get(token) for d in tuning.get("decisions", [])]
        row[f"llm_{token}"] = sum(values) if (
            len(values) == row["llm_calls"] and all(isinstance(v, int) and v >= 0 for v in values)
        ) else None
    return row


def compare_pair(reference, candidate, energy_gap):
    """Keep losses and censored runs; faster stopping alone is not a speedup."""
    paired = {
        "case": candidate["case"], "budget": candidate["budget"], "seed": candidate["seed"],
        "repetition": candidate["repetition"], "reference": reference["policy"],
        "candidate": candidate["policy"], "delivery_delta": None, "energy_saving_percent": None,
        "certified_speedup": None, "llm_effective": candidate["llm_effective"],
        "reason": "Sin dos resultados factibles para el mismo snapshot.",
    }
    if not (reference["feasible"] and candidate["feasible"]
            and reference["instance_sha256"] == candidate["instance_sha256"]):
        return paired
    paired["delivery_delta"] = candidate["deliveries"] - reference["deliveries"]
    paired["reason"] = "Cobertura distinta: energía y velocidad no se comparan."
    if paired["delivery_delta"] != 0:
        return paired
    energy = reference["energy_kwh"]
    if energy is not None and energy > 0 and candidate["energy_kwh"] is not None:
        paired["energy_saving_percent"] = 100 * (energy - candidate["energy_kwh"]) / energy
    def certified(row):
        gap = row["energy_relative_gap"]
        return row["deliveries_proven_optimal"] and (
            row["energy_proven_optimal"] or (
                gap is not None and 0 <= gap <= energy_gap
                and row["energy_best_bound"] is not None
            )
        )
    paired["reason"] = "Mismo cumplimiento; tiempos censurados o certificado insuficiente."
    if certified(reference) and certified(candidate):
        paired["certified_speedup"] = reference["wall_seconds"] / candidate["wall_seconds"]
        paired["reason"] = "Mismo máximo de entregas y tolerancia energética certificada; incluye lectura y validación."
    return paired


def write_table(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def paired_statistics(pairs):
    """Descriptive paired statistics; no winner selection or cross-instance inference."""
    groups = defaultdict(list)
    for pair in pairs:
        groups[pair["case"], pair["budget"], pair["reference"], pair["candidate"]].append(pair)
    output = []
    for (case, budget, reference, candidate), group in groups.items():
        energies = [p["energy_saving_percent"] for p in group if p["energy_saving_percent"] is not None]
        speeds = [p["certified_speedup"] for p in group if p["certified_speedup"] is not None]
        output.append({
            "case": case, "budget": budget, "reference": reference, "candidate": candidate,
            "pairs": len(group), "equal_coverage_energy_pairs": len(energies),
            "energy_wins": sum(v > 1e-6 for v in energies),
            "energy_losses": sum(v < -1e-6 for v in energies),
            "energy_ties": sum(abs(v) <= 1e-6 for v in energies),
            "energy_saving_median_percent": median(energies) if energies else None,
            "energy_saving_min_percent": min(energies, default=None),
            "energy_saving_max_percent": max(energies, default=None),
            "certified_speed_pairs": len(speeds),
            "certified_speedup_median": median(speeds) if speeds else None,
            "llm_effective_pairs": sum(p["llm_effective"] for p in group),
        })
    return output


def summarize(args, plan):
    for entry in plan["inputs"].values():
        if _sha(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("Un input del manifiesto cambió durante la campaña")
    rows, meta_by_case = [], {}
    factors = json.loads(args.impact.read_text()) if args.impact else None
    for case in plan["cases"]:
        prep = args.output_dir / "cases" / case["id"] / "preparation.json"
        if prep.exists():
            meta_by_case[case["id"]] = checked_preparation(prep.parent)
    for directory in sorted((args.output_dir / "runs").glob("*")):
        record = directory / "execution.json"
        if not record.exists():
            continue
        execution = json.loads(record.read_text())
        for filename, sha in execution["files_sha256"].items():
            if _sha(directory / filename) != sha:
                raise ValueError(f"Artefacto alterado: {directory / filename}")
        result_path = directory / "result.json"
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        job = {k: execution[k] for k in ("case", "budget", "seed", "repetition", "policy")}
        row = row_from_result(job, execution, result, meta_by_case[job["case"]])
        greedy = json.loads(
            (args.output_dir / "cases" / job["case"] / "greedy.json").read_text()
        )["kpis"]
        row["greedy_deliveries"] = greedy["served_deliveries"]
        row["greedy_energy_saving_percent"] = None
        if (row["feasible"] and greedy["feasible"]
                and row["deliveries"] == greedy["served_deliveries"]
                and greedy["net_battery_energy_kwh"] > 0):
            row["greedy_energy_saving_percent"] = (
                100 * (greedy["net_battery_energy_kwh"] - row["energy_kwh"])
                / greedy["net_battery_energy_kwh"]
            )
        row["result_path"] = str(result_path) if result_path.exists() else None
        row.update(impact_metrics(row, factors))
        rows.append(row)
    _save(args.output_dir / "runs.json", rows)
    write_table(args.output_dir / "runs.csv", rows)
    paired = []
    by_pair = defaultdict(dict)
    for row in rows:
        by_pair[row["case"], row["budget"], row["seed"], row["repetition"]][row["policy"]] = row
    for policies in by_pair.values():
        for ref, candidate in (("standard", "deterministic"), ("standard", "adaptive"), ("deterministic", "adaptive")):
            if ref in policies and candidate in policies:
                paired.append(compare_pair(policies[ref], policies[candidate], plan["energy_relative_gap"]))
    _save(args.output_dir / "paired.json", paired)
    write_table(args.output_dir / "paired.csv", paired)
    stats = paired_statistics(paired)
    _save(args.output_dir / "paired-summary.json", stats)
    write_table(args.output_dir / "paired-summary.csv", stats)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["case"], row["budget"], row["policy"]].append(row)
    summaries = []
    for (case, budget, policy), group in grouped.items():
        valid = [r for r in group if r["feasible"]]
        summaries.append({
            "case": case, "budget": budget, "policy": policy, "runs": len(group),
            "feasible_runs": len(valid), "exact_optimal_runs": sum(r["lexicographic_optimal"] for r in group),
            "deliveries_min": min((r["deliveries"] for r in valid), default=None),
            "deliveries_max": max((r["deliveries"] for r in valid), default=None),
            "energy_median_kwh": median([r["energy_kwh"] for r in valid])
            if valid and len({r["deliveries"] for r in valid}) == 1 else None,
            "wall_median_seconds": median(r["wall_seconds"] for r in group),
            "wall_max_seconds": max(r["wall_seconds"] for r in group),
            "llm_effective_runs": sum(r["llm_effective"] for r in group),
        })
    _save(args.output_dir / "summary.json", summaries)
    write_table(args.output_dir / "summary.csv", summaries)
    report = [
        "# Evidencia para la presentación", "",
        f"Commit base: `{plan['code']['git_commit']}`. Fuente ejecutada: `{plan['code']['source_sha256']}`.",
        f"Corridas registradas: **{len(rows)}/{len(plan['jobs'])}**. Gap energético objetivo: **{100 * plan['energy_relative_gap']:g}%**.",
        "Los tiempos de pared incluyen arranque, lectura y validación. La preparación en frío se guarda aparte.",
        "Un timeout sigue en el denominador. 0,5% no es óptimo exacto. Las medianas de energía requieren igual cobertura para compararse.",
        "",
        "| Escenario | Política | Presupuesto s | Factibles / runs | Entregas mín–máx | Energía mediana kWh | Pared mediana s | Óptimos exactos |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    def show(value):
        return "ND" if value is None else f"{value:.4f}"
    for s in summaries:
        report.append(
            f"| {s['case']} | {s['policy']} | {s['budget']:g} | {s['feasible_runs']}/{s['runs']} | "
            f"{s['deliveries_min']}–{s['deliveries_max']} | {show(s['energy_median_kwh'])} | "
            f"{s['wall_median_seconds']:.3f} | {s['exact_optimal_runs']} |"
        )
    report += ["", "## Alcance y supuestos", ""]
    for name, meta in meta_by_case.items():
        report.append(
            f"- {name}: {meta['customers']} clientes, {meta['vehicles']} vehículos, "
            f"{meta['road_nodes']} nodos / {meta['road_arcs']} arcos viales; "
            f"{meta['compact_nodes']} nodos / {meta['compact_arcs']} arcos tras preparación "
            f"({meta['preprocessing_seconds']:.3f} s). Demanda: {meta['case']['kind']}."
        )
    report += [
        "", "La escala aumenta demanda/flota sobre la misma red vial. Los clientes añadidos son escenarios generados, no demanda oficial observada.",
        "Capacidad útil, reserva y estimador energético son supuestos del snapshot. La validación no demuestra autonomía real ni calibración predictiva.",
        "Las sensibilidades reoptimizan bajo otra hipótesis; no prueban que las rutas originales toleren ese cambio.",
        "La referencia greedy usa menos presupuesto y no permite recargas: mide una alternativa simple, no un competidor de igual capacidad.",
        "Los resultados sobre una sola geografía no prueban generalización. Variar las semillas de escenario y aportar otras redes en campañas independientes.",
        "", "## Aporte del LLM", "",
        f"Corridas adaptativas: {sum(r['policy'] == 'adaptive' for r in rows)}; "
        f"con cambios efectivos de algoritmo: {sum(r['llm_effective'] for r in rows)}.",
        "Comparar adaptive tanto con standard como con deterministic. `paired.csv` conserva pérdidas y fallos.",
        "La comparación por política asignada incluye fallback; el subconjunto efectivo es descriptivo y puede tener sesgo de selección.",
        "Solo `certified_speedup` compara tiempos hasta la misma tolerancia certificada. No llamar aceleración al cociente de dos timeouts.",
        "", "## Impacto ambiental", "",
        "CO₂ de escape evitado: escenario diésel en exactamente las mismas rutas. Es efecto de electrificación, no mejora atribuible al solver.",
        "La diferencia operacional incluye electricidad para reponer todo el uso de batería, incluso la carga inicial; no es ciclo de vida ni CO₂e.",
        "Sin factores documentados, el resultado es ND. Una proyección anual solo repite días equivalentes explícitos; no representa actividad medida.",
        "", "## Comparación con terceros", "",
        "Los baselines medidos son internos. No se dispone de corridas de otros equipos.",
        "Para comparar, entregar a todos el mismo snapshot y presupuesto, recoger rutas y validarlas con el comando `validate-external`.",
        "Los tiempos declarados por terceros no son tiempos medidos aquí. Los benchmarks EVRPTW publicados tienen otros objetivos y restricciones.",
        "", "## Archivos para las diapositivas", "",
        "`runs.csv`: resultados individuales y CO₂ estimado. `summary.csv`: agregados. `paired.csv`: diferencias pareadas.",
        "`cases/*/greedy.json`: referencia de inserción sin recarga, validada en calles, con su presupuesto de 1 s.",
        "`cases/*/preparation.json`: física, tamaños, representación, tiempos y hashes. `runs/*`: JSON nativo y logs.",
    ]
    (args.output_dir / "report.md").write_text("\n".join(report) + "\n")
    return rows


def validate_external(args):
    """Audit a competitor's native Solution, ignoring their feasibility/optimality labels."""
    directory = args.case_dir
    compact, road = load_instance(directory / "instance.json"), load_instance(directory / "road.json")
    archive = PathArchive.model_validate_json((directory / "paths.json").read_text())
    external = json.loads(args.result.read_text())
    if external.get("instance_sha256") != result_fingerprint(compact):
        raise ValueError("El resultado externo no corresponde al mismo snapshot")
    solution = Solution.model_validate(external["solution"])
    validation = validate_solution(compact, solution, enforce_movement_limit=False)
    expanded = None
    if validation.feasible:
        expanded, validation, _ = expand_and_validate(compact, road, archive, solution, without_h=True)
    _save(args.output, {
        "competitor": external.get("method"), "source_sha256": _sha(args.result),
        "instance_sha256": result_fingerprint(compact), "validation": validation.model_dump(),
        "kpis": compute_metrics(road, expanded, validation),
        "reported_wall_seconds": external.get("wall_seconds"),
        "timing_source": "reported_by_competitor_not_measured_here",
        "optimality": "not_certified_by_this_import",
    })
    return 0 if validation.feasible else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    campaign = sub.add_parser("campaign")
    campaign.add_argument("--road-instance", required=True, type=Path)
    campaign.add_argument("--routing-csv", type=Path)
    campaign.add_argument("--output-dir", required=True, type=Path)
    campaign.add_argument("--customers", nargs="*", type=int, default=[40])
    campaign.add_argument("--vehicles", nargs="+", type=int, default=[2])
    campaign.add_argument("--scenario-seeds", nargs="+", type=int, default=[0])
    campaign.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    campaign.add_argument("--repetitions", type=int, default=1)
    campaign.add_argument("--budgets", nargs="+", type=float, default=[30])
    campaign.add_argument("--threads", type=int, default=1)
    campaign.add_argument("--energy-relative-gap", type=float, default=.005)
    campaign.add_argument("--preprocessing-seconds", type=float, default=10)
    campaign.add_argument("--process-grace-seconds", type=float, default=30)
    campaign.add_argument("--sensitivity", action="store_true")
    campaign.add_argument("--scenarios", type=Path, help="Lista JSON de cambios explícitos a parámetros/operations")
    campaign.add_argument("--impact", type=Path)
    campaign.add_argument("--with-bedrock", action="store_true")
    campaign.add_argument("--bedrock-model", default=os.getenv("BEDROCK_MODEL_ID", "us.openai.gpt-5.6-luna"))
    campaign.add_argument("--aws-region", default="us-east-1")
    campaign.add_argument("--aws-profile", default="hackathon")
    campaign.add_argument("--llm-max-calls", type=int, default=4)
    campaign.add_argument("--llm-timeout-seconds", type=float, default=8)
    campaign.add_argument("--execute", action="store_true", help="Sin esta opción solo imprime el plan")
    campaign.add_argument("--resume", action="store_true")
    campaign.add_argument("--report-only", action="store_true")
    campaign.add_argument("--wall-budget-seconds", type=float, default=600)
    external = sub.add_parser("validate-external")
    external.add_argument("--case-dir", required=True, type=Path)
    external.add_argument("--result", required=True, type=Path)
    external.add_argument("--output", required=True, type=Path)
    worker = sub.add_parser("_prepare", help=argparse.SUPPRESS)
    worker.add_argument("--manifest", required=True, type=Path)
    worker.add_argument("--case", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "_prepare":
            plan = json.loads(args.manifest.read_text())
            worker_args = SimpleNamespace(
                output_dir=args.manifest.parent, road_instance=Path(plan["inputs"]["road"]["path"]),
                routing_csv=Path(plan["inputs"]["routing_csv"]["path"]) if "routing_csv" in plan["inputs"] else None,
                preprocessing_seconds=plan["preprocessing_seconds"],
            )
            prepare_case(worker_args, plan, next(c for c in plan["cases"] if c["id"] == args.case))
            return 0
        if args.action == "validate-external":
            return validate_external(args)
        from ev_routing.contracts import SolverConfig
        from ev_routing.search_policy import BedrockConfig, SearchConfig

        for seed in args.seeds:
            for budget in args.budgets:
                SolverConfig(seed=seed, time_limit_seconds=budget, threads=args.threads,
                             energy_relative_gap=args.energy_relative_gap)
        SearchConfig(
            policy="adaptive" if args.with_bedrock else "standard", max_llm_calls=args.llm_max_calls,
            bedrock=BedrockConfig(model_id=args.bedrock_model, timeout_seconds=args.llm_timeout_seconds),
        )
        for values in (args.seeds, args.customers, args.vehicles, args.scenario_seeds, args.budgets):
            if len(set(values)) != len(values):
                raise ValueError("No repetir semillas, tamaños, flotas ni presupuestos")
        if any(n < 1 for n in args.customers + args.vehicles) or any(s < 0 for s in args.scenario_seeds):
            raise ValueError("Tamaños positivos y semillas no negativas")
        if (args.repetitions < 1 or args.wall_budget_seconds <= 0
                or not math.isfinite(args.wall_budget_seconds)
                or args.process_grace_seconds < 0 or not math.isfinite(args.process_grace_seconds)
                or args.preprocessing_seconds < 0 or not math.isfinite(args.preprocessing_seconds)):
            raise ValueError("Presupuestos y repeticiones inválidos")
        args.output_dir = args.output_dir.resolve()
        plan = make_plan(args)
        print(json.dumps({
            "cases": len(plan["cases"]), "runs": len(plan["jobs"]),
            "max_solver_seconds": plan["max_solver_seconds"], "max_llm_calls": plan["max_llm_calls"],
            "wall_budget_seconds": args.wall_budget_seconds, "execute": args.execute,
        }), flush=True)
        if not (args.execute or args.report_only):
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        manifest = args.output_dir / "manifest.json"
        if manifest.exists():
            if not (args.resume or args.report_only):
                raise ValueError("La campaña existe: usar --resume o elegir otro directorio")
            if json.loads(manifest.read_text()) != plan:
                raise ValueError("Plan, inputs o código distintos; no mezclar evidencia")
        else:
            if args.report_only:
                raise ValueError("No existe la campaña")
            if args.output_dir.exists() and any(args.output_dir.iterdir()):
                raise ValueError("El directorio de salida debe estar vacío")
            _save(manifest, plan)
        started = monotonic()
        completed = 0
        if args.execute and not args.report_only:
            cases = {c["id"]: c for c in plan["cases"]}
            for job in plan["jobs"]:
                remaining = args.wall_budget_seconds - (monotonic() - started)
                if remaining < job["budget"] + args.process_grace_seconds:
                    break
                meta = prepare_in_process(
                    args, plan, cases[job["case"]],
                    remaining - job["budget"] - args.process_grace_seconds,
                )
                remaining = args.wall_budget_seconds - (monotonic() - started)
                if remaining < job["budget"] + args.process_grace_seconds:
                    break
                if code_identity() != plan["code"]:
                    raise ValueError("El código cambió durante la campaña")
                execution = run_job(args, plan, job, job["budget"] + args.process_grace_seconds)
                completed += 1
                print(json.dumps({
                    **job, "returncode": execution["returncode"],
                    "wall_seconds": execution["wall_seconds"], "customers": meta["customers"],
                }), flush=True)
                # Durable checkpoints remain usable if the next process is interrupted.
                summarize(args, plan)
        rows = summarize(args, plan)
        _save(args.output_dir / "campaign-status.json", {
            "planned": len(plan["jobs"]), "recorded": len(rows), "visited_this_invocation": completed,
            "complete": len(rows) == len(plan["jobs"]), "elapsed_seconds": monotonic() - started,
        })
        return 0 if len(rows) == len(plan["jobs"]) and all(r["feasible"] for r in rows) else 2
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
