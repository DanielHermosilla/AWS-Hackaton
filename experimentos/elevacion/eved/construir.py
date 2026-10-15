"""Construye la elevación eVED sobre el grafo empaquetado y reporta cobertura.

Uso:
    uv run python -m experimentos.elevacion.eved.construir [radio_m] [interpolacion]

Descomprime el grafo .gz empaquetado, corre FuenteEved.elevar(G) y guarda:
    experimentos/elevacion/eved/cobertura.json
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
import time
from pathlib import Path

import osmnx as ox

from evrp.elevacion.eved import FuenteEved

RAIZ = Path(__file__).resolve().parents[3]
GRAFO_GZ = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
CSV = RAIZ / "data" / "eVED_EV.csv"
SALIDA = Path(__file__).resolve().parent


def cargar_grafo() -> "ox.MultiDiGraph":
    plano = RAIZ / ".cache" / "osm" / "ann_arbor_drive.graphml"
    plano.parent.mkdir(parents=True, exist_ok=True)
    if not plano.exists() or plano.stat().st_mtime < GRAFO_GZ.stat().st_mtime:
        with gzip.open(GRAFO_GZ, "rb") as a, open(plano, "wb") as b:
            shutil.copyfileobj(a, b)
    return ox.load_graphml(plano)


def main():
    radio = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    interp = sys.argv[2] if len(sys.argv) > 2 else "idw"
    G = cargar_grafo()
    fuente = FuenteEved(CSV, radio_m=radio, interpolacion=interp)
    t0 = time.perf_counter()
    alturas, meta = fuente.elevar(G)
    meta["segundos"] = round(time.perf_counter() - t0, 2)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "cobertura.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
