"""Resume baseline_s1.json vs after_s1.json en una tabla para el informe."""
import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parent


def carga(nombre):
    return {(r["clientes"], r["vehiculos"]): r for r in json.load(open(D / nombre))}


b = carga("baseline_s1.json")
a = carga("after_s1.json")
print("cli veh |  base_t base_E  base_gap | after_t after_E after_gap | dE%")
for k in sorted(b):
    rb, ra = b[k], a.get(k)
    if ra is None:
        continue
    dE = 100.0 * (ra["energia_kwh"] - rb["energia_kwh"]) / rb["energia_kwh"]
    print("{:3d} {:3d} | {:6.1f} {:7.3f}  {:6.3f}  | {:6.1f} {:7.3f}  {:6.3f}  | {:+5.2f}".format(
        k[0], k[1], rb["t_total_s"], rb["energia_kwh"], rb["gap"] or 0.0,
        ra["t_total_s"], ra["energia_kwh"], ra["gap"] or 0.0, dE))
