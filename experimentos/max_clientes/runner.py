"""Runner: tabla instancia x (N* esperado, N* motor, energía, tiempo, formulación).

PEQUEÑAS: motor compacta, motor completa y oráculo (verdad). Verifica N* motor == N*
oráculo y energía motor == energía oráculo (fase 2 con N* fijo).
GRANDES (20 clientes, infactible atender a todos): motor compacta (+fallback) y motor
completa; se comparan entre sí (la completa es la referencia exacta).

Ejecutar:
    uv run python experimentos/max_clientes/runner.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .harness import construir_inst, correr_motor
from .oraculo import resolver_oraculo
from . import instancias as I

SALIDA = Path(__file__).resolve().parent / "resultados.json"
TOL = 1e-3


def correr_pequena(builder) -> dict:
    nombre, filas, bat, res, nveh, pista = builder()
    out = {"instancia": nombre, "n_clientes": sum(f["node_type"] == "visit" for f in filas),
           "n_cargadores": sum(f["node_type"] == "charger" for f in filas),
           "n_veh": nveh, "bateria_kwh": bat, "reserva_kwh": res, "pista": pista}
    # Oráculo (independiente)
    inst_o, cfg_o, _ = construir_inst(filas, bat, res, nveh, "compacta")
    t0 = time.perf_counter()
    orac = resolver_oraculo(inst_o)
    out["oraculo"] = {**orac, "t_s": round(time.perf_counter() - t0, 3)}
    # Motor compacta (+fallback a completa)
    inst_c, cfg_c, _ = construir_inst(filas, bat, res, nveh, "compacta")
    out["motor_compacta"] = correr_motor(inst_c, cfg_c, con_fallback=True)
    # Motor completa
    inst_f, cfg_f, _ = construir_inst(filas, bat, res, nveh, "completa")
    out["motor_completa"] = correr_motor(inst_f, cfg_f, con_fallback=False)
    # Chequeos
    nE = orac["n_estrella"]
    out["ok_n_compacta"] = out["motor_compacta"]["n_motor"] == nE
    out["ok_n_completa"] = out["motor_completa"]["n_motor"] == nE
    out["ok_energia_completa"] = (out["motor_completa"]["energia"] is not None
                                  and abs(out["motor_completa"]["energia"] - orac["energia"]) < TOL)
    return out


def correr_grande(builder) -> dict:
    nombre, filas, bat, res, nveh, pista = builder()
    out = {"instancia": nombre, "n_clientes": sum(f["node_type"] == "visit" for f in filas),
           "n_cargadores": sum(f["node_type"] == "charger" for f in filas),
           "n_veh": nveh, "bateria_kwh": bat, "reserva_kwh": res, "pista": pista}
    inst_c, cfg_c, _ = construir_inst(filas, bat, res, nveh, "compacta", tiempo=30.0)
    out["motor_compacta"] = correr_motor(inst_c, cfg_c, con_fallback=True)
    inst_f, cfg_f, _ = construir_inst(filas, bat, res, nveh, "completa", tiempo=30.0)
    out["motor_completa"] = correr_motor(inst_f, cfg_f, con_fallback=False)
    # Referencia: la completa (exacta). Comparamos N* y energía.
    nref = out["motor_completa"]["n_motor"]
    out["ok_n_coinciden"] = out["motor_compacta"]["n_motor"] == nref
    e_c = out["motor_compacta"]["energia"]
    e_f = out["motor_completa"]["energia"]
    out["ok_energia"] = (e_c is not None and e_f is not None
                         and out["motor_compacta"]["n_motor"] == nref and abs(e_c - e_f) < TOL)
    return out


def main():
    res = {"pequenas": [], "grandes": []}
    for b in I.PEQUENAS:
        r = correr_pequena(b)
        res["pequenas"].append(r)
        print(json.dumps({k: r[k] for k in ("instancia", "oraculo", "motor_compacta",
              "motor_completa", "ok_n_compacta", "ok_n_completa", "ok_energia_completa")},
              ensure_ascii=False, default=str), flush=True)
    for b in I.GRANDES:
        r = correr_grande(b)
        res["grandes"].append(r)
        print(json.dumps({k: r[k] for k in ("instancia", "motor_compacta", "motor_completa",
              "ok_n_coinciden", "ok_energia")}, ensure_ascii=False, default=str), flush=True)
    SALIDA.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n-> {SALIDA}")
    _tabla(res)


def _tabla(res):
    print("\n== PEQUEÑAS (oráculo = verdad) ==")
    print(f"{'instancia':<20}{'N*orac':>7}{'N*comp':>7}{'N*full':>7}{'E_orac':>9}{'E_full':>9}{'form':>18}")
    for r in res["pequenas"]:
        o, c, f = r["oraculo"], r["motor_compacta"], r["motor_completa"]
        print(f"{r['instancia']:<20}{o['n_estrella']:>7}{c['n_motor']:>7}{f['n_motor']:>7}"
              f"{o['energia']:>9.3f}{(f['energia'] or -1):>9.3f}{c['formulacion']:>18}")
    print("\n== GRANDES (20 clientes; completa = referencia) ==")
    print(f"{'instancia':<20}{'N*comp':>7}{'N*full':>7}{'E_comp':>9}{'E_full':>9}{'t_comp':>8}{'t_full':>8}{'form':>18}")
    for r in res["grandes"]:
        c, f = r["motor_compacta"], r["motor_completa"]
        print(f"{r['instancia']:<20}{c['n_motor']:>7}{f['n_motor']:>7}"
              f"{(c['energia'] or -1):>9.3f}{(f['energia'] or -1):>9.3f}"
              f"{c['t_total_s']:>8.2f}{f['t_total_s']:>8.2f}{c['formulacion']:>18}")


if __name__ == "__main__":
    main()
