"""Ensayo con 60 estaciones, clientes simulados opcionales y logs de SCIP/LLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ev_routing.contracts import SolverConfig
from ev_routing.heuristics import InitialSolution
from ev_routing.inputs import load_instance, save_instance
from ev_routing.search_policy import BedrockConfig, SearchConfig
from ev_routing.service_graph import REPRESENTATION, build_service_graph, fingerprint
from ev_routing.simulation import simulate_customers

PROJECT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--instance", type=Path, default=Path("artifacts/hackathon/service-instance.json"))
    result.add_argument("--road-instance", type=Path, default=Path("artifacts/hackathon/instance.json"))
    result.add_argument("--path-archive", type=Path, default=Path("artifacts/hackathon/service-paths.json"))
    result.add_argument("--initial-solution", type=Path)
    result.add_argument("--simulate-customers", type=int, metavar="TOTAL",
                        help="Conservar clientes originales y añadir ubicaciones sintéticas hasta TOTAL")
    result.add_argument("--simulation-seed", type=int, default=0,
                        help="Semilla de ubicaciones, independiente de --seed del solver (default: 0)")
    result.add_argument("--output-dir", type=Path, help="Directorio nuevo; por defecto uno por ejecución")
    result.add_argument("--time-limit-seconds", type=float, default=60)
    result.add_argument("--threads", type=int, default=1)
    result.add_argument("--seed", type=int, default=0)
    result.add_argument("--search-policy", choices=["adaptive", "standard", "deterministic"],
                        default="adaptive")
    result.add_argument("--bedrock-model", default=os.getenv("BEDROCK_MODEL_ID"))
    result.add_argument("--aws-region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    result.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE", "hackathon"))
    result.add_argument("--llm-timeout-seconds", type=float, default=8)
    result.add_argument("--llm-max-calls", type=int, default=4)
    result.add_argument("--llm-max-output-tokens", type=int, default=2048)
    result.add_argument("--llm-reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"])
    result.add_argument("--llm-time-fraction", type=float, default=.25)
    return result


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args) -> int:
    config = SolverConfig(
        solver="scip-routes", time_limit_seconds=args.time_limit_seconds,
        threads=args.threads, seed=args.seed, tee=True,
    )
    search = SearchConfig(
        policy=args.search_policy, max_llm_calls=args.llm_max_calls, show_llm_trace=True,
        llm_time_fraction=args.llm_time_fraction,
        bedrock=BedrockConfig(
            model_id=args.bedrock_model, region=args.aws_region,
            profile=args.aws_profile or None, timeout_seconds=args.llm_timeout_seconds,
            max_output_tokens=args.llm_max_output_tokens,
            reasoning_effort=args.llm_reasoning_effort,
        ),
    )
    simulating = args.simulate_customers is not None
    if simulating and args.initial_solution is not None:
        raise ValueError(
            "--initial-solution no se puede combinar con --simulate-customers: "
            "el nuevo snapshot necesita su propio arranque"
        )
    keys = ("road_instance",) if simulating else ("instance", "road_instance", "path_archive")
    inputs = {key: getattr(args, key).resolve() for key in keys}
    if args.initial_solution is not None:
        inputs["initial_solution"] = args.initial_solution.resolve()
    for key, path in inputs.items():
        if not path.is_file():
            raise ValueError(
                f"Falta --{key.replace('_', '-')}: {path}. "
                "Preparar la red y service-graph o indicar archivos existentes."
            )
    started = monotonic()
    instance = load_instance(inputs["road_instance" if simulating else "instance"])
    source_inputs = inputs.copy()
    if simulating:
        print(f"Simulando {args.simulate_customers} clientes totales; "
              f"semilla {args.simulation_seed}.", flush=True)
        instance = simulate_customers(instance, args.simulate_customers, seed=args.simulation_seed)
    counts = {"customers": len(instance.customer_ids), "chargers": len(instance.charger_ids)}
    if counts["customers"] < 1 or counts["chargers"] != 60:
        raise ValueError(f"Este ensayo exige clientes y 60 estaciones; la entrada contiene {counts}")
    if not simulating and instance.provenance.get("representation", {}).get("kind") != REPRESENTATION:
        raise ValueError("--instance debe ser el grafo de servicios, vinculado a su red y caminos")
    if "initial_solution" in inputs:
        initial = InitialSolution.model_validate_json(inputs["initial_solution"].read_text())
        if initial.instance_sha256 != fingerprint(instance):
            raise ValueError("El arranque no corresponde al snapshot seleccionado")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or Path(
        f"artifacts/test-{counts['customers']}c-60s/{stamp}-{uuid4().hex[:6]}",
    )).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"El directorio no está vacío: {output}. Elegir otro para conservar los logs.")
    output.mkdir(parents=True, exist_ok=True)
    simulation = instance.provenance.get("source_provenance", {}).get("simulation")
    if simulating:
        simulation = instance.provenance["simulation"]
        inputs = {key: output / name for key, name in (
            ("road_instance", "instance.json"), ("instance", "service-instance.json"),
            ("path_archive", "service-paths.json"),
        )}
        print("Precalculando caminos de energía mínima para los nuevos servicios…", flush=True)
        road = instance
        instance, archive = build_service_graph(road, road.parameters.movement_limit)
        # Igual que service-graph --service-movements none: no elegir ni utilizar H.
        instance.provenance["horizon_selection"] = {
            "mode": "none", "effective_horizon": None, "movement_limit_used": None,
        }
        instance.provenance["representation"]["optimality_scope"] = (
            "Rutas sin H sobre los caminos fijos disponibles; no toda la red vial."
        )
        archive.service_instance_sha256 = fingerprint(instance)
        save_instance(road, inputs["road_instance"])
        save_instance(instance, inputs["instance"])
        inputs["path_archive"].write_text(archive.model_dump_json() + "\n", encoding="utf-8")
        (output / "simulation.json").write_text(
            json.dumps(simulation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        del road, archive
    preparation_seconds = monotonic() - started
    logs = output / "logs"
    search.log_directory = str(logs)
    command = [
        sys.executable, "-u", "-m", "ev_routing.cli", "run",
        "--solver", "scip-routes", "--tee", "--show-llm-trace",
        "--time-limit-seconds", str(config.time_limit_seconds),
        "--threads", str(config.threads), "--seed", str(config.seed),
        "--search-policy", search.policy,
        "--aws-region", search.bedrock.region, "--aws-profile", search.bedrock.profile or "",
        "--llm-max-calls", str(search.max_llm_calls),
        "--llm-timeout-seconds", str(search.bedrock.timeout_seconds),
        "--llm-max-output-tokens", str(search.bedrock.max_output_tokens),
        "--llm-time-fraction", str(search.llm_time_fraction),
        "--solver-log-directory", str(logs), "--output", str(output / "result.json"),
    ]
    if search.bedrock.model_id:
        command.extend(["--bedrock-model", search.bedrock.model_id])
    if search.bedrock.reasoning_effort:
        command.extend(["--llm-reasoning-effort", search.bedrock.reasoning_effort])
    for key, path in inputs.items():
        command.extend([f"--{key.replace('_', '-')}", str(path)])
    manifest = {
        "schema_version": "1.0", "created_at_utc": stamp, **counts,
        "formulation": "complete_routes_without_h", "command": command,
        "inputs": {key: {"path": str(path), "sha256": _file_hash(path)}
                   for key, path in inputs.items()},
        "source_inputs": {key: {"path": str(path), "sha256": _file_hash(path)}
                          for key, path in source_inputs.items()},
        "simulation": simulation, "simulation_generated": simulating,
        "preparation_seconds": preparation_seconds,
        "solver_config": config.model_dump(), "search_config": search.model_dump(),
    }
    (output / "run-config.json").write_text(json.dumps(
        manifest, ensure_ascii=False, indent=2, allow_nan=False,
    ) + "\n", encoding="utf-8")
    # El hijo valida hashes de red/caminos y factibilidad antes de llamar a AWS.
    print(f"{counts['customers']} clientes, 60 estaciones; solver sin H. Salida: {output}", flush=True)
    print("SCIP y LLM en vivo; copia íntegra en run.log. Máximo una llamada Bedrock.", flush=True)
    with (output / "run.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=PROJECT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", bufsize=1,
        )
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            status = process.wait()
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    result_path = output / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        print(json.dumps({
            "status": result["status"], "deliveries": result["kpis"]["served_deliveries"],
            "energy_kwh": result["kpis"]["net_battery_energy_kwh"],
            "llm_status": result["tuning"]["status"], "llm_calls": result["tuning"]["calls"],
            "result": str(result_path), "log": str(output / "run.log"),
            "prompt": str(logs / "llm-request.json") if (logs / "llm-request.json").exists() else None,
            "decision": str(logs / "llm-decision.json")
            if (logs / "llm-decision.json").exists() else None,
        }, ensure_ascii=False), flush=True)
    return status


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
