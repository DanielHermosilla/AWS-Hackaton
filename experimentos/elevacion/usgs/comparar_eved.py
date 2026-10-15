"""Compara USGS 3DEP contra eVED: error de altura en los nodos que eVED mide directo.

eVED solo tiene dato observado (no interpolado) en ~16 % de los nodos. En ESOS
nodos comparamos la altura USGS (DEM) contra la altura eVED (mediana de telemetría)
y reportamos el error (USGS − eVED): MAE, RMSE, sesgo y percentiles. Es la medida
más limpia porque evita comparar contra valores que eVED inventó por interpolación.

Uso:
    uv run python -m experimentos.elevacion.usgs.comparar_eved
"""
from __future__ import annotations

import gzip
import json
import shutil
import time
from pathlib import Path

import numpy as np
import osmnx as ox

from evrp.elevacion.eved import FuenteEved
from evrp.elevacion.usgs import FuenteUsgs

RAIZ = Path(__file__).resolve().parents[3]
GRAFO_GZ = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
CSV = RAIZ / "data" / "eVED_EV.csv"
SALIDA = Path(__file__).resolve().parent


def cargar_grafo():
    plano = RAIZ / ".cache" / "osm" / "ann_arbor_drive.graphml"
    plano.parent.mkdir(parents=True, exist_ok=True)
    if not plano.exists() or plano.stat().st_mtime < GRAFO_GZ.stat().st_mtime:
        with gzip.open(GRAFO_GZ, "rb") as a, open(plano, "wb") as b:
            shutil.copyfileobj(a, b)
    return ox.load_graphml(plano)


def _directos_eved(fuente: FuenteEved, G):
    """Reproduce la asignación de eVED para saber qué nodos tienen dato DIRECTO
    (observado) y su altura por mediana, sin interpolación."""
    from scipy.spatial import cKDTree

    nodos = list(G.nodes)
    nlat = np.array([float(G.nodes[v]["y"]) for v in nodos])
    nlon = np.array([float(G.nodes[v]["x"]) for v in nodos])
    plat, plon, ph = fuente._leer_puntos()
    lat0 = float(nlat.mean()); lon0 = float(nlon.mean())
    xy_nodos = fuente._proyectar(nlat, nlon, lat0, lon0)
    xy_puntos = fuente._proyectar(plat, plon, lat0, lon0)
    arbol = cKDTree(xy_nodos)
    dpn, ipn = arbol.query(xy_puntos, k=1)
    dentro = dpn <= fuente.radio_m
    asign: dict[int, list[float]] = {}
    for idx_nodo, h, ok in zip(ipn, ph, dentro):
        if ok:
            asign.setdefault(int(idx_nodo), []).append(float(h))
    directos = {int(nodos[i]): float(np.median(v)) for i, v in asign.items()}
    return directos


def main():
    G = cargar_grafo()
    t0 = time.perf_counter()
    f_usgs = FuenteUsgs(cache_dir=str(RAIZ / ".cache" / "elevacion" / "usgs"))
    alt_usgs, meta_usgs = f_usgs.elevar(G)
    t_usgs = round(time.perf_counter() - t0, 2)

    f_eved = FuenteEved(CSV, radio_m=120.0, interpolacion="idw")
    directos = _directos_eved(f_eved, G)

    pares = [(alt_usgs[v], h_eved) for v, h_eved in directos.items() if v in alt_usgs]
    u = np.array([p[0] for p in pares]); e = np.array([p[1] for p in pares])
    dif = u - e
    res = {
        "nodos_comparados": int(len(pares)),
        "fuente_a": "usgs", "fuente_b": "eved_directo",
        "mae_m": round(float(np.mean(np.abs(dif))), 2),
        "rmse_m": round(float(np.sqrt(np.mean(dif ** 2))), 2),
        "sesgo_medio_m_usgs_menos_eved": round(float(np.mean(dif)), 2),
        "p50_abs_m": round(float(np.percentile(np.abs(dif), 50)), 2),
        "p90_abs_m": round(float(np.percentile(np.abs(dif), 90)), 2),
        "max_abs_m": round(float(np.max(np.abs(dif))), 2),
        "corr_pearson": round(float(np.corrcoef(u, e)[0, 1]), 4),
        "usgs_rango_m": [round(float(u.min()), 1), round(float(u.max()), 1)],
        "eved_rango_m": [round(float(e.min()), 1), round(float(e.max()), 1)],
        "usgs_segundos": t_usgs,
        "usgs_desde_cache": meta_usgs.get("desde_cache"),
        "usgs_bytes_descargados": meta_usgs.get("bytes_descargados"),
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "comparar_eved.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
