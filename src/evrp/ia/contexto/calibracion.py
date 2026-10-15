"""Calibración de consumo por banda de temperatura (y velocidad) desde eVED.

Reutiliza la integración por Δt real de `evrp.energia` (README §9.1: sumar
`Energy_Consumption` directo sobrestima ~2×). La distancia se integra con la
velocidad. Se agrega por viaje (VehId, Trip) y luego por banda; así la validación
puede separarse por viajes/fechas, no por filas.

Bandas de temperatura por defecto (°C): <0, 0–10, 10–20, 20–30, >30. La calefacción
y el aire acondicionado disparan el consumo en los extremos, por eso el factor de
`ajustar` se ancla a estas bandas.
"""
from __future__ import annotations

import csv
import json
import statistics as st
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Límites de banda de temperatura (°C). N bandas = len(limites)+1.
LIMITES_TEMP = (0.0, 10.0, 20.0, 30.0)
# Banda de referencia (clima templado) para el factor relativo.
BANDA_REFERENCIA = "20-30"
LIMITES_VEL = (20.0, 40.0, 60.0)  # km/h


@dataclass
class BandaConsumo:
    nombre: str
    viajes: int
    km: float
    consumo_kwh_km: float | None
    p25: float | None = None
    p75: float | None = None

    def a_dict(self) -> dict:
        return {
            "banda": self.nombre, "viajes": self.viajes, "km": round(self.km, 2),
            "consumo_kwh_km": self.consumo_kwh_km, "p25": self.p25, "p75": self.p75,
        }


@dataclass
class CalibracionTemperatura:
    consumo_global_kwh_km: float
    banda_referencia: str
    bandas: dict[str, BandaConsumo]
    # factor[banda] = consumo_banda / consumo_referencia (acotado al calcular).
    factores: dict[str, float] = field(default_factory=dict)
    bandas_velocidad: dict[str, dict] = field(default_factory=dict)
    viajes_totales: int = 0

    def factor(self, banda: str) -> float:
        return self.factores.get(banda, 1.0)

    def a_dict(self) -> dict:
        return {
            "consumo_global_kwh_km": self.consumo_global_kwh_km,
            "banda_referencia": self.banda_referencia,
            "viajes_totales": self.viajes_totales,
            "bandas": {k: v.a_dict() for k, v in self.bandas.items()},
            "factores": self.factores,
            "bandas_velocidad": self.bandas_velocidad,
        }


def _banda_temp(oat: float, limites=LIMITES_TEMP) -> str:
    if oat < limites[0]:
        return f"<{limites[0]:.0f}"
    for a, b in zip(limites, limites[1:]):
        if a <= oat < b:
            return f"{a:.0f}-{b:.0f}"
    return f">{limites[-1]:.0f}"


def _banda_vel(v: float, limites=LIMITES_VEL) -> str:
    if v < limites[0]:
        return f"<{limites[0]:.0f}"
    for a, b in zip(limites, limites[1:]):
        if a <= v < b:
            return f"{a:.0f}-{b:.0f}"
    return f">{limites[-1]:.0f}"


