"""Modelo de energía por tramo y calibración con eVED."""
from __future__ import annotations

import csv
import json
import statistics as st
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

G = 9.81


@dataclass(frozen=True)
class ModeloEnergia:
    """e = c·ℓ + κ·([Δh]⁺/η_d − η_r·[Δh]⁻),  κ = m·g/3.6e6 (kWh por metro de desnivel)."""
    consumo_kwh_km: float
    masa_kg: float = 1590.0
    eta_traccion: float = 0.90
    eta_regeneracion: float = 0.60
    usar_pendiente: bool = False

    def __post_init__(self):
        if self.consumo_kwh_km <= 0:
            raise ValueError("consumo_kwh_km debe ser > 0")
        if not (0 <= self.eta_regeneracion <= 1 and 0 < self.eta_traccion <= 1):
            raise ValueError("Eficiencias fuera de rango: 0<=eta_r<=1, 0<eta_d<=1")

    @property
    def kappa(self) -> float:
        return self.masa_kg * G / 3.6e6

    def tramo(self, km: float, dh_m: float = 0.0) -> float:
        e = self.consumo_kwh_km * km
        if self.usar_pendiente and dh_m:
            e += self.kappa * (dh_m / self.eta_traccion if dh_m > 0 else self.eta_regeneracion * dh_m)
        return e


def calibrar_eved(ruta_ev: str | Path, km_min: float = 2.0, dsoc_min: float = 10.0) -> dict:
    """Consumo (kWh/km) y capacidad útil (kWh) desde eVED_EV.csv.

    La energía se integra con el Δt real entre filas (README §9.1: la suma directa
    de Energy_Consumption sobrestima ~2×). La distancia se integra con la velocidad.
    """
    viajes: dict[tuple[str, str], dict] = {}
    previo: dict[tuple[str, str], datetime] = {}
    with open(ruta_ev, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            k = (r["VehId"], r["Trip"])
            t = datetime.strptime(r["Timestamp"], "%Y-%m-%d %H:%M:%S.%f")
            v = float(r["Vehicle Speed[km/h]"]) if r["Vehicle Speed[km/h]"] != "nan" else 0.0
            e = float(r["Energy_Consumption"]) if r["Energy_Consumption"] != "nan" else 0.0
            soc = float(r["HV Battery SOC[%]"]) if r["HV Battery SOC[%]"] != "nan" else None
            d = viajes.setdefault(k, {"km": 0.0, "kwh": 0.0, "soc0": soc, "soc1": soc})
            if k in previo:
                dt = (t - previo[k]).total_seconds()
                d["km"] += v * dt / 3600.0
                d["kwh"] += e * dt
            previo[k] = t
            if soc is not None:
                d["soc1"] = soc
                if d["soc0"] is None:
                    d["soc0"] = soc
    buenos = [d for d in viajes.values() if d["km"] > km_min]
    if not buenos:
        raise ValueError("No hay viajes suficientes para calibrar")
    consumo = sum(d["kwh"] for d in buenos) / sum(d["km"] for d in buenos)
    por_viaje = [d["kwh"] / d["km"] for d in buenos]
    caps = [d["kwh"] / ((d["soc0"] - d["soc1"]) / 100) for d in buenos
            if d["soc0"] is not None and d["soc1"] is not None and d["soc0"] - d["soc1"] >= dsoc_min]
    q = st.quantiles(por_viaje, n=4)
    return {
        "viajes": len(buenos),
        "consumo_kwh_km": round(consumo, 4),
        "consumo_p25_p75": [round(q[0], 4), round(q[2], 4)],
        "bateria_util_kwh": round(st.median(caps), 2) if caps else None,
        "viajes_capacidad": len(caps),
    }


def guardar_calibracion(res: dict, ruta: str | Path) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
