"""Analisis del grafo real para decidir el algoritmo de ruteo EV.

Lee competition_routing_nodes.csv / evaluation_routing_nodes.csv y calcula,
con distancias haversine (geodesicas), metricas que determinan que algoritmo
conviene: tamano, dispersion, alcance de bateria y densidad de cargadores.

No usa el solver ni inventa rutas: es un diagnostico de las instancias.
"""
from __future__ import annotations

import csv
import sys
from itertools import combinations
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

# Parametros del escenario oficial (config/default.json)
BATTERY_KWH = 24.0
RESERVE_KWH = 2.4
INITIAL_SOC = 0.6
# Energia por km: el modelo usa distance_only kwh_per_km. Nissan Leaf ~0.15 kWh/km.
KWH_PER_KM = 0.15


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.009 * asin(min(1.0, sqrt(h)))


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    nodes = []
    for r in rows:
        t = r["node_type"]
        t = t if t in ("base", "visit") else "charger"
        nodes.append({"id": r["node_id"], "type": t,
                      "lat": float(r["latitude"]), "lng": float(r["longitude"])})
    return nodes


def analyze(path):
    nodes = load(path)
    base = next(n for n in nodes if n["type"] == "base")
    visits = [n for n in nodes if n["type"] == "visit"]
    chargers = [n for n in nodes if n["type"] == "charger"]
    print("\n" + "=" * 62)
    print("INSTANCIA: " + path.name)
    print("=" * 62)
    print("Nodos totales : %d" % len(nodes))
    print("  base        : 1 (%s)" % base["id"])
    print("  visitas     : %d" % len(visits))
    print("  cargadores  : %d" % len(chargers))

    pos = lambda n: (n["lat"], n["lng"])

    d_base = sorted(haversine_km(pos(base), pos(v)) for v in visits)
    print("\nDistancia base->visita (km): min %.2f | media %.2f | max %.2f"
          % (d_base[0], sum(d_base) / len(d_base), d_base[-1]))

    diam = max(haversine_km(pos(a), pos(b)) for a, b in combinations(visits, 2))
    print("Diametro entre visitas (km) : %.2f" % diam)

    usable = (INITIAL_SOC * BATTERY_KWH) - RESERVE_KWH
    full_usable = BATTERY_KWH - RESERVE_KWH
    range_initial = usable / KWH_PER_KM
    range_full = full_usable / KWH_PER_KM
    print("\nEnergia utilizable inicial  : %.1f kWh (SoC %.1f, bat %.0f, reserva %.1f)"
          % (usable, INITIAL_SOC, BATTERY_KWH, RESERVE_KWH))
    print("Alcance con SoC inicial     : %.1f km @ %.2f kWh/km" % (range_initial, KWH_PER_KM))
    print("Alcance a bateria llena     : %.1f km" % range_full)

    sin_recarga = [v for v in visits if 2 * haversine_km(pos(base), pos(v)) > range_initial]
    print("\nVisitas sin ida+vuelta directa sin recargar (recta): %d/%d"
          % (len(sin_recarga), len(visits)))

    peor = 0.0
    for v in visits:
        dc = min(haversine_km(pos(v), pos(c)) for c in chargers)
        peor = max(peor, dc)
    print("Peor distancia visita->cargador mas cercano (km): %.2f" % peor)

    print("\n--- Implicacion para el MILP actual (red vial completa) ---")
    print("El modelo NO usa estos 81 nodos directamente: engancha cada uno a")
    print("la red vial OSM y crea binarias x[arco,k,r] y z[nodo,k,r].")
    print("Con |A| arcos viales (cientos-miles), K=2, H=30 => decenas/cientos")
    print("de miles de binarias. time_limit=60s rara vez cierra el gap.")


if __name__ == "__main__":
    base_dir = Path(r"C:\Users\Laptop_2\Desktop\maximo\AWS-Hackaton-main\Electromovilidad")
    targets = sys.argv[1:] or [
        str(base_dir / "competition_routing_nodes.csv"),
        str(base_dir / "evaluation_routing_nodes.csv"),
    ]
    for t in targets:
        analyze(Path(t))
