"""Mide el efecto de la regla de parada: sintéticos de 30 y 40 clientes, semillas 1-2,
60 s de presupuesto, 1 hilo, con y sin regla (t_min_s=15, sin_mejora_s=8).

Guarda benchmarks/resultados/parada.jsonl e imprime una tabla Markdown.
Un proceso, sin paralelismo.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RAIZ = Path(__file__).resolve().parent.parent
RES = Path(__file__).resolve().parent / "resultados" / "parada.jsonl"
REF = "data/competition_routing_nodes.csv"
PRESUPUESTO = 60.0


def _resolver(csv_path, perfil, activar):
    from evrp.api import resolver
    cfg = {"solver": {"hilos": 1, "tiempo_limite_s": PRESUPUESTO, "presupuesto_total_s": PRESUPUESTO,
                      "parada": {"activar": activar, "t_min_s": 15.0, "sin_mejora_s": 8.0}}}
    t0 = time.perf_counter()
    r = resolver(csv_path, cfg, [perfil], salida=None)
    return r, round(time.perf_counter() - t0, 2)


def main():
    from evrp.sintetico import generar, escribir
    RES.parent.mkdir(parents=True, exist_ok=True)
    (RAIZ / ".cache").mkdir(exist_ok=True)
    filas_out = []
    for clientes in (30, 40):
        for semilla in (1, 2):
            csv_path = str(RAIZ / ".cache" / f"sint{clientes}_s{semilla}.csv")
            escribir(generar(clientes, semilla=semilla, referencia=REF), csv_path)
            for perfil in ("ev_routing",):
                for activar in (False, True):
                    r, wall = _resolver(csv_path, perfil, activar)
                    k = r.kpis
                    solver = k.get("solver") or {}
                    f2 = solver.get("fase2") if isinstance(solver, dict) else None
                    if f2 is None and isinstance(solver, dict):
                        f2 = (solver.get("compacta") or {}).get("fase2")
                    parada = solver.get("parada") if isinstance(solver, dict) else None
                    if parada is None and isinstance(solver, dict):
                        parada = (solver.get("compacta") or {}).get("parada")
                    fila = {"clientes": clientes, "semilla": semilla, "perfil": perfil,
                            "parada": activar, "entregas": k["entregas"],
                            "energia_kwh": k["energia_total_kwh"], "km": k["km_total"],
                            "t_total_s": k["tiempo_computo_s"], "wall_s": wall,
                            "gap": (f2 or {}).get("gap"), "estado_f2": (f2 or {}).get("estado"),
                            "interrumpida": (parada or {}).get("interrumpida")}
                    filas_out.append(fila)
                    print(f"  c{clientes} s{semilla} parada={activar}: ent={fila['entregas']} "
                          f"E={fila['energia_kwh']:.3f} t={fila['t_total_s']:.1f}s "
                          f"gap={fila['gap']} int={fila['interrumpida']}")
    with open(RES, "w", encoding="utf-8") as f:
        for x in filas_out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    # tabla comparativa off vs on
    print("\n| clientes | semilla | E off | E on | ΔE% | t off | t on | ahorro s | int |")
    print("|---|---|---|---|---|---|---|---|---|")
    porv = {}
    for x in filas_out:
        porv.setdefault((x["clientes"], x["semilla"]), {})[x["parada"]] = x
    for (c, s), par in sorted(porv.items()):
        off, on = par.get(False), par.get(True)
        if not (off and on):
            continue
        de = 100 * (on["energia_kwh"] - off["energia_kwh"]) / off["energia_kwh"] if off["energia_kwh"] else 0
        ahorro = off["t_total_s"] - on["t_total_s"]
        print(f"| {c} | {s} | {off['energia_kwh']:.3f} | {on['energia_kwh']:.3f} | {de:+.2f} | "
              f"{off['t_total_s']:.1f} | {on['t_total_s']:.1f} | {ahorro:+.1f} | {on['interrumpida']} |")
    print(f"\n-> {RES}")


if __name__ == "__main__":
    main()
