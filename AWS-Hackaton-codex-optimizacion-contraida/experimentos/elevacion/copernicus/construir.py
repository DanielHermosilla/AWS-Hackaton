"""Construye la elevación Copernicus sobre el grafo empaquetado y reporta cobertura.

Descarga (si falta) la tesela Copernicus DEM 30 m que cubre el mapa empaquetado,
muestrea la altura de cada nodo y guarda experimentos/elevacion/copernicus/cobertura.json
con cobertura, teselas, tamaño de descarga y tiempos.

Requiere rasterio para leer el GeoTIFF:
    uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.construir [bilineal|vecino]
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
import time
from pathlib import Path

import osmnx as ox

from evrp.elevacion.copernicus import FuenteCopernicus

RAIZ = Path(__file__).resolve().parents[3]
GRAFO_GZ = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
CACHE_TILES = RAIZ / ".cache" / "elevacion" / "copernicus"
SALIDA = Path(__file__).resolve().parent


def cargar_grafo():
    plano = RAIZ / ".cache" / "osm" / "ann_arbor_drive.graphml"
    plano.parent.mkdir(parents=True, exist_ok=True)
    if not plano.exists() or plano.stat().st_mtime < GRAFO_GZ.stat().st_mtime:
        with gzip.open(GRAFO_GZ, "rb") as a, open(plano, "wb") as b:
            shutil.copyfileobj(a, b)
    return ox.load_graphml(plano)


def main():
    muestreo = sys.argv[1] if len(sys.argv) > 1 else "bilineal"
    G = cargar_grafo()
    fuente = FuenteCopernicus(cache_tiles=CACHE_TILES, muestreo=muestreo)
    t0 = time.perf_counter()
    _, meta = fuente.elevar(G)
    meta["segundos_total"] = round(time.perf_counter() - t0, 2)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "cobertura.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