def _agregar_viajes(ruta_ev: str | Path, km_min: float) -> list[dict]:
    """Integra energía/distancia por (VehId, Trip) con Δt real. Añade OAT y vel. medias."""
    viajes: dict[tuple[str, str], dict] = {}
    previo: dict[tuple[str, str], datetime] = {}
    with open(ruta_ev, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            k = (r["VehId"], r["Trip"])
            t = datetime.strptime(r["Timestamp"], "%Y-%m-%d %H:%M:%S.%f")
            v = float(r["Vehicle Speed[km/h]"]) if r["Vehicle Speed[km/h]"] not in ("", "nan") else 0.0
            e = float(r["Energy_Consumption"]) if r["Energy_Consumption"] not in ("", "nan") else 0.0
            oat = r.get("OAT[DegC]", "")
            oat = float(oat) if oat not in ("", "nan") else None
            d = viajes.setdefault(k, {"km": 0.0, "kwh": 0.0, "oat_sum": 0.0, "oat_n": 0,
                                      "vel_sum": 0.0, "vel_n": 0, "fecha": t.date().isoformat()})
            if k in previo:
                dt = (t - previo[k]).total_seconds()
                if 0 < dt < 60:  # ignora saltos largos (viajes mal cortados)
                    d["km"] += v * dt / 3600.0
                    d["kwh"] += e * dt
            previo[k] = t
            if oat is not None:
                d["oat_sum"] += oat
                d["oat_n"] += 1
            if v > 0:
                d["vel_sum"] += v
                d["vel_n"] += 1
    salida = []
    for (veh, trip), d in viajes.items():
        if d["km"] <= km_min or d["oat_n"] == 0:
            continue
        salida.append({
            "veh": veh, "trip": trip, "fecha": d["fecha"],
            "km": d["km"], "kwh": d["kwh"],
            "consumo": d["kwh"] / d["km"],
            "oat": d["oat_sum"] / d["oat_n"],
            "vel": d["vel_sum"] / d["vel_n"] if d["vel_n"] else 0.0,
        })
    return salida


def calibrar_por_temperatura(
    ruta_ev: str | Path,
    *,
    km_min: float = 2.0,
    factor_min: float = 0.7,
    factor_max: float = 1.8,
    viajes_min_banda: int = 5,
) -> CalibracionTemperatura:
    """Calibra consumo (kWh/km) por banda de temperatura y velocidad.

    `factor_min`/`factor_max` acotan los factores relativos a la banda de
    referencia (lista blanca de rangos; evita extrapolaciones absurdas).
    """
    viajes = _agregar_viajes(ruta_ev, km_min)
    if not viajes:
        raise ValueError("No hay viajes suficientes para calibrar")

    consumo_global = sum(v["kwh"] for v in viajes) / sum(v["km"] for v in viajes)

    # Agregación por banda de temperatura.
    por_banda: dict[str, list[dict]] = {}
    for v in viajes:
        por_banda.setdefault(_banda_temp(v["oat"]), []).append(v)

    bandas: dict[str, BandaConsumo] = {}
    for nombre, vs in por_banda.items():
        km = sum(x["km"] for x in vs)
        consumo = sum(x["kwh"] for x in vs) / km if km else None
        por_viaje = sorted(x["consumo"] for x in vs)
        p25 = p75 = None
        if len(por_viaje) >= 4:
            q = st.quantiles(por_viaje, n=4)
            p25, p75 = round(q[0], 4), round(q[2], 4)
        bandas[nombre] = BandaConsumo(nombre, len(vs), km,
                                      round(consumo, 4) if consumo else None, p25, p75)

    # Factor relativo a la banda de referencia (si tiene datos; si no, al global).
    ref = bandas.get(BANDA_REFERENCIA)
    base = ref.consumo_kwh_km if (ref and ref.consumo_kwh_km) else consumo_global
    factores: dict[str, float] = {}
    for nombre, b in bandas.items():
        if b.consumo_kwh_km and b.viajes >= viajes_min_banda:
            f = b.consumo_kwh_km / base
            factores[nombre] = round(min(factor_max, max(factor_min, f)), 3)

    # Agregación por banda de velocidad (informativa).
    por_vel: dict[str, list[dict]] = {}
    for v in viajes:
        por_vel.setdefault(_banda_vel(v["vel"]), []).append(v)
    bandas_vel = {}
    for nombre, vs in por_vel.items():
        km = sum(x["km"] for x in vs)
        bandas_vel[nombre] = {
            "viajes": len(vs), "km": round(km, 2),
            "consumo_kwh_km": round(sum(x["kwh"] for x in vs) / km, 4) if km else None,
        }

    return CalibracionTemperatura(
        consumo_global_kwh_km=round(consumo_global, 4),
        banda_referencia=BANDA_REFERENCIA,
        bandas=bandas,
        factores=factores,
        bandas_velocidad=bandas_vel,
        viajes_totales=len(viajes),
    )


def guardar_calibracion(cal: CalibracionTemperatura, ruta: str | Path) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(cal.a_dict(), indent=2, ensure_ascii=False),
                          encoding="utf-8")


def cargar_calibracion(ruta: str | Path) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


# ---- utilidades para la evaluación (validación por viajes/fechas) ----

def viajes_para_evaluacion(ruta_ev: str | Path, km_min: float = 2.0) -> list[dict]:
    """Expone los viajes agregados (con oat, vel, consumo real) para evaluar modelos."""
    return _agregar_viajes(ruta_ev, km_min)
