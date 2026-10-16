"""Modelo de energía por tramo y calibración con eVED."""
from __future__ import annotations

import csv
import json
import statistics as st
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

G = 9.81

# --- F2: tiempo por arco (OPCIONAL, apagado por defecto) --------------------
# Velocidad efectiva por tipo de vía OSM (km/h), usada cuando falta `maxspeed`.
# Calibrada groseramente con eVED: la velocidad media de marcha (incluidas
# detenciones) ronda 0.80× el límite señalizado en vías urbanas (40–72 km/h) y
# sube hacia el límite en autopista. Ver docs/experimentos/dijkstra_extensiones.md.
V_EF_POR_VIA = {
    "motorway": 95.0, "motorway_link": 55.0,
    "trunk": 75.0, "trunk_link": 45.0,
    "primary": 55.0, "primary_link": 40.0,
    "secondary": 45.0, "secondary_link": 35.0,
    "tertiary": 40.0, "tertiary_link": 30.0,
    "unclassified": 35.0, "residential": 30.0,
    "living_street": 15.0, "service": 20.0,
}
V_EF_DEFECTO = 32.0            # vía desconocida
FACTOR_MAXSPEED = 0.80        # fracción del límite señalizado para v efectiva (eVED)


def _mph_a_kmh(txt: str) -> float | None:
    t = txt.strip().lower()
    try:
        if t.endswith("mph"):
            return float(t[:-3].strip()) * 1.609344
        return float(t.split()[0])        # ya en km/h
    except (ValueError, IndexError):
        return None


def velocidad_efectiva_kmh(highway, maxspeed=None) -> float:
    """v_ef (km/h) de un arco a partir de `maxspeed` y/o tipo de vía OSM.

    Prioriza `maxspeed` (×FACTOR_MAXSPEED); si falta o es inválido, usa la tabla
    por tipo de vía. Acepta listas de OSM (toma el primer valor válido / tipo).
    """
    if isinstance(maxspeed, (list, tuple)):
        maxspeed = maxspeed[0] if maxspeed else None
    if maxspeed is not None:
        lim = _mph_a_kmh(str(maxspeed))
        if lim and lim > 0:
            return lim * FACTOR_MAXSPEED
    if isinstance(highway, (list, tuple)):
        highway = highway[0] if highway else None
    return V_EF_POR_VIA.get(str(highway), V_EF_DEFECTO)


def tiempo_arco_min(km: float, highway=None, maxspeed=None) -> float:
    """Tiempo del arco en minutos: t = ℓ / v_ef · 60."""
    v = velocidad_efectiva_kmh(highway, maxspeed)
    return 60.0 * km / v if v > 0 else 0.0


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
