"""Banco de pruebas de escala para el motor E-VRP.

Mide tiempo (red/preparacion, heuristica, MILP), energia, gap y entregas para
instancias sinteticas de clientes x vehiculos x semillas, con separacion de tiempos.

Uso:
    uv run python experimentos/escala/bench.py --clientes 20 40 --veh 2 3 --semillas 1 2 3 \
        --perfil ev_routing --tiempo 60 --salida experimentos/escala/baseline.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from evrp import config as cfgmod
from evrp import heuristica
from evrp.datos import cargar_nodos
from evrp.instancia import construir, tipos_desde_config
from evrp.red import crear_red, RedHaversine
from evrp.sintetico import generar, escribir
from evrp.validador import validar

RAIZ = Path(__file__).resolve().parents[2]
REF = RAIZ / "data" / "competition_routing_nodes.csv"
TMP = Path(__file__).resolve().parent / "_tmp"


def _nodos_sinteticos(nclientes: int, semilla: int) -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    filas = generar(nclientes, semilla, str(REF))
    ruta = TMP / f"syn_{nclientes}_{semilla}.csv"
    escribir(filas, ruta)
    return ruta


def _fusionar(base, extra):
    import copy
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusionar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def medir(nclientes: int, nveh: int, semilla: int, perfil: str, tiempo: float,
          overrides: dict | None = None, total: float | None = None) -> dict:
    ruta = _nodos_sinteticos(nclientes, semilla)
    extra = {"flota": [{"tipo": "leaf2013", "cantidad": nveh}],
             "solver": {"tiempo_limite_s": tiempo}}
    if overrides:
        extra = _fusionar(extra, overrides)
    # El modelo MILP solo recibe cfg["solver"], así que replicamos "escala" ahí.
    if "escala" in extra:
        extra.setdefault("solver", {})["escala"] = extra["escala"]
    cfg = cfgmod.cargar(None, extra, [perfil])

    t0 = time.perf_counter()
    nodos = cargar_nodos(ruta)
    red = crear_red(cfg)
    energia_ref = tipos_desde_config(cfg)[0].energia
    try:
        red.preparar(nodos, energia_ref)
    except Exception as exc:
        if cfg["red"].get("respaldo_linea_recta"):
            red = RedHaversine(cfg["red"]["factor_vial"])
            red.preparar(nodos, energia_ref)
        else:
            raise RuntimeError(f"red fallo: {exc}")
    inst = construir(nodos, red, cfg)
    t_red = time.perf_counter() - t0

    t1 = time.perf_counter()
    inicial = heuristica.resolver(inst, bool(cfg["solver"].get("usar_todos_vehiculos")))
    t_heur = time.perf_counter() - t1

    # Presupuesto de reloj total: el MILP recibe lo que queda tras red+heuristica,
    # menos un margen por el sobrepaso tipico de HiGHS al cortar por tiempo (~2-3 s).
    if total is not None:
        margen = float(cfg["solver"].get("escala", {}).get("overshoot_margen_s", 3.0))
        restante = max(float(cfg["solver"].get("escala", {}).get("min_s", 10.0)),
                       total - (t_red + t_heur) - margen)
        cfg["solver"]["tiempo_limite_s"] = restante

    certificado = len(inicial.atendidos) == len(inst.clientes)
    traza = {}
    t2 = time.perf_counter()
    if cfg["solver"].get("formulacion", "compacta") == "compacta":
        from evrp.milp_compacto import ModeloCompacto
        modelo = ModeloCompacto(inst, cfg["solver"], inicial)
    else:
        from evrp.milp import ModeloMILP
        modelo = ModeloMILP(inst, cfg["solver"])
    sol_milp, traza = modelo.optimizar(inicial, certificado)
    if (cfg["solver"].get("formulacion", "compacta") == "compacta"
            and (sol_milp is None or len(sol_milp.atendidos) < len(inst.clientes))):
        from evrp.milp import ModeloMILP
        sol_c, traza_c = ModeloMILP(inst, cfg["solver"]).optimizar(sol_milp or inicial, False)
        traza = {"compacta": traza, "completa": traza_c}
        if sol_c is not None and (sol_milp is None or (len(sol_c.atendidos), -sol_c.energia) >
                                  (len(sol_milp.atendidos), -sol_milp.energia)):
            sol_milp = sol_c
    t_milp = time.perf_counter() - t2

    sol = sol_milp if sol_milp is not None else inicial
    if sol_milp is not None and inicial is not None:
        if (len(inicial.atendidos), -inicial.energia) > (len(sol_milp.atendidos), -sol_milp.energia):
            sol = inicial

    rutas, tipo_de = {}, {}
    k = 0
    for dt in inst.tipos:
        propias = sol.rutas.get(dt.tipo.nombre, [])
        for idx in range(dt.tipo.cantidad):
            k += 1
            r = propias[idx] if idx < len(propias) else [inst.ini, inst.fin]
            rutas[str(k)] = [inst.real(v) for v in r]
            tipo_de[str(k)] = dt.tipo.nombre
    val = validar(inst, rutas, tipo_de)

    gap = _extraer_gap(traza)
    return {
        "clientes": nclientes, "vehiculos": nveh, "semilla": semilla, "perfil": perfil,
        "red": red.nombre, "arcos": sum(len(dt.arcos) for dt in inst.tipos),
        "cargadores": sum(len(dt.F) for dt in inst.tipos) // max(1, len(inst.tipos)),
        "t_red_s": round(t_red, 3), "t_heur_s": round(t_heur, 3), "t_milp_s": round(t_milp, 3),
        "t_total_s": round(t_red + t_heur + t_milp, 3),
        "factible": val["factible"], "entregas": val["entregas"],
        "energia_kwh": round(val["energia_total_kwh"], 4),
        "heur_entregas": len(inicial.atendidos), "heur_energia": round(inicial.energia, 4),
        "gap": gap, "origen": sol.origen,
    }


def _extraer_gap(traza: dict):
    if not traza:
        return None
    if "fase2" in traza and isinstance(traza["fase2"], dict):
        return traza["fase2"].get("gap")
    if "compacta" in traza:
        g = _extraer_gap(traza["compacta"])
        if traza.get("completa"):
            g2 = _extraer_gap(traza["completa"])
            return g2 if g2 is not None else g
        return g
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clientes", type=int, nargs="+", default=[20, 40, 60, 80, 100])
    ap.add_argument("--veh", type=int, nargs="+", default=[2, 3, 5])
    ap.add_argument("--semillas", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--perfil", default="ev_routing")
    ap.add_argument("--tiempo", type=float, default=60.0)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--overrides", default=None, help="JSON de overrides de config")
    ap.add_argument("--k", type=int, default=0, help="k_vecinos (poda heuristica de arcos)")
    ap.add_argument("--adaptativo", action="store_true", help="activa presupuesto adaptativo")
    ap.add_argument("--total", type=float, default=None,
                    help="presupuesto de reloj TOTAL; el MILP recibe total-(red+heur)")
    args = ap.parse_args()

    overrides = json.loads(args.overrides) if args.overrides else {}
    if args.k:
        overrides.setdefault("escala", {})["k_vecinos"] = args.k
    if args.adaptativo:
        overrides.setdefault("escala", {})["adaptativo"] = True
    filas = []
    for nc in args.clientes:
        for nv in args.veh:
            for s in args.semillas:
                r = medir(nc, nv, s, args.perfil, args.tiempo, overrides, args.total)
                filas.append(r)
                print(json.dumps(r, ensure_ascii=False), flush=True)
    if args.salida:
        Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.salida).write_text(json.dumps(filas, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n-> {args.salida} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
