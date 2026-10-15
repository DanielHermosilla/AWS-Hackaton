import argparse
import json
from pathlib import Path
from typing import Any

from .contracts import ProblemInstance, SolverConfig
from .inputs import load_problem_instance_from_csv
from .pipeline import run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EV routing solver")
    parser.add_argument("--csv", type=str, help="input nodes CSV")
    parser.add_argument("--instance", type=str, help="instance JSON")
    parser.add_argument("--output", type=str, required=True, help="output JSON path")
    parser.add_argument("--movement-limit", type=int, default=6)
    parser.add_argument("--capacity", type=float, default=24.0)
    parser.add_argument("--reserve", type=float, default=None)
    parser.add_argument("--initial-soc", type=float, default=0.6)
    parser.add_argument("--vehicles", type=int, default=2)
    parser.add_argument("--time-limit", type=float, default=300.0)
    args = parser.parse_args(argv)

    if args.instance:
        data = json.loads(Path(args.instance).read_text(encoding="utf-8"))
        instance = ProblemInstance(**data)
    elif args.csv:
        instance = load_problem_instance_from_csv(
            args.csv,
            movement_limit=args.movement_limit,
            battery_capacity_kwh=args.capacity,
            reserve_kwh=args.reserve,
            initial_soc=args.initial_soc,
            num_vehicles=args.vehicles,
        )
    else:
        raise SystemExit("provide --csv or --instance")

    solver_config = SolverConfig(time_limit_seconds=args.time_limit)
    result = run(instance, solver_config)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
