"""Simula una regla de parada por estancamiento sobre curvas ya recolectadas (sin nuevas corridas).

Regla: detener en el primer instante t >= t_min en que la mejor solución lleva W segundos sin mejorar.
Se mide la energía en ese instante contra la final de la corrida completa, y el tiempo ahorrado.
"""
import json

FUENTES = ("experimentos/topk/visual.jsonl", "experimentos/ia_tuning/curvas.jsonl")


def simular(curva, w, t_min):
    sols = [p for p in curva if p["sol"] is not None]
    if not sols:
        return None
    mejor, t_mejor = sols[0]["sol"], sols[0]["t_s"]
    t0 = sols[0]["t_s"]
    for p in sols[1:]:
        # ¿se cumple la regla antes de este punto?
        t_corte = max(t_mejor + w, t0 + t_min)
        if p["t_s"] >= t_corte and p["sol"] >= mejor - 1e-9:
            return t_corte, mejor
        if p["sol"] < mejor - 1e-9:
            mejor, t_mejor = p["sol"], p["t_s"]
    t_corte = max(t_mejor + w, t0 + t_min)
    return (t_corte, mejor) if t_corte <= sols[-1]["t_s"] else (sols[-1]["t_s"], mejor)


filas = [json.loads(l) for f in FUENTES for l in open(f, encoding="utf-8")]
print("| W (s sin mejora) | t_min (s) | corridas | pérdida de energía máx | pérdida media | tiempo ahorrado medio |")
print("|---|---|---|---|---|---|")
for t_min in (0, 10, 15):
    for w in (5, 6, 7, 8):
        perd, ahorro = [], []
        for d in filas:
            sols = [p for p in d["curva"] if p["sol"] is not None]
            if not sols:
                continue
            ef, tf = sols[-1]["sol"], d["t_total_s"]
            t, e = simular(d["curva"], w, t_min)
            perd.append(100 * (e - ef) / ef)
            ahorro.append(tf - t)
        print(f"| {w} | {t_min} | {len(perd)} | {max(perd):.2f} % | {sum(perd) / len(perd):.2f} % "
              f"| {sum(ahorro) / len(ahorro):.0f} s |")
print()
print("Detalle W=8, t_min=15:")
for d in filas:
    sols = [p for p in d["curva"] if p["sol"] is not None]
    t, e = simular(d["curva"], 8, 15)
    print(f"  {d['instancia']} {d['config']} rep{d.get('rep', 0)}: corta en {t:.0f}s ({e:.3f} kWh) "
          f"vs completa {d['t_total_s']:.0f}s ({sols[-1]['sol']:.3f} kWh)")
