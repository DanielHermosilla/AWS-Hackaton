"""E2 ROBUSTEZ.

1) Distribución de consumo por viaje de eVED: integra Energy_Consumption*dt (kWh) y km
   por viaje (velocidad*dt). Percentiles p10..p95 del consumo (kWh/km) y por banda de OAT.
2) Planifica con p50 (modelo plano) y valida las MISMAS rutas con consumos p75/p90/p95
   en B=16 (perfil eved) y B=24 (perfil ev_routing): factibilidad, margen mínimo, energía.
"""
from __future__ import annotations

import csv
import json
import statistics as st
from datetime import datetime
from pathlib import Path

import comun as C

SAL = Path(__file__).resolve().parent / "e2_robustez.json"
EV = str(C.DATA / "eVED_EV.csv")

BANDAS = [("<0", -1e9, 0.0), ("0-10", 0.0, 10.0), ("10-20", 10.0, 20.0),
          ("20-30", 20.0, 30.0), (">30", 30.0, 1e9)]


def consumo_por_viaje(ruta, km_min=2.0):
    """Devuelve lista de (consumo_kwh_km, oat_medio) por viaje con km>km_min."""
    viajes = {}
    previo = {}
    with open(ruta, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            k = (r["VehId"], r["Trip"])
            t = datetime.strptime(r["Timestamp"], "%Y-%m-%d %H:%M:%S.%f")
            v = float(r["Vehicle Speed[km/h]"]) if r["Vehicle Speed[km/h]"] != "nan" else 0.0
            e = float(r["Energy_Consumption"]) if r["Energy_Consumption"] != "nan" else 0.0
            oat = r.get("OAT[DegC]", "nan")
            oat = float(oat) if oat not in ("", "nan") else None
            d = viajes.setdefault(k, {"km": 0.0, "kwh": 0.0, "oat": []})
            if k in previo:
                dt = (t - previo[k]).total_seconds()
                d["km"] += v * dt / 3600.0
                d["kwh"] += e * dt
            previo[k] = t
            if oat is not None:
                d["oat"].append(oat)
    out = []
    for d in viajes.values():
        if d["km"] > km_min and d["kwh"] > 0:
            out.append((d["kwh"] / d["km"], st.mean(d["oat"]) if d["oat"] else None))
    return out


def pctiles(xs, ps=(10, 25, 50, 75, 90, 95)):
    xs = sorted(xs)
    n = len(xs)
    def q(p):
        i = min(n - 1, max(0, int(round(p / 100 * (n - 1)))))
        return round(xs[i], 4)
    return {f"p{p}": q(p) for p in ps}


def banda(oat):
    for nombre, lo, hi in BANDAS:
        if lo <= oat < hi:
            return nombre
    return "n/a"


def main():
    viajes = consumo_por_viaje(EV)
    consumos = [c for c, _ in viajes]
    glob = pctiles(consumos)
    por_banda = {}
    for nombre, lo, hi in BANDAS:
        b = [c for c, o in viajes if o is not None and lo <= o < hi]
        if b:
            por_banda[nombre] = {"n": len(b), "mediana": round(st.median(b), 4),
                                 **pctiles(b, (50, 90))}

    # --- planificar con p50 y validar con p75/p90/p95 ---
    cfg_plan = C.cfg_base("eved", tiempo=25.0, consumo=glob["p50"])
    insts = {**C.instancias_oficiales(), **C.instancias_sinteticas()}
    escenarios = {}
    for perfil, Bk in [("eved", 16), ("ev_routing", 24)]:
        filas = []
        for nombre, csv_ in insts.items():
            prep = C.preparar(csv_, cfg_plan, C.INST / f"{nombre}_plano.json.gz")
            cfg_p50 = C.cfg_base(perfil, tiempo=25.0, consumo=glob["p50"])
            r = C.resolver(prep, cfg_p50)
            rutas = C.rutas_de(r)
            fila = {"inst": nombre, "entregas_p50": r["kpis"]["entregas"],
                    "energia_p50": r["kpis"]["energia_total_kwh"]}
            for pq in ("p75", "p90", "p95"):
                cfg_q = C.cfg_base(perfil, tiempo=25.0, consumo=glob[pq])
                ev = C.energia_de_rutas(prep, cfg_q, rutas, "leaf2013")
                fila[pq] = {"factible": ev["factible"], "energia": ev["energia_total_kwh"],
                            "margen_min_kwh": ev["margen_min_kwh"], "errores": len(ev["errores"])}
            filas.append(fila)
        escenarios[f"{perfil}_B{Bk}"] = filas

    out = {"viajes": len(viajes), "consumo_pctiles_kwh_km": glob,
           "por_banda_oat": por_banda, "escenarios": escenarios}
    SAL.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("viajes", len(viajes), "p50", glob["p50"], "p95", glob["p95"])
    print("ESCRITO", SAL)


if __name__ == "__main__":
    main()
