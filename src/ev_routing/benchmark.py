"""Benchmark pareado de políticas sobre el mismo maestro por rutas sin H."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from ev_routing.heuristics import InitialSolution
from ev_routing.inputs import load_instance
from ev_routing.search_policy import BedrockConfig, SearchConfig
from ev_routing.service_graph import (
    PathArchive,
    check_service_context,
    expand_and_validate,
    fingerprint,
)
from ev_routing.validation import validate_solution


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument("--road-instance", type=Path)
    parser.add_argument("--path-archive", type=Path)
    parser.add_argument("--initial-solution", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--time-limit-seconds", type=float, default=60)
    parser.add_argument("--energy-relative-gap", type=float, default=0.005)
    parser.add_argument("--process-grace-seconds", type=float, default=60)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--policies", nargs="+", choices=["standard", "deterministic", "adaptive"],
        default=["standard", "deterministic", "adaptive"],
    )
    parser.add_argument("--bedrock-model", default=os.getenv("BEDROCK_MODEL_ID"))
    parser.add_argument("--aws-region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE", "hackathon"))
    parser.add_argument("--llm-max-calls", type=int, default=4)
    parser.add_argument("--llm-timeout-seconds", type=float, default=8)
    parser.add_argument("--llm-max-output-tokens", type=int, default=2048)
    parser.add_argument("--llm-instance-context-bytes", type=int, default=8000)
    parser.add_argument("--llm-reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--llm-time-fraction", type=float, default=.25)
    parser.add_argument("--decision-interval-seconds", type=float, default=15)
    parser.add_argument("--resume", action="store_true")
    return parser


def summarize_run(policy, seed, repetition, elapsed, returncode, result):
    phases = {p["name"]: p for p in result.get("solve", {}).get("phases", [])}
    search = result.get("solve", {}).get("search") or {}
    tuning = result.get("tuning", {})
    row = {
        "policy": policy, "seed": seed, "repetition": repetition,
        "status": result.get("status", "execution_error"), "returncode": returncode,
        "feasible": result.get("kpis", {}).get("feasible", False),
        "deliveries": result.get("kpis", {}).get("served_deliveries"),
        "energy_kwh": result.get("kpis", {}).get("net_battery_energy_kwh"),
        "lexicographic_optimal": result.get("solve", {}).get("lexicographic_optimal", False),
        "wall_seconds": elapsed,
        "pipeline_seconds": result.get("runtime_seconds", {}).get("total"),
        "llm_seconds": result.get("runtime_seconds", {}).get("llm"),
        "native_optimize_seconds": sum(
            p.get("native_optimize_seconds", 0) for p in search.get("phases", [])
        ) if search else None,
        "llm_status": tuning.get("status"),
        "llm_calls": tuning.get("calls", 0),
        "llm_applied": tuning.get("applied_decisions", 0),
        "llm_updates_during_solve": sum(
            d["status"] == "applied"
            and d["event"] not in {"before_decomposition", "before_search", "after_seed"}
            for d in tuning.get("decisions", [])
        ),
        "llm_comparison_eligible": policy != "adaptive" or tuning.get("applied_decisions", 0) > 0,
        "instance_sha256": result.get("instance_sha256"),
    }
    for name in ("deliveries", "energy"):
        phase = phases.get(name, {})
        for key in ("incumbent", "best_bound", "relative_gap", "proven_optimal", "termination_condition"):
            row[f"{name}_{key}"] = phase.get(key)
    for name in ("inputTokens", "outputTokens", "totalTokens"):
        values = [(d.get("usage") or {}).get(name) for d in tuning.get("decisions", [])]
        row[f"llm_{name}"] = (
            sum(values)
            if len(values) == tuning.get("calls", 0)
            and all(isinstance(v, int) and v >= 0 for v in values)
            else None
        )
    return row


def run_benchmark(args) -> int:
    from ev_routing.contracts import SolverConfig

    instance = load_instance(args.instance)
    solver_config = SolverConfig(
        solver="scip-routes", time_limit_seconds=args.time_limit_seconds, threads=args.threads,
        energy_relative_gap=args.energy_relative_gap,
    )
    if args.repetitions < 1 or args.process_grace_seconds < 0:
        raise ValueError("Repeticiones positivas y margen de proceso no negativo")
    if len(set(args.policies)) != len(args.policies) or len(set(args.seeds)) != len(args.seeds):
        raise ValueError("No repetir políticas ni semillas; usar --repetitions")
    for seed in args.seeds:
        SolverConfig(seed=seed)
    search = SearchConfig(
        policy="adaptive" if "adaptive" in args.policies else "standard",
        bedrock=BedrockConfig(
            model_id=args.bedrock_model, region=args.aws_region,
            profile=args.aws_profile or None, timeout_seconds=args.llm_timeout_seconds,
            max_output_tokens=args.llm_max_output_tokens,
            reasoning_effort=args.llm_reasoning_effort,
        ),
        max_llm_calls=args.llm_max_calls,
        llm_time_fraction=args.llm_time_fraction,
        decision_interval_seconds=args.decision_interval_seconds,
        instance_context_bytes=args.llm_instance_context_bytes,
    )
    paths = {"instance": args.instance.resolve()}
    for key in ("road_instance", "path_archive", "initial_solution"):
        path = getattr(args, key)
        if path is not None:
            paths[key] = path.resolve()
    if ("road_instance" in paths) != ("path_archive" in paths):
        raise ValueError("Proporcionar --road-instance y --path-archive juntos")
    for key, path in paths.items():
        if not path.is_file():
            raise ValueError(f"No existe el archivo --{key.replace('_', '-')}: {path}")
    road = archive = None
    if "road_instance" in paths:
        road = load_instance(paths["road_instance"])
        archive = PathArchive.model_validate_json(paths["path_archive"].read_text())
        check_service_context(instance, road, archive)
    elif instance.provenance.get("representation", {}).get("kind") in {
        "service_paths_nonnegative", "resource_paths",
    }:
        raise ValueError("La variante de servicios requiere su red y archivo de caminos")
    if "initial_solution" in paths:
        initial = InitialSolution.model_validate_json(paths["initial_solution"].read_text())
        if initial.instance_sha256 != fingerprint(instance):
            raise ValueError("La solución inicial no corresponde al snapshot seleccionado")
        if initial.solution is not None:
            validation = validate_solution(instance, initial.solution, enforce_movement_limit=False)
            if not validation.feasible:
                raise ValueError(f"Solución inicial inválida: {validation.violations}")
            if road is not None:
                _, validation, _ = expand_and_validate(
                    instance, road, archive, initial.solution, without_h=True,
                )
                if not validation.feasible:
                    raise ValueError(f"Solución inicial vial inválida: {validation.violations}")
    del road, archive  # No retener toda la red vial mientras corre cada proceso hijo.
    code = Path(__file__).parent
    code_hash = hashlib.sha256()
    for path in sorted(code.rglob("*.py")):
        code_hash.update(str(path.relative_to(code)).encode())
        code_hash.update(path.read_bytes())
    plan = []
    for repetition in range(args.repetitions):
        for seed in args.seeds:
            policies = list(args.policies)
            random.Random(seed + repetition * 1_000_003).shuffle(policies)
            plan.extend(
                {"policy": policy, "seed": seed, "repetition": repetition}
                for policy in policies
            )
    manifest = {
        "schema_version": "1.0", "engine": "SCIP complete routes without H",
        "inputs": {key: {"path": str(path), "sha256": _sha(path)} for key, path in paths.items()},
        "instance_sha256": fingerprint(instance), "code_sha256": code_hash.hexdigest(),
        "versions": {
            name: _version(name) for name in ("pyscipopt", "pyomo", "boto3", "numpy", "scipy")
        },
        "environment": {
            "platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count(),
        },
        "solver_config": solver_config.model_dump(),
        "search_config": search.model_dump(), "process_grace_seconds": args.process_grace_seconds,
        "plan": plan,
        "comparison_scope": "Same snapshot, operations, H-free route formulation, engine and resources.",
        "energy_comparison": "Only directly comparable at the same served count.",
    }
    output = args.output_dir.resolve()
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if not args.resume:
            raise ValueError("El benchmark ya existe; usar otro directorio o --resume")
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("--resume requiere mismos datos, código, versiones, recursos y plan")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("El directorio de salida debe estar vacío")
    else:
        _save(manifest_path, manifest)
    # No heredar config/default.json ni otro archivo mutable del directorio
    # de trabajo. El proceso hijo recibe exactamente los recursos del manifiesto.
    frozen_config = output / "solver-config.json"
    _save(frozen_config, {"solver": solver_config.model_dump()})
    print(json.dumps({
        "runs": len(plan), "policies": args.policies,
        "budget_seconds_per_run": args.time_limit_seconds,
        "max_llm_calls_total": args.llm_max_calls * sum(p["policy"] == "adaptive" for p in plan),
        "output_directory": str(output),
    }), flush=True)
    rows = []
    for item in plan:
        if any(_sha(path) != manifest["inputs"][key]["sha256"] for key, path in paths.items()):
            raise ValueError("Un archivo de entrada cambió durante el benchmark")
        policy, seed, repetition = item["policy"], item["seed"], item["repetition"]
        directory = output / f"{policy}-seed{seed}-rep{repetition}"
        result_path, record_path = directory / "result.json", directory / "execution.json"
        if args.resume and record_path.exists():
            execution = json.loads(record_path.read_text())
            actual = _sha(result_path) if result_path.exists() else None
            if execution.get("result_sha256") != actual:
                raise ValueError(f"Resultado modificado o ausente en {directory.name}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            # Solo una ejecución interrumpida sin execution.json puede llegar aquí.
            # Eliminar su resultado parcial evita atribuírselo al proceso nuevo.
            result_path.unlink(missing_ok=True)
            command = [
                sys.executable, "-m", "ev_routing.cli", "run", "--solver", "scip-routes",
                "--config", str(frozen_config),
                "--instance", str(paths["instance"]), "--output", str(result_path),
                "--search-policy", policy, "--time-limit-seconds", str(args.time_limit_seconds),
                "--threads", str(args.threads), "--seed", str(seed),
                "--aws-region", args.aws_region, "--aws-profile", args.aws_profile,
                "--llm-max-calls", str(args.llm_max_calls),
                "--llm-timeout-seconds", str(args.llm_timeout_seconds),
                "--llm-max-output-tokens", str(args.llm_max_output_tokens),
                "--llm-instance-context-bytes", str(args.llm_instance_context_bytes),
                "--llm-time-fraction", str(args.llm_time_fraction),
                "--decision-interval-seconds", str(args.decision_interval_seconds),
                "--solver-log-directory", str(directory / "native"),
            ]
            if args.bedrock_model:
                command += ["--bedrock-model", args.bedrock_model]
            if args.llm_reasoning_effort:
                command += ["--llm-reasoning-effort", args.llm_reasoning_effort]
            for key in ("road_instance", "path_archive", "initial_solution"):
                if key in paths:
                    command += ["--" + key.replace("_", "-"), str(paths[key])]
            environment = os.environ.copy()
            environment.update(
                OMP_NUM_THREADS=str(args.threads), OPENBLAS_NUM_THREADS=str(args.threads),
                MKL_NUM_THREADS=str(args.threads),
            )
            began = perf_counter()
            with (directory / "process.log").open("w") as log:
                try:
                    completed = subprocess.run(
                        command, stdout=log, stderr=subprocess.STDOUT, env=environment,
                        timeout=args.time_limit_seconds + args.process_grace_seconds,
                        check=False,
                    )
                    returncode = completed.returncode
                except subprocess.TimeoutExpired:
                    returncode = 124
            execution = {
                **item, "command": command, "wall_seconds": perf_counter() - began,
                "returncode": returncode,
                "result_sha256": _sha(result_path) if result_path.exists() else None,
            }
            _save(record_path, execution)
        if any(_sha(path) != manifest["inputs"][key]["sha256"] for key, path in paths.items()):
            raise ValueError("Un archivo de entrada cambió durante el benchmark")
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        row = summarize_run(
            policy, seed, repetition, execution["wall_seconds"], execution["returncode"], result,
        )
        rows.append(row)
        _save(output / "summary.json", rows)
        with (output / "summary.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps(row, ensure_ascii=False, allow_nan=False), flush=True)
    return 2 if any(
        row["returncode"] not in (0, 1)
        or row["status"] in {"error", "invalid_solution", "unavailable", "execution_error"}
        or not row["llm_comparison_eligible"] for row in rows
    ) else 0


def _version(name):
    """An optional AWS dependency must not prevent a local route benchmark."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main(argv=None) -> int:
    try:
        return run_benchmark(build_parser().parse_args(argv))
    except (ValueError, OSError, ImportError, importlib.metadata.PackageNotFoundError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
