"""Campaign: local pilot, frozen paired comparison, presentation impact tables."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from ev_routing.benchmark import _save, _sha
from ev_routing.presentation_impact import ImpactFactors, report_campaign
from ev_routing.search_policy import DEFAULT_BEDROCK_MODEL
from ev_routing.synthetic_instances import FAMILIES
from ev_routing.synthetic_benchmark import PRESETS

ROOT = Path(__file__).resolve().parents[2]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["plan", "run", "report"])
    p.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/presentation-benchmark")
    p.add_argument("--impact", type=Path, default=ROOT / "config/presentation-impact.json")
    p.add_argument("--customers", nargs="+", type=int, default=[16, 24])
    p.add_argument("--families", nargs="+", choices=FAMILIES, default=["dispatch", "crossed"])
    p.add_argument("--development-seeds", nargs="+", type=int, default=[0])
    p.add_argument("--test-seeds", nargs="+", type=int, default=[1000, 1001])
    p.add_argument("--solver-seeds", nargs="+", type=int, default=[0])
    p.add_argument("--pilot-seconds", type=float, default=15)
    p.add_argument("--time-limit-seconds", type=float, default=45)
    p.add_argument("--energy-relative-gap", type=float, default=.005)
    p.add_argument("--llm-max-calls", type=int, default=2)
    p.add_argument("--llm-timeout-seconds", type=float, default=12)
    p.add_argument("--bedrock-model", default=os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL))
    p.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE", "hackathon"))
    p.add_argument("--aws-region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    p.add_argument("--ablation", action="store_true", help="Añadir AWS solo tuning, sin propuestas de rutas.")
    p.add_argument("--without-bedrock", action="store_true", help="Probar el pipeline con políticas locales.")
    p.add_argument("--tee", action="store_true", help="Mostrar SCIP, prompts, respuestas y decisiones.")
    p.add_argument("--resume", action="store_true", help="Reusar solo corridas de idéntico código y plan.")
    return p


def plan(args):
    for name in ("customers", "families", "development_seeds", "test_seeds", "solver_seeds"):
        values = getattr(args, name)
        if not values or len(values) != len(set(values)):
            raise ValueError(f"{name}: lista no vacía, sin duplicados.")
    if set(args.development_seeds) & set(args.test_seeds):
        raise ValueError("No reutilizar semillas de desarrollo como prueba.")
    if any(n < 4 or n > 200 for n in args.customers):
        raise ValueError("Use 4..200 clientes.")
    if any(n < 0 for n in args.development_seeds + args.test_seeds + args.solver_seeds):
        raise ValueError("Las semillas deben ser no negativas.")
    if any(not math.isfinite(n) or n <= 0 for n in (args.pilot_seconds, args.time_limit_seconds)):
        raise ValueError("Presupuestos de resolución positivos y finitos.")
    if not 1 <= args.llm_max_calls <= 20 or not 0 < args.llm_timeout_seconds <= 60:
        raise ValueError("Use 1..20 consultas y timeout en (0,60].")
    if not math.isfinite(args.energy_relative_gap) or not 0 <= args.energy_relative_gap <= 1:
        raise ValueError("Gap energético entre 0 y 1.")
    modes = ["standard", "fixed", "rules"]
    if not args.without_bedrock:
        modes += ["adaptive"]
        if args.ablation:
            modes += ["adaptive_knobs"]
    cases = len(args.customers) * len(args.families) * len(args.solver_seeds)
    pilot_runs = cases * len(args.development_seeds) * len(PRESETS)
    comparison_runs = cases * len(args.test_seeds) * len(modes)
    calls = cases * len(args.test_seeds) * sum(p.startswith("adaptive") for p in modes) * args.llm_max_calls
    return {
        "families": args.families, "customers": args.customers, "policies": modes,
        "pilot_runs_without_aws": pilot_runs, "comparison_runs": comparison_runs,
        "max_real_aws_calls": calls,
        "solver_budget_minutes": (pilot_runs * args.pilot_seconds + comparison_runs * args.time_limit_seconds) / 60,
        "extra_costs": "Añadir preparación, arranque y validación; inferencia incluida en el presupuesto del solver.",
        "development_seeds": args.development_seeds, "test_seeds": args.test_seeds,
        "solver_seeds": args.solver_seeds, "energy_relative_gap": args.energy_relative_gap,
        "bedrock_model": args.bedrock_model if calls else None,
        "factor_sha256": _sha(args.impact), "dataset_scope": "targeted_synthetic_demonstration",
    }


def run(args):
    args.output_dir = args.output_dir.resolve()
    ImpactFactors.model_validate_json(args.impact.read_text())
    if args.action == "report":
        report_campaign(args.output_dir / "comparison", args.impact, args.output_dir / "presentation")
        print(f"Informe: {args.output_dir / 'presentation/diapositivas.md'}")
        return 0
    specification = plan(args)
    print(json.dumps(specification, indent=2, ensure_ascii=False), flush=True)
    if args.action == "plan":
        return 0
    manifest = args.output_dir / "presentation-plan.json"
    if manifest.exists():
        if not args.resume or json.loads(manifest.read_text()) != specification:
            raise ValueError("La campaña existe; use --resume con el mismo plan o un directorio nuevo.")
    elif args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError("El directorio debe estar vacío para una campaña nueva.")
    else:
        _save(manifest, specification)
    common = [
        "--customers", *map(str, args.customers), "--families", *args.families,
        "--solver-seeds", *map(str, args.solver_seeds),
        "--energy-relative-gap", str(args.energy_relative_gap),
        "--pilot-objective", "lexicographic",
    ]
    if args.resume:
        common += ["--resume"]
    if args.tee:
        common += ["--tee"]
    prefix = [sys.executable, "-m", "ev_routing.synthetic_benchmark"]
    pilot = prefix + [
        "pilot", *common, "--instance-seeds", *map(str, args.development_seeds),
        "--time-limit-seconds", str(args.pilot_seconds),
        "--output-dir", str(args.output_dir / "pilot"),
    ]
    if subprocess.run(pilot, check=False).returncode:
        raise ValueError("Falló el piloto; no se inventa una política fija.")
    compare = prefix + [
        "compare", *common, "--instance-seeds", *map(str, args.test_seeds),
        "--time-limit-seconds", str(args.time_limit_seconds),
        "--fixed-policy", str(args.output_dir / "pilot/selected-policy.json"),
        "--policies", *specification["policies"],
        "--output-dir", str(args.output_dir / "comparison"),
        "--llm-max-calls", str(args.llm_max_calls),
        "--llm-timeout-seconds", str(args.llm_timeout_seconds),
        "--llm-time-fraction", ".5", "--instance-context-bytes", "45000",
        "--bedrock-model", args.bedrock_model,
        "--aws-profile", args.aws_profile, "--aws-region", args.aws_region,
    ]
    code = subprocess.run(compare, check=False).returncode
    if (args.output_dir / "comparison/summary.json").exists():
        report_campaign(args.output_dir / "comparison", args.impact, args.output_dir / "presentation")
        print(f"Informe: {args.output_dir / 'presentation/diapositivas.md'}", flush=True)
    return code


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
