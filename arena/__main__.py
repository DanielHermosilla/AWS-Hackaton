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
    args = p.parse_args(argv)

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
