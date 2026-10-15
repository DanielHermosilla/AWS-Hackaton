"""E3 VARIABILIDAD Y FLOTA.

10 sintéticas (20 clientes) x vehiculos {1,2,3} x usar_todos_vehiculos {False,True}.
Mide energía total (media, rango), entregas y tiempo de cómputo. Perfil eved, 1 hilo.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import comun as C

SAL = Path(__file__).resolve().parent / "e3_flota.json"


def main():
    insts = C.instancias_sinteticas()
    cfg_prep = C.cfg_base("eved", tiempo=25.0)
    filas = []
    for nv in (1, 2, 3):
        for usar_todos in (False, True):
            res = []
            for nombre, csv_ in insts.items():
                prep = C.preparar(csv_, cfg_prep, C.INST / f"{nombre}_plano.json.gz")
                cfg = C.cfg_base("eved", vehiculos=nv, tiempo=25.0, usar_todos=usar_todos)
                r = C.resolver(prep, cfg)
                k = r["kpis"]
                res.append({"inst": nombre, "entregas": k["entregas"], "clientes": k["clientes"],
                            "energia": k["energia_total_kwh"], "t_s": k["tiempo_computo_s"],
                            "vehic_usados": sum(1 for v, rr in r["rutas"].items() if len(rr) > 2)})
            ener = [x["energia"] for x in res]
            ent = [x["entregas"] for x in res]
            ts = [x["t_s"] for x in res]
            filas.append({
                "vehiculos": nv, "usar_todos": usar_todos,
                "energia_media": round(st.mean(ener), 3),
                "energia_min": round(min(ener), 3), "energia_max": round(max(ener), 3),
                "entregas_media": round(st.mean(ent), 2), "entregas_min": min(ent),
                "todas_entregadas": sum(1 for x in res if x["entregas"] == x["clientes"]),
                "t_medio_s": round(st.mean(ts), 2), "t_max_s": round(max(ts), 2),
                "detalle": res,
            })
            print(f"nv={nv} todos={usar_todos} E_media={st.mean(ener):.2f} "
                  f"ent_media={st.mean(ent):.1f} t_med={st.mean(ts):.1f}s")
    SAL.write_text(json.dumps(filas, indent=2, ensure_ascii=False), encoding="utf-8")
    print("ESCRITO", SAL)


if __name__ == "__main__":
    main()
