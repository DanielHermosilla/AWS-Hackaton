"""Construye la elevación USGS 3DEP sobre el grafo empaquetado y reporta cobertura.

Uso:
    uv run python -m experimentos.elevacion.usgs.construir

Descarga (una vez, a .cache/elevacion/usgs) el DEM 3DEP del bbox del grafo, corre
FuenteUsgs.elevar(G) y guarda experimentos/elevacion/usgs/cobertura.json
"""
from __future__ import annotations

import gzip
import json
import shutil
import time
from pathlib import Path

import osmnx as ox

from evrp.elevacion.usgs import FuenteUsgs

RAIZ = Path(__file__).resolve().parents[3]
GRAFO_GZ = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
SALIDA = Path(__file__).resolve().parent


def cargar_grafo():
    plano = RAIZ / ".cache" / "osm" / "ann_arbor_drive.graphml"
    plano.parent.mkdir(parents=True, exist_ok=True)
    if not plano.exists() or plano.stat().st_mtime < GRAFO_GZ.stat().st_mtime:
        with gzip.open(GRAFO_GZ, "rb") as a, open(plano, "wb") as b:
            shutil.copyfileobj(a, b)
    return ox.load_graphml(plano)


def main():
    G = cargar_grafo()
    fuente = FuenteUsgs(cache_dir=str(RAIZ / ".cache" / "elevacion" / "usgs"))
    t0 = time.perf_counter()
    alturas, meta = fuente.elevar(G)
    meta["segundos"] = round(time.perf_counter() - t0, 2)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "cobertura.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
