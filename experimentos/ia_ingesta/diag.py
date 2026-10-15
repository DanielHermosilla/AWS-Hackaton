"""Diagnóstico: imprime direcciones extraídas vs esperadas y el parecido.

Uso: $env:AWS_PROFILE='hackathon'; uv run python -m experimentos.ia_ingesta.diag haiku 3
(evalúa los primeros N casos de un modelo e imprime el emparejamiento).
"""
from __future__ import annotations

import sys

from evrp.ia import ClienteBedrock
from evrp.ia.ingesta import extraer

from .corpus import CORPUS
from .evaluar import MODELOS, _emparejar, _parecido


def main(argv=None):
    argv = argv or sys.argv[1:]
    alias = argv[0] if argv else "haiku"
    n = int(argv[1]) if len(argv) > 1 else 5
    modelo = MODELOS.get(alias, alias)
    c = ClienteBedrock(region="us-east-1", modelo=modelo, perfil="hackathon")
    for caso in CORPUS[:n]:
        out = extraer(texto=caso.texto, contexto="ciudad: Ann Arbor, Michigan",
                      cliente=c, modelo=modelo)
        print(f"\n=== {caso.id} ({caso.tipo}) ===")
        print("ESPERADOS:", [e.direccion for e in caso.esperados])
        print("EXTRAIDOS:", [p["direccion"] for p in out["pedidos"]])
        for ext, esp in _emparejar(out["pedidos"], caso.esperados):
            s = _parecido(ext["direccion"], esp.direccion) if ext else 0.0
            print(f"  esp={esp.direccion!r:40} ext={(ext or {}).get('direccion')!r:40} sim={s:.2f}")


if __name__ == "__main__":
    main()
