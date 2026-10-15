"""Resolucion de supuestos fisicos comunes a partir del escenario.

Un perfil ('eved' o 'ev_routing') fija los valores base; el bloque 'supuestos' del
escenario los puede sobrescribir campo a campo. El resultado se usa identico para
los dos motores y para el validador neutral.
"""
from __future__ import annotations

from dataclasses import dataclass

PERFILES = {
    "eved": {"bateria_kwh": 16.0, "soc_inicial": 0.60, "reserva_kwh": 1.6,
             "consumo_kwh_km": 0.156},
    "ev_routing": {"bateria_kwh": 24.0, "soc_inicial": 0.60, "reserva_kwh": 2.4,
                   "consumo_kwh_km": 0.1567712473},
}

CONECTORES_LEAF = ["CHADEMO", "J1772"]


@dataclass(frozen=True)
class SupuestosComunes:
    bateria_kwh: float
    reserva_kwh: float
    soc_inicial: float
    consumo_kwh_km: float
    conectores: tuple[str, ...]
    red: str
    pendiente: bool
    max_acceso_m: float | None
    perfil: str | None


def resolver(escenario: dict) -> SupuestosComunes:
    s = escenario.get("supuestos", {})
    perfil = s.get("perfil")
    base = dict(PERFILES.get(perfil, PERFILES["ev_routing"]))
    bateria = float(s.get("bateria_kwh", base["bateria_kwh"]))
    reserva = float(s.get("reserva_kwh", base["reserva_kwh"]))
    soc = float(s.get("soc_inicial", base["soc_inicial"]))
    consumo = float(s.get("consumo_kwh_km", base["consumo_kwh_km"]))
    conectores = tuple(s.get("conectores", CONECTORES_LEAF))
    return SupuestosComunes(
        bateria_kwh=bateria, reserva_kwh=reserva, soc_inicial=soc,
        consumo_kwh_km=consumo, conectores=conectores,
        red=s.get("red", "osm"), pendiente=bool(s.get("pendiente", False)),
        max_acceso_m=s.get("max_acceso_m"), perfil=perfil)
