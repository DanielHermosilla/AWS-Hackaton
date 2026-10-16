"""Genera figuras de energia20 (ejecutar con: uv run --with matplotlib==3.9.2)."""
from __future__ import annotations

import csv
import json
import statistics as st
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = Path(__file__).resolve().parent
FIG = AQUI.parents[1] / "docs" / "experimentos" / "figuras"
FIG.mkdir(parents=True, exist_ok=True)
EV = AQUI.parents[1] / "data" / "eVED_EV.csv"


def fig_e1():
    d = json.load(open(AQUI / "e1_sensibilidad.json", encoding="utf-8"))
    nombres = [x["nombre"] for x in d]
    pl = [x["energia_plano_kwh"] for x in d]
    pn = [x["recalculo_energia_rutas_plano"]["pendiente_nominal"]["energia_total_kwh"] for x in d]
    cal = [x["recalculo_energia_rutas_plano"]["pendiente_calibrado_eved"]["energia_total_kwh"] for x in d]
    arc = [x["reoptimizacion_pendiente"]["dif_arcos_vs_plano"]["pct_distintos"] for x in d]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.5))
    x = range(len(nombres))
    w = 0.27
    a1.bar([i - w for i in x], pl, w, label="plano")
    a1.bar(list(x), pn, w, label="pendiente nominal")
    a1.bar([i + w for i in x], cal, w, label="pendiente calibrado eVED")
    a1.set_xticks(list(x)); a1.set_xticklabels(nombres, rotation=60, ha="right", fontsize=7)
    a1.set_ylabel("energía total (kWh)"); a1.set_title("E1: energía de la ruta óptima-plano por modelo")
    a1.legend(fontsize=8)
    a2.bar(list(x), arc, color="tab:red")
    a2.set_xticks(list(x)); a2.set_xticklabels(nombres, rotation=60, ha="right", fontsize=7)
    a2.set_ylabel("% arcos distintos"); a2.set_title("E1: cambio de rutas al reoptimizar con pendiente")
    fig.tight_layout(); fig.savefig(FIG / "energia20_e1_sensibilidad.png", dpi=110); plt.close(fig)


def _consumos():
    viajes = {}
    previo = {}
    with open(EV, encoding="utf-8", newline="") as f:
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
    return [(d["kwh"] / d["km"], st.mean(d["oat"]) if d["oat"] else None)
            for d in viajes.values() if d["km"] > 2.0 and d["kwh"] > 0]


def fig_e2():
    e2 = json.load(open(AQUI / "e2_robustez.json", encoding="utf-8"))
    viajes = _consumos()
    cons = [c for c, _ in viajes]
    bandas = {"<0": [], "0-10": [], "10-20": [], "20-30": [], ">30": []}
    for c, o in viajes:
        if o is None:
            continue
        b = "<0" if o < 0 else "0-10" if o < 10 else "10-20" if o < 20 else "20-30" if o < 30 else ">30"
        bandas[b].append(c)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.5))
    a1.hist(cons, bins=40, color="tab:blue", alpha=0.8)
    p = e2["consumo_pctiles_kwh_km"]
    for etq, col in [("p50", "green"), ("p75", "orange"), ("p90", "red"), ("p95", "purple")]:
        a1.axvline(p[etq], color=col, ls="--", label=f"{etq}={p[etq]}")
    a1.set_xlabel("consumo por viaje (kWh/km)"); a1.set_ylabel("nº viajes")
    a1.set_title(f"E2: distribución de consumo eVED (n={e2['viajes']})"); a1.legend(fontsize=8)
    datos = [bandas[k] for k in bandas if bandas[k]]
    etiquetas = [f"{k}\n(n={len(bandas[k])})" for k in bandas if bandas[k]]
    a2.boxplot(datos, labels=etiquetas, showfliers=False)
    a2.set_ylabel("consumo (kWh/km)"); a2.set_title("E2: consumo por banda de temperatura (OAT °C)")
    fig.tight_layout(); fig.savefig(FIG / "energia20_e2_robustez.png", dpi=110); plt.close(fig)


def fig_e3():
    d = json.load(open(AQUI / "e3_flota.json", encoding="utf-8"))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.5))
    for usar in (False, True):
        xs = [f["vehiculos"] for f in d if f["usar_todos"] == usar]
        em = [f["energia_media"] for f in d if f["usar_todos"] == usar]
        elo = [f["energia_media"] - f["energia_min"] for f in d if f["usar_todos"] == usar]
        ehi = [f["energia_max"] - f["energia_media"] for f in d if f["usar_todos"] == usar]
        a1.errorbar(xs, em, yerr=[elo, ehi], marker="o", capsize=4,
                    label=f"usar_todos={usar}")
    a1.set_xlabel("vehículos"); a1.set_ylabel("energía total (kWh)")
    a1.set_title("E3: energía media (barras=rango) vs flota"); a1.legend(fontsize=8)
    a1.set_xticks([1, 2, 3])
    for usar in (False, True):
        xs = [f["vehiculos"] for f in d if f["usar_todos"] == usar]
        tm = [f["t_medio_s"] for f in d if f["usar_todos"] == usar]
        a2.plot(xs, tm, marker="s", label=f"usar_todos={usar}")
    a2.set_xlabel("vehículos"); a2.set_ylabel("tiempo de cómputo medio (s)")
    a2.set_title("E3: tiempo de cómputo vs flota"); a2.legend(fontsize=8); a2.set_xticks([1, 2, 3])
    fig.tight_layout(); fig.savefig(FIG / "energia20_e3_flota.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    fig_e1()
    fig_e2()
    fig_e3()
    print("figuras en", FIG)
