"""Lectura del archivo de nodos y compatibilidad de conectores."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

# Sinónimos aceptados para node_type (el formato oficial usa base / visit / charger).
TIPOS_NODO = {
    "base": "base", "depot": "base", "deposito": "base",
    "visit": "cliente", "client": "cliente", "cliente": "cliente", "customer": "cliente",
    "charger": "cargador", "cargador": "cargador", "station": "cargador",
}

ALIAS_CONECTOR = {"TESLA": "NACS", "CCS1": "CCS", "CCS2": "CCS", "J1772COMBO": "CCS", "TYPE1": "J1772"}


def normalizar_conector(texto: str) -> str:
    t = texto.strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    return ALIAS_CONECTOR.get(t, t)


def _float(v: str | None) -> float | None:
    if v is None or str(v).strip() in ("", "nan", "NaN"):
        return None
    return float(v)


@dataclass(frozen=True)
class Nodo:
    id: str
    tipo: str            # base | cliente | cargador
    lat: float
    lon: float
    fila: int            # índice 0-based de la fila de datos en el CSV
    conectores: frozenset = field(default_factory=frozenset)
    puertos: int | None = None
    potencia_kw: float | None = None
    direccion: str = ""
    operador: str = ""


def cargar_nodos(ruta: str | Path) -> list[Nodo]:
    nodos: list[Nodo] = []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        faltan = {"node_id", "node_type", "latitude", "longitude"} - set(lector.fieldnames or [])
        if faltan:
            raise ValueError(f"Faltan columnas obligatorias en {ruta}: {sorted(faltan)}")
        vistos: set[str] = set()
        for fila, r in enumerate(lector):
            nid = r["node_id"].strip()
            if not nid:
                continue
            if nid in vistos:
                raise ValueError(f"node_id duplicado: {nid}")
            vistos.add(nid)
            tipo = TIPOS_NODO.get(r["node_type"].strip().lower())
            if tipo is None:
                raise ValueError(f"node_type desconocido en {nid}: {r['node_type']!r}")
            lat, lon = _float(r["latitude"]), _float(r["longitude"])
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"Coordenadas inválidas en {nid}")
            conns = frozenset(
                normalizar_conector(c) for c in (r.get("connector_types") or "").split(";") if c.strip()
            )
            puertos = _float(r.get("total_ports"))
            nodos.append(Nodo(
                id=nid, tipo=tipo, lat=lat, lon=lon, fila=fila, conectores=conns,
                puertos=None if puertos is None else int(puertos),
                potencia_kw=_float(r.get("max_power_kw")),
                direccion=(r.get("address") or "").strip(), operador=(r.get("network") or "").strip(),
            ))
    bases = [n for n in nodos if n.tipo == "base"]
    if len(bases) != 1:
        raise ValueError(f"Se espera exactamente 1 base; hay {len(bases)}")
    return nodos


def compatible(cargador: Nodo, conectores_vehiculo: set[str]) -> bool:
    """Un cargador sirve si comparte algún conector y no declara 0 puertos."""
    if cargador.tipo != "cargador":
        return False
    if cargador.puertos is not None and cargador.puertos <= 0:
        return False
    return bool(cargador.conectores & {normalizar_conector(c) for c in conectores_vehiculo})


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))
