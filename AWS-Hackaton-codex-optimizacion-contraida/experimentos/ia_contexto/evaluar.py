"""Evaluación Idea D: error de consumo predicho vs eVED, por viaje.

Compara tres métodos para predecir el consumo (kWh/km) de cada viaje:
  (i)   sin ajuste: consumo global constante.
  (ii)  fórmula por temperatura (calibración por banda), sin LLM.
  (iii) LLM + fórmula: idéntico a (ii) en el factor, pero las variables provienen de
        un texto de contexto que el LLM interpreta. En la evaluación offline usamos el
        extractor de reglas sobre un texto sintético por viaje (equivale a un LLM
        perfecto en extracción); el aporte real que se mide es el de la fórmula.

Validación honesta: la calibración (fit) se hace con un subconjunto de **fechas** y la
evaluación con las fechas restantes (split temporal, no por filas). Métrica: MAE y RMSE
del consumo por viaje, y error relativo medio.
"""
from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

from evrp.ia.contexto import factor_desde_variables
from evrp.ia.contexto.calibracion import (
    BANDA_REFERENCIA, _banda_temp, calibrar_por_temperatura, viajes_para_evaluacion,
)


def _split_por_fecha(viajes, frac_fit=0.6):
    fechas = sorted({v["fecha"] for v in viajes})
    corte = fechas[int(len(fechas) * frac_fit)]
    fit = [v for v in viajes if v["fecha"] < corte]
    test = [v for v in viajes if v["fecha"] >= corte]
    return fit, test, corte


def _calibrar_desde_viajes(viajes, factor_min=0.7, factor_max=1.8, viajes_min_banda=5):
    """Replica la lógica de banda/factor sobre una lista de viajes (para el split)."""
    por_banda = {}
    for v in viajes:
        por_banda.setdefault(_banda_temp(v["oat"]), []).append(v)
    consumo_banda = {}
    for nombre, vs in por_banda.items():
        km = sum(x["km"] for x in vs)
        if km:
            consumo_banda[nombre] = sum(x["kwh"] for x in vs) / km
    consumo_global = sum(v["kwh"] for v in viajes) / sum(v["km"] for v in viajes)
    base = consumo_banda.get(BANDA_REFERENCIA, consumo_global)
    factores = {}
    for nombre, c in consumo_banda.items():
        if len(por_banda[nombre]) >= viajes_min_banda:
            f = c / base
            factores[nombre] = min(factor_max, max(factor_min, f))
    return {"consumo_global_kwh_km": consumo_global, "base": base,
            "factores": factores, "consumo_banda": consumo_banda}


def _metricas(errores):
    mae = sum(abs(e) for e in errores) / len(errores)
    rmse = math.sqrt(sum(e * e for e in errores) / len(errores))
    return {"n": len(errores), "mae": round(mae, 5), "rmse": round(rmse, 5)}


def _texto_contexto(v):
    """Texto sintético por viaje para alimentar el extractor (simula contexto operativo)."""
    oat = v["oat"]
    if oat < 0:
        clima = f"Hace {oat:.0f} grados, con nieve."
    elif oat < 10:
        clima = f"Temperatura de {oat:.0f} grados, frío."
    elif oat > 30:
        clima = f"Hace {oat:.0f} grados, mucho calor."
    else:
        clima = f"Temperatura de {oat:.0f} grados, templado."
    return clima


def evaluar(ruta_ev="data/eVED_EV.csv", salida="experimentos/ia_contexto/evaluacion.json"):
    viajes = viajes_para_evaluacion(ruta_ev)
    fit, test, corte = _split_por_fecha(viajes)
    cal = _calibrar_desde_viajes(fit)
    cal_dict = {"factores": {k: round(v, 3) for k, v in cal["factores"].items()}}
    base = cal["base"]

    err_sin, err_temp, err_llm = [], [], []
    for v in test:
        real = v["consumo"]
        # (i) sin ajuste
        err_sin.append(cal["consumo_global_kwh_km"] - real)
        # (ii) fórmula por temperatura (variables = solo temperatura, directo)
        pred_temp = base * factor_desde_variables(
            {"temperatura_c": v["oat"]}, cal_dict)["ajustes"]["consumo_factor"]
        err_temp.append(pred_temp - real)
        # (iii) LLM + fórmula: variables extraídas de texto (reglas = proxy del LLM)
        from evrp.ia.contexto import extraer_variables_reglas
        vars_ctx = extraer_variables_reglas(_texto_contexto(v))
        pred_llm = base * factor_desde_variables(vars_ctx, cal_dict)["ajustes"]["consumo_factor"]
        err_llm.append(pred_llm - real)

    reales = [v["consumo"] for v in test]
    res = {
        "viajes_fit": len(fit), "viajes_test": len(test), "fecha_corte": corte,
        "consumo_global_fit": round(cal["consumo_global_kwh_km"], 4),
        "factores_fit": cal_dict["factores"],
        "consumo_real_test_medio": round(st.mean(reales), 4),
        "metodos": {
            "i_sin_ajuste": _metricas(err_sin),
            "ii_formula_temp": _metricas(err_temp),
            "iii_llm_formula": _metricas(err_llm),
        },
    }
    # Mejora relativa de (ii) sobre (i).
    mae_i = res["metodos"]["i_sin_ajuste"]["mae"]
    mae_ii = res["metodos"]["ii_formula_temp"]["mae"]
    res["mejora_mae_ii_vs_i_pct"] = round(100 * (mae_i - mae_ii) / mae_i, 1)

    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return res


if __name__ == "__main__":
    evaluar()
