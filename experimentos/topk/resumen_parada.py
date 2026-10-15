"""Resumen de rendimiento decreciente a partir de curvas ya recolectadas (sin nuevas corridas)."""
import json


def gap_en(curva, t):
    v = [p["gap_pct"] for p in curva if p["t_s"] <= t and p["gap_pct"] is not None]
    return v[-1] if v else None


filas = [json.loads(l) for f in ("experimentos/topk/visual.jsonl", "experimentos/ia_tuning/curvas.jsonl")
         for l in open(f, encoding="utf-8")]
print("| instancia | config | heurística kWh | final kWh | mejora del MILP | t incumbente final (s) "
      "| gap 15 s | gap 30 s | gap 60 s | gap 120 s |")
print("|---|---|---|---|---|---|---|---|---|---|")
for d in filas:
    if d.get("rep", 0) != 0 or d["config"] == "base_AA":
        continue
    c = d["curva"]
    sols = [p for p in c if p["sol"] is not None]
    ef = sols[-1]["sol"]
    t_fin = next(p["t_s"] for p in sols if abs(p["sol"] - ef) < 1e-6)
    h = d["heuristica_kwh"]
    print(f"| {d['instancia']} | {d['config']} | {h:.3f} | {ef:.3f} | {100 * (h - ef) / h:.2f} % | {t_fin:.0f} "
          f"| {gap_en(c, 15)} | {gap_en(c, 30)} | {gap_en(c, 60)} | {gap_en(c, 120)} |")
