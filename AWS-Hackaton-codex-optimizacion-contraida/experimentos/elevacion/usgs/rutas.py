"""Efecto de la elevación USGS 3DEP en las rutas: energía plano vs pendiente.

1) Carga el grafo empaquetado, inyecta `elevation` por nodo con FuenteUsgs (DEM 3DEP)
   y lo guarda como GraphML en la caché del experimento (sin tocar red.py/pipeline.py).
2) Corre evrp.resolver en competition y evaluation con energia=plano y energia=
   pendiente, pasando ese GraphML por config.red.osm_grafo.
3) Compara energía, km, orden de ruta y tiempo.

Uso:
    uv run python experimentos/elevacion/usgs/rutas.py [perfil]   # perfil: eved|ev_routing
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
import time
from pathlib import Path

import osmnx as ox

from evrp import resolver
from evrp.elevacion.usgs import FuenteUsgs

RAIZ = Path(__file__).resolve().parents[3]
GRAFO_GZ = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
SALIDA = Path(__file__).resolve().parent
GRAPHML_ELEV = SALIDA / "ann_arbor_elev_usgs.graphml"


def preparar_graphml():
    plano = RAIZ / ".cache" / "osm" / "ann_arbor_drive.graphml"
    plano.parent.mkdir(parents=True, exist_ok=True)
    if not plano.exists() or plano.stat().st_mtime < GRAFO_GZ.stat().st_mtime:
        with gzip.open(GRAFO_GZ, "rb") as a, open(plano, "wb") as b:
            shutil.copyfileobj(a, b)
    G = ox.load_graphml(plano)
    fuente = FuenteUsgs(cache_dir=str(RAIZ / ".cache" / "elevacion" / "usgs"))
    meta = fuente.aplicar(G)
    ox.save_graphml(G, GRAPHML_ELEV)
    return meta


def _orden_clientes(rutas):
    return {v: [p for p in r if p.startswith("V")] for v, r in rutas.items()}


def correr(nodos_csv, perfil, energia, grafo):
    cfg = {
        "pipeline": {"red": "osm", "energia": energia},
        "red": {"osm_grafo": str(grafo), "osm_permitir_descarga": False},
    }
    t0 = time.perf_counter()
    r = resolver(nodos_csv, cfg, [perfil], salida=None)
    seg = round(time.perf_counter() - t0, 2)
    k = r.kpis
    return {
        "energia_total_kwh": k["energia_total_kwh"],
        "km_total": k["km_total"],
        "entregas": k["entregas"],
        "factible": k["factible"],
        "tiempo_s": seg,
        "rutas": r.rutas,
        "orden_clientes": _orden_clientes(r.rutas),
    }


def comparar(nombre, nodos_csv, perfil, grafo):
    plano = correr(nodos_csv, perfil, "plano", grafo)
    pend = correr(nodos_csv, perfil, "pendiente", grafo)
    cambios = sum(1 for v in plano["orden_clientes"]
                  if plano["orden_clientes"].get(v) != pend["orden_clientes"].get(v))
    return {
        "instancia": nombre,
        "perfil": perfil,
        "plano": {k: plano[k] for k in ("energia_total_kwh", "km_total", "entregas", "tiempo_s")},
        "pendiente": {k: pend[k] for k in ("energia_total_kwh", "km_total", "entregas", "tiempo_s")},
        "delta_energia_kwh": round(pend["energia_total_kwh"] - plano["energia_total_kwh"], 4),
        "delta_km": round(pend["km_total"] - plano["km_total"], 3),
        "vehiculos_con_orden_distinto": cambios,
        "orden_plano": plano["orden_clientes"],
        "orden_pendiente": pend["orden_clientes"],
    }


def main():
    perfil = sys.argv[1] if len(sys.argv) > 1 else "eved"
    meta = preparar_graphml()
    res = {"elevacion": meta, "comparaciones": []}
    for nombre, archivo in [("competition", "competition_routing_nodes.csv"),
                            ("evaluation", "evaluation_routing_nodes.csv")]:
        res["comparaciones"].append(comparar(nombre, RAIZ / "data" / archivo, perfil, GRAPHML_ELEV))
    (SALIDA / f"rutas_{perfil}.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
