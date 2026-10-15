"""CLI de la arena.

Uso:
    uv run python -m arena correr arena/escenarios/smoke.json --out results/arena/smoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="arena", description=__doc__)
    sub = p.add_subparsers(dest="comando", required=True)
    correr = sub.add_parser("correr", help="Corre un escenario y escribe resultados")
    correr.add_argument("escenario", type=Path)
    correr.add_argument("--out", type=Path, default=None,
                        help="Directorio de salida (por defecto results/arena/<nombre>)")
    scip = sub.add_parser("scip", help="Arena SCIP: evrp (HiGHS) vs ev_routing (flujo propio + SCIP)")
    scip.add_argument("--out", type=Path, default=Path("results/arena_scip"))
    scip.add_argument("--presupuesto-companero", type=float, default=60.0)
    scip.add_argument("--presupuesto-evrp", type=float, default=60.0)
    scip.add_argument("--margen-m", type=float, default=800.0)
    scip.add_argument("--timeout-s", type=float, default=420.0)
    scip.add_argument("--hs", type=int, nargs="+", default=None)
    scip.add_argument("--instancias", nargs="+", default=None)
    args = p.parse_args(argv)

    if args.comando == "scip":
        from arena.scip_arena import correr as correr_scip
        res = correr_scip(args.out, presupuesto_companero=args.presupuesto_companero,
                          presupuesto_evrp=args.presupuesto_evrp, margen_m=args.margen_m,
                          timeout_s=args.timeout_s, hs=args.hs, instancias=args.instancias)
        print(f"Listo. {len(res['filas'])} filas. Salida: {res['out']}")
        return 0

    if args.comando == "correr":
        from arena.runner import cargar_escenario, correr as correr_escenario
        esc = cargar_escenario(args.escenario)
        out = args.out or Path("results/arena") / esc.get("nombre", "arena")
        res = correr_escenario(args.escenario, out)
        print(f"Listo. Motores: {len(res['motores'])} filas; "
              f"solvers: {len(res['solvers'])} filas. Salida: {res['out']}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
