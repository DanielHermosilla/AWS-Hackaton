"""E1 SENSIBILIDAD AL MODELO.

Para cada instancia (competition, evaluation y 10 sintéticas de 20):
  - Resuelve con modelo PLANO (perfil eved) -> rutas_plano.
  - Recalcula la ENERGÍA de rutas_plano con:
      * pendiente eVED calibrada (consumo 0.110, eta_t 0.50, eta_r 0.94),
      * temperatura frío (<0 C, 0.236 kWh/km) y templado (20-30 C, 0.127),
    sin cambiar las rutas.
  - REOPTIMIZA con el modelo pendiente-eVED -> rutas_pend; mide % de arcos
    distintos frente a rutas_plano y Δenergía (recalculada con el mismo modelo).

Pregunta: ¿cambian las RUTAS o solo los kWh?
"""
from __future__ import annotations

import json
from pathlib import Path

import comun as C

SAL = Path(__file__).resolve().parent / "e1_sensibilidad.json"
TIPO = "leaf2013"


def una(nombre, csv):
    # --- preparación plano y pendiente-eved (cacheadas en disco) ---
    cfg_plano = C.cfg_base("eved", tiempo=25.0)
    cfg_pend = C.cfg_base("eved", elevacion="eved", tiempo=25.0)
    cfg_pend_cal = C.cfg_base("eved", elevacion="eved", tiempo=25.0, consumo=C.CAL_EVED["consumo_kwh_km"])
    # consumo/eta de calibración en el tipo:
    for v in cfg_pend_cal["tipos_vehiculo"].values():
        v["eta_traccion"] = C.CAL_EVED["eta_traccion"]
        v["eta_regeneracion"] = C.CAL_EVED["eta_regeneracion"]

    prep_plano = C.preparar(csv, cfg_plano, C.INST / f"{nombre}_plano.json.gz")
    prep_pend = C.preparar(csv, cfg_pend, C.INST / f"{nombre}_pend.json.gz")

    # --- resolver plano ---
    r_plano = C.resolver(prep_plano, cfg_plano)
    rutas_plano = C.rutas_de(r_plano)
    e_plano = r_plano["kpis"]["energia_total_kwh"]

    # --- recalcular energía de rutas_plano con otros modelos (sin reoptimizar) ---
    recalc = {}
    recalc["pendiente_nominal"] = C.energia_de_rutas(prep_pend, cfg_pend, rutas_plano, TIPO)
    recalc["pendiente_calibrado_eved"] = C.energia_de_rutas(prep_pend, cfg_pend_cal, rutas_plano, TIPO)
    for etq, c in C.TEMP.items():
        cfg_t = C.cfg_base("eved", tiempo=25.0, consumo=c)
        recalc[f"temp_{etq}"] = C.energia_de_rutas(prep_plano, cfg_t, rutas_plano, TIPO)

    # --- reoptimizar con pendiente-eved y comparar rutas ---
    r_pend = C.resolver(prep_pend, cfg_pend)
    rutas_pend = C.rutas_de(r_pend)
    # energía de ambas bajo el MISMO modelo pendiente (comparación justa):
    e_plano_bajo_pend = recalc["pendiente_nominal"]["energia_total_kwh"]
    e_pend_bajo_pend = C.energia_de_rutas(prep_pend, cfg_pend, rutas_pend, TIPO)["energia_total_kwh"]

    return {
        "nombre": nombre,
        "entregas_plano": r_plano["kpis"]["entregas"],
        "clientes": r_plano["kpis"]["clientes"],
        "energia_plano_kwh": e_plano,
        "recalculo_energia_rutas_plano": recalc,
        "reoptimizacion_pendiente": {
            "entregas": r_pend["kpis"]["entregas"],
            "dif_arcos_vs_plano": C.dif_arcos(rutas_plano, rutas_pend),
            "energia_rutas_plano_bajo_pendiente": e_plano_bajo_pend,
            "energia_rutas_pend_bajo_pendiente": e_pend_bajo_pend,
            "delta_energia_kwh": round(e_plano_bajo_pend - e_pend_bajo_pend, 4),
            "delta_energia_pct": round(100 * (e_plano_bajo_pend - e_pend_bajo_pend) /
                                       e_plano_bajo_pend, 2) if e_plano_bajo_pend else 0.0,
        },
    }


def main():
    insts = {**C.instancias_oficiales(), **C.instancias_sinteticas()}
    filas = []
    for nombre, csv in insts.items():
        try:
            fila = una(nombre, csv)
        except Exception as exc:  # noqa: BLE001
            fila = {"nombre": nombre, "error": str(exc)[:300]}
        filas.append(fila)
        print(nombre, "ok" if "error" not in fila else fila["error"][:120])
    SAL.write_text(json.dumps(filas, indent=2, ensure_ascii=False), encoding="utf-8")
    print("ESCRITO", SAL)


if __name__ == "__main__":
    main()
