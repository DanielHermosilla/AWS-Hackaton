"""Compara la altura Copernicus vs eVED en los nodos con dato DIRECTO de eVED.

eVED solo tiene dato observado en ~16 % de los nodos (el resto lo interpola). Para
una comparación justa de *error de altura*, usamos únicamente los nodos donde eVED
tiene telemetría directa (mediana de puntos dentro del radio) y medimos ahí la
diferencia Copernicus − eVED. Copernicus cubre el 100 % de los nodos (DEM denso),
así que la intersección = nodos directos de eVED.

Reporta MAE, RMSE, sesgo (media), percentiles y correlación.

    uv run --with rasterio==1.4.3 python -m experimentos.elevacion.copernicus.comparar_eved [radio_m]
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import osmnx as ox

from evrp.elevacion.copernicus import FuenteCopernicus
from evrp.elevacion.eved import FuenteEved

RAIZ = Path(__file__).resolve().parents[3]
GRAFO_GZ = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
CSV = RAIZ / "data" / "eVED_EV.csv"
CACHE_TILES = RAIZ / ".cache" / "elevacion" / "copernicus"
SALIDA = Path(__file__).resolve().parent


def cargar_grafo():
    plano = RAIZ / ".cache" / "osm" / "ann_arbor_drive.graphml"
    plano.parent.mkdir(parents=True, exist_ok=True)
    if not plano.exists() or plano.stat().st_mtime < GRAFO_GZ.stat().st_mtime:
        with gzip.open(GRAFO_GZ, "rb") as a, open(plano, "wb") as b:
            shutil.copyfileobj(a, b)
    return ox.load_graphml(plano)


def _nodos_directos_eved(G, radio_m):
    """Devuelve {nodo_osm -> altura_eved} SOLO para nodos con dato directo.

    Reusa la lógica de asignación de FuenteEved pero quedándose con los directos:
    corre elevar() y marca como directo todo nodo cuya distancia de interpolación
    sea 0 no es trivial, así que replicamos la asignación mediana por nodo aquí con
    un radio dado (idéntico al de FuenteEved).
    """
    from scipy.spatial import cKDTree

    f = FuenteEved(CSV, radio_m=radio_m, interpolacion="idw", cache_dir=None)
    plat, plon, ph = f._leer_puntos()
    nodos = list(G.nodes)
    nlat = np.array([float(G.nodes[v]["y"]) for v in nodos])
    nlon = np.array([float(G.nodes[v]["x"]) for v in nodos])
    lat0, lon0 = float(nlat.mean()), float(nlon.mean())
    xy_nodos = f._proyectar(nlat, nlon, lat0, lon0)
    xy_puntos = f._proyectar(plat, plon, lat0, lon0)
    arbol = cKDTree(xy_nodos)
    dpn, ipn = arbol.query(xy_puntos, k=1)
    dentro = dpn <= radio_m
    asign: dict[int, list[float]] = {}
    for idx_nodo, h, ok in zip(ipn, ph, dentro):
        if ok:
            asign.setdefault(int(idx_nodo), []).append(float(h))
    return {int(nodos[i]): float(np.median(hs)) for i, hs in asign.items()}


def main():
    radio = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    G = cargar_grafo()

    t0 = time.perf_counter()
    alt_cop, meta_cop = FuenteCopernicus(cache_tiles=CACHE_TILES).elevar(G)
    seg_cop = round(time.perf_counter() - t0, 2)

    directos_eved = _nodos_directos_eved(G, radio)

    pares = [(alt_cop[v], he) for v, he in directos_eved.items() if v in alt_cop]
    cop = np.array([a for a, _ in pares])
    eved = np.array([b for _, b in pares])
    dif = cop - eved  # Copernicus menos eVED

    res = {
        "radio_eved_m": radio,
        "nodos_grafo": G.number_of_nodes(),
        "nodos_directos_eved": len(directos_eved),
        "nodos_comparados": len(pares),
        "cobertura_copernicus": meta_cop.get("cobertura_directa"),
        "segundos_copernicus": seg_cop,
        "error_altura_cop_vs_eved_m": {
            "mae": round(float(np.mean(np.abs(dif))), 2),
            "rmse": round(float(np.sqrt(np.mean(dif ** 2))), 2),
            "sesgo_medio": round(float(np.mean(dif)), 2),
            "mediana_abs": round(float(np.median(np.abs(dif))), 2),
            "p90_abs": round(float(np.percentile(np.abs(dif), 90)), 2),
            "max_abs": round(float(np.max(np.abs(dif))), 2),
            "min": round(float(np.min(dif)), 2),
            "max": round(float(np.max(dif)), 2),
        },
        "correlacion_pearson": round(float(np.corrcoef(cop, eved)[0, 1]), 4),
        "rango_cop_m": [round(float(cop.min()), 1), round(float(cop.max()), 1)],
        "rango_eved_m": [round(float(eved.min()), 1), round(float(eved.max()), 1)],
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "comparacion_eved.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
