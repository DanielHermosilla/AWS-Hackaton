"""CLI de la integración: el mismo ProblemInstance y pipeline que la web.

El solver y los contratos proceden de Daniel Hermosilla. Esta entrada local
no incorpora la CLI upstream porque importa el preprocesador excluido.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ev_routing.contracts import ProblemInstance, SolverConfig
from ev_routing.pipeline import run_instance


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Clave JSON duplicada: {key}")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError(f"Número JSON no finito: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="Resolver una instancia nativa de Daniel")
    run.add_argument("--instance", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--time-limit-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.time_limit_seconds <= 120:
            raise ValueError("time-limit-seconds debe estar entre 1 y 120")
        payload = json.loads(
            args.instance.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_pairs, parse_constant=_invalid_number,
        )
        # Match the HTTP boundary: JSON arrays may represent native tuples,
        # but booleans/strings must not become physical numeric values.
        instance = ProblemInstance.model_validate_json(
            json.dumps(payload, allow_nan=False), strict=True,
        )
        config = SolverConfig(
            solver="scip-routes", time_limit_seconds=args.time_limit_seconds,
            threads=1, seed=0, relative_gap=0,
        )
        result = run_instance(instance, config, output_path=args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(
        {"run_id": result["run_id"], "status": result["status"], "output": str(args.output)},
        ensure_ascii=False, allow_nan=False,
    ))
    return 0 if result["validation"] and result["validation"]["feasible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
