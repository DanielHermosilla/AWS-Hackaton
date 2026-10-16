"""Benchmark de las extensiones de la etapa de caminos (F0/F2/F1-lite).

Compara, por versión de opciones, sobre instancias sintéticas de 20 clientes
(semillas 1-5) + competition + evaluation:
  - tiempo de preparación (etapa 1),
  - energía total y entregas resultantes (etapa 2, MILP HiGHS, 1 hilo),
  - % de arcos de ruta distintos vs base (geometría de los tramos usados),
  - pares descartados por T_max y pares rescatados por camino alternativo.

Resultados en experimentos/dijkstra/resultados.jsonl (una línea por caso).

Uso:
    uv run python experimentos/dijkstra/bench.py                 # todo
    uv run python experimentos/dijkstra/bench.py --semillas 1 2  # subconjunto
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data"
TMP = Path(__file__).resolve().parent / "_instancias"
SALIDA = Path(__file__).resolve().parent / "resultados.jsonl"

# Versiones de opciones a comparar (todas sobre perfil eved).
VERSIONES = {
    "base": {},
    "snap_sentido": {"snap_sentido": True},
    "tiempo_arco": {"tiempo_arco": True},
    "tmax_30": {"tiempo_arco": True, "t_max_trayecto_min": 30},
    "tmax_20": {"tiempo_arco": True, "t_max_trayecto_min": 20},
    "tmax_15": {"tiempo_arco": True, "t_max_trayecto_min": 15},
    "alternativos": {"caminos_alternativos": True},
}


def _instancia_sintetica(semilla: int, n_clientes: int = 20) -> Path:
    from evrp import sintetico

    TMP.mkdir(parents=True, exist_ok=True)
    ruta = TMP / f"s{semilla}_c{n_clientes}.csv"
    if not ruta.exists():
        filas = sintetico.generar(n_clientes, semilla=semilla,
                                   referencia=DATA / "competition_routing_nodes.csv")
        sintetico.escribir(filas, ruta)
    return ruta


def _arcos_ruta(resultado) -> set[tuple[str, str]]:
    """Conjunto de arcos (i, j) de nodo clave usados en las rutas de la solución."""
    arcos = set()
    for ruta in resultado.rutas.values():
        for a, b in zip(ruta, ruta[1:]):
            arcos.add((a, b))
    return arcos


def _correr_caso(nombre_inst: str, csv: Path, perfiles: list[str]) -> list[dict]:
    import evrp

    filas = []
    base_arcos = None
    for ver, opts in VERSIONES.items():
        red = {"osm_permitir_descarga": False, **opts}
        cfg = {"red": red, "solver": {"hilos": 1, "tiempo_limite_s": 60,
                                      "presupuesto_total_s": 55}}
        t0 = time.perf_counter()
        prep = evrp.preparar(str(csv), cfg, perfiles)
        t_prep = time.perf_counter() - t0
        r = evrp.resolver_preparada(prep, cfg, perfiles)
        arcos = _arcos_ruta(r)
        if ver == "base":
            base_arcos = arcos
        distintos = len(arcos ^ base_arcos) if base_arcos is not None else 0
        union = len(arcos | base_arcos) if base_arcos else len(arcos)
        pct_dist = round(100.0 * distintos / union, 1) if union else 0.0
        ext = prep.red.get("extensiones", {})
        fila = {
            "instancia": nombre_inst, "version": ver, "opciones": opts,
            "t_preparacion_s": round(t_prep, 3),
            "entregas": r.kpis["entregas"],
            "energia_total_kwh": round(r.kpis["energia_total_kwh"], 4),
            "factible": r.kpis["factible"],
            "arcos_distintos_vs_base_pct": pct_dist,
            "pares_descartados_tmax": ext.get("pares_descartados_tmax", 0),
            "pares_rescatados": ext.get("pares_rescatados", 0),
            "clamp_recortados": (ext.get("clamp_info") or {}).get("arcos_recortados"),
        }
        filas.append(fila)
        print(f"  {nombre_inst:14s} {ver:13s} prep={t_prep:5.2f}s ent={fila['entregas']:2d} "
              f"E={fila['energia_total_kwh']:8.4f} dist%={pct_dist:4.1f} "
              f"tmax={fila['pares_descartados_tmax']:3d} resc={fila['pares_rescatados']:3d}")
    return filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--semillas", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--oficiales", nargs="+", default=["competition", "evaluation"])
    args = ap.parse_args()

    SALIDA.write_text("", encoding="utf-8")
    casos = [(f"sint_s{s}", _instancia_sintetica(s)) for s in args.semillas]
    for of in args.oficiales:
        csv = DATA / f"{of}_routing_nodes.csv"
        if csv.exists():
            casos.append((of, csv))

    with open(SALIDA, "a", encoding="utf-8") as f:
        for nombre, csv in casos:
            print(f"[{nombre}]")
            for fila in _correr_caso(nombre, csv, ["eved"]):
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                f.flush()
    print(f"\nResultados en {SALIDA}")


if __name__ == "__main__":
    main()
