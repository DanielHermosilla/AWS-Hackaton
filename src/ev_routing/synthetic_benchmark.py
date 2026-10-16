"""Piloto y comparación pareada sobre redes sintéticas, sin dar el testigo al solver."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from threading import Thread
from time import perf_counter

from ev_routing.benchmark import _save, _sha
from ev_routing.contracts import SolverConfig
from ev_routing.inputs import load_instance, save_instance
from ev_routing.pipeline import run_instance
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.route_policy import RoutePolicy
from ev_routing.search_policy import DEFAULT_BEDROCK_MODEL, BedrockConfig, SearchConfig
from ev_routing.service_graph import PathArchive, check_service_context, fingerprint
from ev_routing.synthetic_instances import FAMILIES, GENERATOR_VERSION, make_case

PRESETS = {
    "standard": {},
    "primal": {
        "seed_time_fraction": .15, "improvement_time_fraction": .3,
        "repair_strategy": "regret", "repair_candidates": 16,
        "resource_repair_seconds": .12, "resource_path_order": "time",
        "destroy_operators": ["related", "route", "random"], "ruin_fraction": .3,
        "population_size": 20, "alns_iterations": 200,
        "restricted_master_seconds": 1.0,
    },
    "pricing": {
        "seed_time_fraction": .1, "improvement_time_fraction": .08,
        "resource_repair_seconds": .08, "columns_per_round": 100,
        "pricing_heuristic_seconds": .3, "pricing_heuristic_starts": 8,
        "epoch_seconds": 8, "node_selection": "best_bound",
        "restricted_master_seconds": .5,
    },
    "blocks": {"rebuild_strategy": "energy_blocks", "rebuild_seconds": 8,
               "improvement_time_fraction": .3},
    "windows": {"rebuild_strategy": "window_blocks", "rebuild_seconds": 8,
                "improvement_time_fraction": .3},
    "deadlines": {"rebuild_strategy": "deadline", "rebuild_seconds": 8,
                  "improvement_time_fraction": .3},
    "electric": {"rebuild_strategy": "electric_local", "rebuild_seconds": 8,
                 "improvement_time_fraction": .3},
}
MODES = (*PRESETS, "fixed", "rules", "adaptive", "adaptive_knobs")


def code_hash() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def physical_hash(instance) -> str:
    data = instance.model_dump(mode="json")
    data.pop("name", None)
    data.pop("provenance", None)
    data["nodes"].sort(key=lambda node: node["node_id"])
    data["arcs"].sort(key=lambda arc: (
        arc["from_node_id"], arc["to_node_id"], arc.get("arc_id") or "",
    ))
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _unique(values, name):
    if not values or len(set(values)) != len(values):
        raise ValueError(f"{name}: use una lista no vacía sin duplicados.")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("stage", choices=["generate", "pilot", "compare", "worker"])
    root.add_argument("--job", type=Path, help=argparse.SUPPRESS)
    root.add_argument("--output-dir", type=Path)
    root.add_argument("--customers", type=int, nargs="+", default=[16, 24])
    root.add_argument("--families", choices=FAMILIES, nargs="+", default=["clustered", "crossed"])
    root.add_argument("--instance-seeds", type=int, nargs="+")
    root.add_argument("--solver-seeds", type=int, nargs="+", default=[0])
    root.add_argument("--policies", choices=MODES, nargs="+")
    root.add_argument("--fixed-policy", type=Path)
    root.add_argument("--adaptive-start", choices=["fixed", "standard"], default="fixed",
                      help="Política inicial común de AWS y su ablación.")
    root.add_argument("--pilot-objective", choices=["coverage", "lexicographic"], default="coverage")
    root.add_argument("--allow-pilot-failures", action="store_true",
                      help="Conservar fallos y elegir solo entre presets que completaron todos los casos.")
    root.add_argument("--time-limit-seconds", type=float)
    root.add_argument("--energy-relative-gap", type=float, default=.005)
    root.add_argument("--threads", type=int, default=1)
    root.add_argument("--process-grace-seconds", type=float, default=20)
    root.add_argument("--preprocessing-seconds", type=float, default=5)
    root.add_argument("--bedrock-model", default=os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL))
    root.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE", "hackathon"))
    root.add_argument("--aws-region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    root.add_argument("--llm-max-calls", type=int, default=2)
    root.add_argument("--llm-timeout-seconds", type=float, default=8)
    root.add_argument("--llm-max-output-tokens", type=int, default=2048)
    root.add_argument("--llm-time-fraction", type=float, default=.25)
    root.add_argument("--instance-context-bytes", type=int, default=24000)
    root.add_argument("--decision-interval-seconds", type=float, default=15)
    root.add_argument("--tee", action="store_true", help="Mostrar también logs SCIP/LLM en vivo.")
    root.add_argument("--resume", action="store_true")
    root.add_argument("--dry-run", action="store_true", help="Preparar y listar, sin resolver ni llamar AWS.")
    return root


def _search(args, mode, fixed):
    overrides = PRESETS.get(mode, fixed)
    if mode in {"adaptive", "adaptive_knobs"} and args.adaptive_start == "standard":
        overrides = {}
    return SearchConfig(
        policy="adaptive" if mode in {"adaptive", "adaptive_knobs"} else "standard",
        route_policy_overrides=overrides, local_rule_control=mode == "rules",
        llm_route_hints=mode != "adaptive_knobs",
        bedrock=BedrockConfig(
            model_id=args.bedrock_model, profile=args.aws_profile or None,
            region=args.aws_region, timeout_seconds=args.llm_timeout_seconds,
            reasoning_effort="low", max_output_tokens=args.llm_max_output_tokens,
        ),
        max_llm_calls=args.llm_max_calls, llm_time_fraction=args.llm_time_fraction,
        instance_context_bytes=args.instance_context_bytes,
        decision_interval_seconds=args.decision_interval_seconds, show_llm_trace=True,
    )


def _prepare_case(directory, customers, seed, family, seconds):
    metadata = directory / "case.json"
    if metadata.exists():
        info = json.loads(metadata.read_text())
        for name, digest in info["files"].items():
            if _sha(directory / name) != digest:
                raise ValueError(f"Entrada sintética modificada: {directory / name}")
        return info
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"Preparación incompleta en {directory}; use una salida nueva.")
    began = perf_counter()
    generated = make_case(customers, seed, family)
    generation_seconds = perf_counter() - began
    began = perf_counter()
    compact, archive = prepare_service_graph(
        generated.road, preprocessing_seconds=seconds,
    )
    check_service_context(compact, generated.road, archive)
    preparation_seconds = perf_counter() - began
    directory.mkdir(parents=True, exist_ok=True)
    save_instance(generated.road, directory / "road.json")
    save_instance(compact, directory / "instance.json")
    _save(directory / "paths.json", archive.model_dump(mode="json"))
    # Archivo de auditoría separado; el job hijo recibe solo road/instance/paths.
    _save(directory / "witness-audit.json", generated.witness.model_dump(mode="json"))
    info = {
        **generated.description, "case_id": directory.name,
        "physical_sha256": physical_hash(generated.road),
        "pricing_sha256": fingerprint(compact),
        "generation_and_witness_validation_seconds": generation_seconds,
        "preprocessing_and_audit_seconds": preparation_seconds,
        "pricing_nodes": len(compact.nodes), "pricing_arcs": len(compact.arcs),
        "files": {name: _sha(directory / name) for name in (
            "road.json", "instance.json", "paths.json", "witness-audit.json",
        )},
    }
    _save(metadata, info)
    return info


def load_fixed(path, source_hash):
    if path is None:
        raise ValueError("compare necesita --fixed-policy del piloto, o solo --policies standard.")
    selected = json.loads(path.read_text())
    if selected.get("schema_version") != "1.0" or selected.get("source") != "synthetic_pilot":
        raise ValueError("El archivo no es una política congelada de este piloto.")
    if selected.get("code_sha256") != source_hash:
        raise ValueError("La política fue elegida con otro código; repita el piloto.")
    RoutePolicy.model_validate(selected["route_policy_overrides"])
    return selected


def summarize(item, case, execution, result, budget, gap):
    phases = {p["name"]: p for p in result.get("solve", {}).get("phases", [])}
    tuning = result.get("tuning", {})
    search = result.get("solve", {}).get("search") or {}
    kpis = result.get("kpis", {})
    valid = (
        execution["returncode"] == 0 and kpis.get("feasible") is True
        and (result.get("validation") or {}).get("feasible") is True
        and (result.get("road_validation") or {}).get("feasible") is True
    )
    deliveries = kpis.get("served_deliveries") if valid else None
    energy = kpis.get("net_battery_energy_kwh") if valid else None
    full = valid and deliveries == case["customers"]
    energy_phase = phases.get("energy", {})
    relative_gap = energy_phase.get("relative_gap")
    bound = energy_phase.get("best_bound")
    gap_hit = bool(
        full and isinstance(relative_gap, (float, int)) and math.isfinite(relative_gap)
        and isinstance(bound, (float, int)) and math.isfinite(bound)
        and bound <= energy + 1e-7
        and (relative_gap <= gap if gap > 0 else energy_phase.get("proven_optimal", False))
    )
    first_full = search.get("first_full_delivery_seconds") if full else None
    elapsed = execution["wall_seconds"]
    prep = case["preprocessing_and_audit_seconds"]
    records = tuning.get("decisions", [])
    usages = [(d.get("usage") or {}).get("totalTokens") for d in records]
    tokens_known = len(usages) == tuning.get("calls", 0) and all(
        isinstance(n, int) and n >= 0 for n in usages
    )
    return {
        **item, "family": case["family"], "customers": case["customers"],
        "instance_seed": case["instance_seed"], "returncode": execution["returncode"],
        "status": result.get("status", "execution_error"),
        "feasible": valid, "deliveries": deliveries, "energy_kwh": energy,
        "served_visit_ids": sorted((result.get("solve", {}).get("solution") or {}).get("served_visit_ids", [])) if valid else None,
        "distance_km": kpis.get("distance_km") if valid else None,
        "charging_stops": kpis.get("charging_stops") if valid else None,
        "minimum_battery_kwh": kpis.get("minimum_battery_kwh") if valid else None,
        "operational_duration_seconds": kpis.get("operational_duration_seconds") if valid else None,
        "full_service": full, "energy_gap_reached": gap_hit,
        "energy_bound_kwh": bound, "energy_relative_gap": relative_gap,
        "deliveries_proven": phases.get("deliveries", {}).get("proven_optimal", False),
        "first_full_delivery_solver_seconds": first_full,
        "first_full_within_solver_budget": full and first_full is not None and first_full <= budget,
        "solver_seconds": result.get("runtime_seconds", {}).get("resolution_including_model"),
        "process_wall_seconds": elapsed, "preprocessing_seconds": prep,
        "cold_pipeline_estimate_seconds": prep + elapsed,
        "time_to_gap_cold_estimate_seconds": prep + elapsed if gap_hit else None,
        "llm_status": tuning.get("status"), "llm_calls": tuning.get("calls", 0),
        "llm_applied": tuning.get("applied_decisions", 0),
        "llm_algorithm_changes": tuning.get("decisions_changing_algorithm", 0),
        "llm_total_tokens": sum(usages) if tokens_known else None,
        "llm_input_tokens": sum((d.get("usage") or {}).get("inputTokens", 0) for d in records) if tokens_known else None,
        "llm_output_tokens": sum((d.get("usage") or {}).get("outputTokens", 0) for d in records) if tokens_known else None,
        "llm_model": tuning.get("model_id"),
        "order_hints": [entry for entry in search.get("heuristic_progress", [])
                        if entry.get("event") == "order_hint_evaluated"],
        "llm_inference_seconds_overlapping": tuning.get("runtime_seconds", 0),
        "local_rule_updates": len(tuning.get("local_decisions", [])),
        "physical_sha256": case["physical_sha256"],
    }


def select_fixed(rows, cases, source_hash, objective="coverage", *, allow_failures=False):
    by_mode = defaultdict(list)
    for row in rows:
        by_mode[row["policy"]].append(row)
    failed = {mode: sum(r["returncode"] != 0 for r in values)
              for mode, values in by_mode.items() if any(r["returncode"] != 0 for r in values)}
    if not by_mode or (failed and not allow_failures):
        raise ValueError("El piloto tiene errores de ejecución; no se congela un ganador.")
    if len({len(values) for values in by_mode.values()}) != 1:
        raise ValueError("Piloto desbalanceado: todos los presets deben probar los mismos casos.")
    eligible = {mode: values for mode, values in by_mode.items() if mode not in failed}
    if not eligible:
        raise ValueError("Todos los presets tuvieron errores de ejecución; no hay política elegible.")
    if any(r["full_service"] and r["first_full_delivery_solver_seconds"] is None for r in rows):
        raise ValueError("Falta el tiempo de servicio completo; no se congela una política "
                         "con telemetría incompleta.")
    scores = {}
    for mode, values in eligible.items():
        scores[mode] = (
            -mean(float(r["first_full_within_solver_budget"]) for r in values),
            mean(1 - (r["deliveries"] or 0) / r["customers"] for r in values),
            mean(r["first_full_delivery_solver_seconds"] if r["first_full_within_solver_budget"]
                 else 2 * r["budget_seconds"] for r in values),
        )
        if objective == "lexicographic":
            scores[mode] = (*scores[mode][:-1],
                            mean(r["energy_kwh"] or 0 for r in values), scores[mode][-1])
    chosen = min(scores, key=lambda name: (scores[name], name != "standard", name))
    return {
        "schema_version": "1.0", "source": "synthetic_pilot",
        "code_sha256": source_hash, "generator_version": GENERATOR_VERSION,
        "selected_preset": chosen, "route_policy_overrides": PRESETS[chosen],
        "selection": ("Full-service rate, unserved fraction, mean energy, PAR2 time."
                      if objective == "lexicographic" else
                      "Lexicographic: full-service rate, unserved fraction, PAR2 full-service time."),
        "selection_scores": scores,
        "excluded_presets_with_execution_failures": failed,
        "pilot_runs_including_failures": len(rows),
        "development_physical_hashes": sorted(c["physical_sha256"] for c in cases),
        "development_instance_seeds": sorted({c["instance_seed"] for c in cases}),
        "development_cases": [
            {k: c[k] for k in ("family", "customers", "instance_seed")} for c in cases
        ],
        "all_development_runs_reached_full_service": all(r["full_service"] for r in rows),
        "any_development_run_reached_full_service": any(r["full_service"] for r in rows),
        "no_test_results_used": True,
    }


def comparisons(rows):
    """Mantener fallos; el speedup de tiempo queda condicionado a éxito conjunto."""
    by_mode = defaultdict(list)
    for row in rows:
        by_mode[row["policy"]].append(row)
    base_name = "fixed" if "fixed" in by_mode else "standard"
    baseline = {(r["case_id"], r["solver_seed"]): r for r in by_mode.get(base_name, [])}
    result = {"baseline": base_name, "modes": {}}
    for mode, values in by_mode.items():
        by_case = defaultdict(list)
        matched = []
        for row in values:
            other = baseline.get((row["case_id"], row["solver_seed"]))
            if other is None:
                continue
            matched.append((other, row))
            if other["energy_gap_reached"] and row["energy_gap_reached"]:
                by_case[row["case_id"]].append(math.log(
                    other["time_to_gap_cold_estimate_seconds"] /
                    row["time_to_gap_cold_estimate_seconds"],
                ))
        log_ratios = [mean(v) for v in by_case.values()]
        interval = None
        if len(log_ratios) >= 2:
            rng = random.Random(0)
            samples = sorted(math.exp(mean(rng.choices(log_ratios, k=len(log_ratios))))
                             for _ in range(2000))
            interval = [samples[49], samples[1949]]
        times = [r["first_full_delivery_solver_seconds"] for r in values
                 if r["first_full_delivery_solver_seconds"] is not None]
        missing_times = sum(
            r["full_service"] and r["first_full_delivery_solver_seconds"] is None for r in values
        )
        energy_pairs = [(a, b) for a, b in matched if
                        a["feasible"] and b["feasible"] and a["deliveries"] == b["deliveries"]]
        result["modes"][mode] = {
            "runs": len(values), "feasible_runs": sum(r["feasible"] for r in values),
            "full_service_runs": sum(r["full_service"] for r in values),
            "full_service_within_solver_budget_runs": sum(
                r["first_full_within_solver_budget"] for r in values
            ),
            "gap_reached_runs": sum(r["energy_gap_reached"] for r in values),
            "execution_failures": sum(r["returncode"] != 0 for r in values),
            "mean_delivery_fraction": mean((r["deliveries"] or 0) / r["customers"] for r in values),
            "median_full_seconds_when_reached": median(times) if times else None,
            "full_service_runs_missing_time": missing_times,
            "full_service_par2_mean_solver_seconds": None if missing_times else mean(
                r["first_full_delivery_solver_seconds"] if r["first_full_within_solver_budget"]
                else 2 * r["budget_seconds"] for r in values
            ),
            "median_process_wall_seconds": median(r["process_wall_seconds"] for r in values),
            "llm_runs_with_algorithm_changes": sum(r["llm_algorithm_changes"] > 0 for r in values),
            "same_delivery_energy_pairs": len(energy_pairs),
            "energy_wins_at_equal_deliveries": sum(
                b["energy_kwh"] < a["energy_kwh"] - 1e-7 for a, b in energy_pairs
            ),
            "energy_losses_at_equal_deliveries": sum(
                b["energy_kwh"] > a["energy_kwh"] + 1e-7 for a, b in energy_pairs
            ),
            "mean_energy_delta_kwh_at_equal_deliveries": (
                mean(b["energy_kwh"] - a["energy_kwh"] for a, b in energy_pairs)
                if energy_pairs else None
            ),
            "joint_gap_success_cases": len(log_ratios),
            "gap_speedup_geomean_on_joint_success": math.exp(mean(log_ratios)) if log_ratios else None,
            "gap_speedup_bootstrap_95_by_instance": interval,
        }
    return result


def _write_summary(output, rows):
    _save(output / "summary.json", rows)
    if not rows:
        return
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    stats = comparisons(rows)
    _save(output / "comparisons.json", stats)
    lines = [
        "# Benchmark sintético del control de búsqueda",
        "",
        "Los testigos no se entregaron al solver ni al LLM. No se usaron datos evaluation.",
        "Los fallbacks del LLM y los fallos permanecen en la comparación.",
        "",
        "| Modo | Corridas | Factibles | Todas las entregas | Gap alcanzado | LLM con cambios |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, values in stats["modes"].items():
        lines.append(f"| {mode} | {values['runs']} | {values['feasible_runs']} | "
                     f"{values['full_service_runs']} | {values['gap_reached_runs']} | "
                     f"{values['llm_runs_with_algorithm_changes']} |")
    lines += [
        "", "El tiempo frío es una estimación: preparación medida una vez + proceso de resolución.",
        "El proceso incluye lectura, solver, inferencia solapada, validación y escritura.",
        "El tiempo asociado al gap es el de finalización con ese gap: no se reconstruye",
        "el primer instante exacto en que se alcanzó.",
        "La generación y validación del testigo son costo de construir el dataset, separados.",
        "first_full_delivery_solver_seconds es la primera observación del motor, no un instante",
        "reconstruido dentro de operaciones indivisibles. Los presupuestos del solver son blandos.",
        "",
        "comparisons.json incluye intervalos bootstrap por instancia para el speedup de gap",
        "solo en éxitos conjuntos. Deben leerse junto a las tasas de éxito; no se eliminan",
        "timeouts para declarar una mejora general. Menos de dos instancias no produce intervalo.",
        "PAR2 asigna dos veces el presupuesto a no completar las entregas dentro del plazo.",
        "La energía se compara únicamente con igual número de entregas.",
        "",
        "Cada corrida guarda process.log, result.json y logs/decisions con las respuestas",
        "del LLM y sus cambios efectivos. Una prueba sin AWS no valida acceso al modelo.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def worker(job_path):
    job = json.loads(job_path.read_text())
    for name, record in job["inputs"].items():
        if _sha(Path(record["path"])) != record["sha256"]:
            raise ValueError(f"Entrada alterada antes de resolver: {name}")
    instance = load_instance(job["inputs"]["instance"]["path"])
    road = load_instance(job["inputs"]["road"]["path"])
    archive = PathArchive.model_validate_json(Path(job["inputs"]["paths"]["path"]).read_text())
    result = run_instance(
        instance, SolverConfig.model_validate(job["solver_config"]),
        search_config=SearchConfig.model_validate(job["search_config"]),
        road_instance=road, path_archive=archive, output_path=job["result_path"],
    )
    return 2 if result["status"] in {"error", "invalid_solution", "unavailable"} else 0


def _execute(command, directory, seconds, threads, tee):
    environment = os.environ.copy()
    environment.update(
        OMP_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS=str(threads),
        MKL_NUM_THREADS=str(threads), PYTHONUNBUFFERED="1",
    )
    started = perf_counter()
    with (directory / "process.log").open("w") as log:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, text=True, bufsize=1,
        )
        def copy():
            for line in process.stdout:
                log.write(line)
                log.flush()
                if tee:
                    print(line, end="", flush=True)
        reader = Thread(target=copy, daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            code = 124
        except KeyboardInterrupt:
            process.kill()
            process.wait()
            raise
        finally:
            reader.join(timeout=5)
            process.stdout.close()
    return code, perf_counter() - started


def run(args):
    if args.stage == "worker":
        if args.job is None:
            raise ValueError("Falta el job del proceso hijo.")
        return worker(args.job)
    if args.output_dir is None:
        raise ValueError("Falta --output-dir.")
    args.instance_seeds = args.instance_seeds or ([100, 101] if args.stage == "compare" else [0])
    args.policies = args.policies or (
        ["standard", "fixed", "rules", "adaptive"] if args.stage == "compare" else list(PRESETS)
    )
    if args.time_limit_seconds is None:
        args.time_limit_seconds = 120 if args.stage == "compare" else 30
    for name in ("customers", "families", "instance_seeds", "solver_seeds", "policies"):
        _unique(getattr(args, name), name)
    if any(n < 4 or n > 200 for n in args.customers) or min(args.instance_seeds) < 0:
        raise ValueError("Use 4..200 clientes y semillas de instancia no negativas.")
    if args.stage == "pilot" and any(p not in PRESETS for p in args.policies):
        raise ValueError("El piloto usa únicamente presets locales; nunca llama AWS.")
    if not math.isfinite(args.process_grace_seconds) or args.process_grace_seconds < 0:
        raise ValueError("El margen de proceso debe ser finito y no negativo.")
    if not math.isfinite(args.preprocessing_seconds) or args.preprocessing_seconds < 0:
        raise ValueError("El presupuesto de preparación debe ser finito y no negativo.")
    source_hash = code_hash()
    selected = None
    if args.stage == "compare" and any(p in {"fixed", "rules", "adaptive", "adaptive_knobs"} for p in args.policies):
        selected = load_fixed(args.fixed_policy, source_hash)
        if set(args.instance_seeds) & set(selected["development_instance_seeds"]):
            raise ValueError("Las semillas de prueba deben ser distintas de las del piloto.")
    fixed = selected["route_policy_overrides"] if selected else {}
    solver = SolverConfig(
        solver="scip-routes", time_limit_seconds=args.time_limit_seconds,
        energy_relative_gap=args.energy_relative_gap, threads=args.threads, tee=True,
    )
    for seed in args.solver_seeds:
        SolverConfig(seed=seed)
    searches = {p: _search(args, p, fixed) for p in args.policies}
    output = args.output_dir.resolve()
    spec = {
        "schema_version": "1.0", "stage": args.stage, "code_sha256": source_hash,
        "generator_version": GENERATOR_VERSION,
        "customers": args.customers, "families": args.families,
        "instance_seeds": args.instance_seeds, "solver_seeds": args.solver_seeds,
        "policies": args.policies, "solver_config": solver.model_dump(mode="json"),
        "search_configs": {p: s.model_dump(mode="json") for p, s in searches.items()},
        "preprocessing_seconds": args.preprocessing_seconds,
        "pilot_objective": args.pilot_objective,
        "process_grace_seconds": args.process_grace_seconds,
        "fixed_policy_sha256": _sha(args.fixed_policy) if selected else None,
        "versions": {name: importlib.metadata.version(name)
                     for name in ("pyscipopt", "numpy", "scipy", "boto3")},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "witness_given_to_solver_or_llm": False,
    }
    manifest = output / "manifest.json"
    if manifest.exists():
        if not args.resume or json.loads(manifest.read_text()) != spec:
            raise ValueError("Use otra salida o --resume con idénticos código, datos y opciones.")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("El directorio de salida debe estar vacío.")
    else:
        _save(manifest, spec)
    cases = []
    for customers in args.customers:
        for family in args.families:
            for seed in args.instance_seeds:
                identifier = f"{family}-n{customers}-instance{seed}"
                case = _prepare_case(
                    output / "instances" / identifier, customers, seed, family,
                    args.preprocessing_seconds,
                )
                if selected and case["physical_sha256"] in selected["development_physical_hashes"]:
                    raise ValueError("Se intentó evaluar una instancia usada para seleccionar la política.")
                cases.append(case)
    _save(output / "cases.json", cases)
    if args.stage == "generate":
        print(f"Generadas {len(cases)} instancias y sus testigos separados en {output}.", flush=True)
        return 0
    plan = []
    rng = random.Random(731)
    ordered = list(cases)
    rng.shuffle(ordered)
    for case in ordered:
        for seed in args.solver_seeds:
            modes = list(args.policies)
            rng.shuffle(modes)
            plan += [{"case_id": case["case_id"], "solver_seed": seed, "policy": p,
                      "budget_seconds": args.time_limit_seconds} for p in modes]
    _save(output / "plan.json", plan)
    print(json.dumps({
        "runs": len(plan), "policies": args.policies, "seconds_per_run": args.time_limit_seconds,
        "solver_budget_minutes": len(plan) * args.time_limit_seconds / 60,
        "max_real_llm_calls": sum(p["policy"] in {"adaptive", "adaptive_knobs"} for p in plan) * args.llm_max_calls,
        "dry_run": args.dry_run, "output_directory": str(output),
    }, ensure_ascii=False), flush=True)
    if args.dry_run:
        return 0
    lookup = {case["case_id"]: case for case in cases}
    rows = []
    for number, item in enumerate(plan, 1):
        if code_hash() != source_hash:
            raise ValueError("El código cambió durante el benchmark; se detiene la comparación.")
        case = lookup[item["case_id"]]
        directory = output / "runs" / f"{item['case_id']}-{item['policy']}-seed{item['solver_seed']}"
        directory.mkdir(parents=True, exist_ok=True)
        result_path, execution_path = directory / "result.json", directory / "execution.json"
        print(f"[{number}/{len(plan)}] {directory.name}", flush=True)
        if args.resume and execution_path.exists():
            execution = json.loads(execution_path.read_text())
            actual = _sha(result_path) if result_path.exists() else None
            if execution.get("result_sha256") != actual:
                raise ValueError(f"Resultado modificado: {result_path}")
        else:
            result_path.unlink(missing_ok=True)
            config = solver.model_copy(update={"seed": item["solver_seed"]})
            search = searches[item["policy"]].model_copy(update={"log_directory": str(directory / "logs")})
            base = output / "instances" / item["case_id"]
            job = {
                "solver_config": config.model_dump(mode="json"),
                "search_config": search.model_dump(mode="json"),
                "inputs": {name: {"path": str(base / filename), "sha256": case["files"][filename]}
                           for name, filename in (("road", "road.json"), ("instance", "instance.json"),
                                                  ("paths", "paths.json"))},
                "result_path": str(result_path),
            }
            _save(directory / "job.json", job)
            command = [sys.executable, "-m", "ev_routing.synthetic_benchmark",
                       "worker", "--job", str(directory / "job.json")]
            code, elapsed = _execute(
                command, directory, args.time_limit_seconds + args.process_grace_seconds,
                args.threads, args.tee,
            )
            execution = {"returncode": code, "wall_seconds": elapsed, "command": command,
                         "result_sha256": _sha(result_path) if result_path.exists() else None}
            _save(execution_path, execution)
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        row = summarize(item, case, execution, result, args.time_limit_seconds, args.energy_relative_gap)
        rows.append(row)
        _write_summary(output, rows)
        print(json.dumps({key: row[key] for key in (
            "policy", "status", "deliveries", "customers", "energy_kwh", "energy_relative_gap",
            "process_wall_seconds", "llm_applied", "llm_algorithm_changes", "local_rule_updates",
        )}, ensure_ascii=False), flush=True)
    if args.stage == "pilot":
        if all(r["returncode"] == 0 for r in rows) or args.allow_pilot_failures:
            selected = select_fixed(rows, cases, source_hash, args.pilot_objective,
                                    allow_failures=args.allow_pilot_failures)
            _save(output / "selected-policy.json", selected)
            print(f"Política congelada: {selected['selected_preset']} → {output / 'selected-policy.json'}",
                  flush=True)
            if not selected["any_development_run_reached_full_service"]:
                print("Ninguna corrida del piloto completó las entregas. Revise el presupuesto "
                      "y las métricas antes de interpretar la comparación.", flush=True)
            if selected["excluded_presets_with_execution_failures"]:
                print("Presets excluidos por fallos, conservados en summary.json: "
                      + json.dumps(selected["excluded_presets_with_execution_failures"]), flush=True)
        else:
            print("Piloto incompleto: no se congeló una política con errores de ejecución.", flush=True)
    print(f"Resumen: {output / 'report.md'}", flush=True)
    return 2 if (any(r["returncode"] != 0 for r in rows)
                 and not (args.stage == "pilot" and args.allow_pilot_failures)) else 0


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except (ValueError, OSError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
