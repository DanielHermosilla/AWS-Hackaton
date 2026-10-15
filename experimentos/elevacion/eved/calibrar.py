"""Calibración de c, η_d, η_r del ModeloEnergia con viajes eVED (fuente elevación eVED).

Modelo por tramo (ver src/evrp/energia.py)::

    e = c·ℓ + κ·( [Δh]⁺/η_d − η_r·[Δh]⁻ ),   κ = m·g/3.6e6

Integrado por viaje::

    E_viaje = c·L + κ·( S⁺/η_d − η_r·S⁻ )

donde L = Σ ℓ (km), S⁺ = Σ [Δh]⁺ (subidas, m) y S⁻ = Σ [Δh]⁻ (bajadas, m, valor
positivo). La energía observada E_obs se integra con el Δt real entre filas
(README §9.1: la suma directa de Energy_Consumption sobrestima ~2×), igual que en
`energia.calibrar_eved`. La distancia se integra con la velocidad.

Ajuste (lineal en los coeficientes a=c, b=κ/η_d, d=κ·η_r)::

    E_obs ≈ a·L + b·S⁺ − d·S⁻

Resolvemos por mínimos cuadrados **no negativos** (a,b,d ≥ 0) y recuperamos::

    c = a,   η_d = κ/b,   η_r = d/κ

con κ fijo por la masa del vehículo. Validación: separación por viajes (no filas)
en train/test; se compara el error de energía por viaje del modelo PLANO (solo c)
frente al modelo con PENDIENTE.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

G_GRAV = 9.81


def extraer_viajes(ruta_ev: str | Path, km_min: float = 2.0, max_filas: int | None = None) -> list[dict]:
    """Devuelve por viaje: L (km), S⁺, S⁻ (m), E_obs (kWh), dt_total (s), filas.

    - L se integra con velocidad × Δt (km).
    - S⁺/S⁻ se integran con Δ(Elevation Smoothed) entre filas consecutivas.
    - E_obs se integra con Energy_Consumption × Δt (kWh).
    """
    acc: dict[tuple[str, str], dict] = {}
    previo: dict[tuple[str, str], dict] = {}
    with open(ruta_ev, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        for i, r in enumerate(lector):
            if max_filas is not None and i >= max_filas:
                break
            k = (r["VehId"], r["Trip"])
            try:
                t = datetime.strptime(r["Timestamp"], "%Y-%m-%d %H:%M:%S.%f")
            except (KeyError, ValueError):
                continue
            def _f(col):
                v = r.get(col)
                if v is None or v == "" or v == "nan":
                    return None
                try:
                    return float(v)
                except ValueError:
                    return None
            v = _f("Vehicle Speed[km/h]") or 0.0
            e = _f("Energy_Consumption") or 0.0
            h = _f("Elevation Smoothed[m]")
            if h is None:
                h = _f("Elevation Raw[m]")
            d = acc.setdefault(k, {"L": 0.0, "Sp": 0.0, "Sm": 0.0, "E": 0.0, "dt": 0.0, "filas": 0})
            d["filas"] += 1
            if k in previo:
                p = previo[k]
                dt = (t - p["t"]).total_seconds()
                if 0 < dt < 60:  # descarta huecos largos (parones GPS)
                    d["L"] += v * dt / 3600.0
                    d["E"] += e * dt
                    d["dt"] += dt
                    if h is not None and p["h"] is not None:
                        dh = h - p["h"]
                        if dh > 0:
                            d["Sp"] += dh
                        else:
                            d["Sm"] += -dh
            previo[k] = {"t": t, "h": h}
    viajes = [{"veh": k[0], "trip": k[1], **v} for k, v in acc.items()
              if v["L"] > km_min and v["E"] > 0]
    return viajes


def _kappa(masa_kg: float) -> float:
    return masa_kg * G_GRAV / 3.6e6


def ajustar_nnls(viajes: list[dict], masa_kg: float = 1590.0) -> dict:
    """NNLS de E_obs ≈ a·L + b·S⁺ − d·S⁻. Recupera c, η_d, η_r."""
    from scipy.optimize import nnls

    kappa = _kappa(masa_kg)
    L = np.array([v["L"] for v in viajes])
    Sp = np.array([v["Sp"] for v in viajes])
    Sm = np.array([v["Sm"] for v in viajes])
    y = np.array([v["E"] for v in viajes])
    # Columna de bajada con signo negativo para que el coeficiente d sea ≥ 0.
    A = np.column_stack([L, Sp, -Sm])
    coef, _ = nnls(A, y)
    a, b, d = coef
    c = a
    eta_d = (kappa / b) if b > 1e-12 else float("inf")
    eta_r = (d / kappa) if kappa > 0 else 0.0
    # η están físicamente en (0,1]; recortamos para reportar pero guardamos crudos.
    return {
        "c_kwh_km": float(c),
        "eta_traccion": float(min(max(eta_d, 1e-3), 1.0)) if math.isfinite(eta_d) else 1.0,
        "eta_regeneracion": float(min(max(eta_r, 0.0), 1.0)),
        "eta_traccion_crudo": float(eta_d) if math.isfinite(eta_d) else None,
        "eta_regeneracion_crudo": float(eta_r),
        "masa_kg": masa_kg,
        "kappa": kappa,
        "coef_nnls": [float(a), float(b), float(d)],
        "n_viajes": len(viajes),
    }


def _pred_plano(viajes, c):
    return np.array([c * v["L"] for v in viajes])


def _pred_pendiente(viajes, c, eta_d, eta_r, masa_kg):
    kappa = _kappa(masa_kg)
    out = []
    for v in viajes:
        out.append(c * v["L"] + kappa * (v["Sp"] / eta_d - eta_r * v["Sm"]))
    return np.array(out)


def _metricas(y, pred):
    err = pred - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mape = float(np.mean(np.abs(err) / np.maximum(y, 1e-6)) * 100)
    return {"MAE_kwh": round(mae, 4), "RMSE_kwh": round(rmse, 4), "MAPE_pct": round(mape, 2)}


def validar_separando_viajes(viajes: list[dict], masa_kg: float = 1590.0,
                             frac_train: float = 0.7, semilla: int = 7) -> dict:
    """Train/test por VIAJE (no por fila). Compara plano vs pendiente en test."""
    rng = np.random.default_rng(semilla)
    idx = np.arange(len(viajes))
    rng.shuffle(idx)
    corte = int(len(viajes) * frac_train)
    tr = [viajes[i] for i in idx[:corte]]
    te = [viajes[i] for i in idx[corte:]]

    # Modelo plano: c por mínimos cuadrados solo con L (sin pendiente).
    Ltr = np.array([v["L"] for v in tr]); ytr = np.array([v["E"] for v in tr])
    c_plano = float(np.dot(Ltr, ytr) / np.dot(Ltr, Ltr))

    # Modelo pendiente: NNLS sobre train.
    fit = ajustar_nnls(tr, masa_kg)
    c_p, eta_d, eta_r = fit["c_kwh_km"], fit["eta_traccion"], fit["eta_regeneracion"]

    yte = np.array([v["E"] for v in te])
    m_plano = _metricas(yte, _pred_plano(te, c_plano))
    m_pend = _metricas(yte, _pred_pendiente(te, c_p, eta_d, eta_r, masa_kg))
    return {
        "n_train": len(tr), "n_test": len(te),
        "c_plano": round(c_plano, 4),
        "ajuste_pendiente": {k: fit[k] for k in ("c_kwh_km", "eta_traccion", "eta_regeneracion")},
        "test_plano": m_plano,
        "test_pendiente": m_pend,
        "mejora_MAE_pct": round(100 * (m_plano["MAE_kwh"] - m_pend["MAE_kwh"]) / m_plano["MAE_kwh"], 2)
        if m_plano["MAE_kwh"] > 0 else 0.0,
    }


def validar_kfold(viajes: list[dict], masa_kg: float = 1590.0, k: int = 5, semilla: int = 7) -> dict:
    """K-fold por viaje; promedia MAE/RMSE/MAPE de plano y pendiente en los folds de test."""
    rng = np.random.default_rng(semilla)
    idx = np.arange(len(viajes))
    rng.shuffle(idx)
    folds = np.array_split(idx, k)
    acum = {"plano": defaultdict(list), "pendiente": defaultdict(list), "mejora": []}
    for f in range(k):
        te_i = folds[f]
        tr_i = np.concatenate([folds[j] for j in range(k) if j != f])
        tr = [viajes[i] for i in tr_i]; te = [viajes[i] for i in te_i]
        Ltr = np.array([v["L"] for v in tr]); ytr = np.array([v["E"] for v in tr])
        c_plano = float(np.dot(Ltr, ytr) / np.dot(Ltr, Ltr))
        fit = ajustar_nnls(tr, masa_kg)
        yte = np.array([v["E"] for v in te])
        mp = _metricas(yte, _pred_plano(te, c_plano))
        ms = _metricas(yte, _pred_pendiente(te, fit["c_kwh_km"], fit["eta_traccion"],
                                            fit["eta_regeneracion"], masa_kg))
        for kk, vv in mp.items():
            acum["plano"][kk].append(vv)
        for kk, vv in ms.items():
            acum["pendiente"][kk].append(vv)
        if mp["MAE_kwh"] > 0:
            acum["mejora"].append(100 * (mp["MAE_kwh"] - ms["MAE_kwh"]) / mp["MAE_kwh"])
    prom = lambda d: {kk: round(float(np.mean(vv)), 4) for kk, vv in d.items()}
    return {
        "k": k,
        "plano": prom(acum["plano"]),
        "pendiente": prom(acum["pendiente"]),
        "mejora_MAE_pct_media": round(float(np.mean(acum["mejora"])), 2) if acum["mejora"] else 0.0,
    }


def main():
    import sys

    raiz = Path(__file__).resolve().parents[3]
    csv_ev = raiz / "data" / "eVED_EV.csv"
    masa = float(sys.argv[1]) if len(sys.argv) > 1 else 1590.0
    max_filas = int(sys.argv[2]) if len(sys.argv) > 2 else None

    viajes = extraer_viajes(csv_ev, km_min=2.0, max_filas=max_filas)
    fit = ajustar_nnls(viajes, masa)
    split = validar_separando_viajes(viajes, masa)
    kf = validar_kfold(viajes, masa, k=5)

    # Rango de Δh por viaje, para contexto.
    Sp = np.array([v["Sp"] for v in viajes]); Sm = np.array([v["Sm"] for v in viajes])
    res = {
        "n_viajes": len(viajes),
        "masa_kg": masa,
        "ajuste_global": fit,
        "subida_m_mediana": round(float(np.median(Sp)), 1),
        "bajada_m_mediana": round(float(np.median(Sm)), 1),
        "split_70_30": split,
        "kfold_5": kf,
    }
    salida = Path(__file__).resolve().parent / "calibracion.json"
    salida.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
