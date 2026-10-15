"""Carga y fusión de configuración (YAML opcional sobre valores por defecto)."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "flota": [{"tipo": "leaf2013", "cantidad": 2}],
    "tipos_vehiculo": {
        "leaf2013": {
            "bateria_kwh": 16.0,
            "soc_inicial": 0.60,
            "reserva_frac": 0.10,
            "conectores": ["CHADEMO", "J1772"],
            "consumo_kwh_km": 0.156,
            "masa_kg": 1590.0,
            "eta_traccion": 0.90,
            "eta_regeneracion": 0.60,
        }
    },
    "pipeline": {
        "red": "osm",
        "energia": "plano",
        "cargadores": "dominancia",
        "inicial": "insercion",
        "solver": "milp",
    },
    "red": {
        "factor_vial": 1.30,
        "osm_margen_km": 2.0,
        "osm_cache": ".cache/osm",
        "osm_grafo": None,                # None = mapa empaquetado (evrp/assets/osm)
        "osm_permitir_descarga": True,    # si el mapa local no cubre los nodos
        "max_acceso_m": None,             # distancia máxima punto→calle; None = sin límite
        "respaldo_linea_recta": False,    # si OSM falla: usar línea recta × factor_vial
    },
    "cargadores": {"top_r": 3},
    "solver": {"tiempo_limite_s": 60.0, "formulacion": "compacta", "usar_todos_vehiculos": False,
               "cargadores_por_arco": 3, "conectividad": "cortes", "gap_relativo": 0.0, "hilos": 0,
               "mostrar_log": False},
    "asesor": {
        "tipo": "ninguno",
        "region": "us-east-1",
        "perfil_aws": None,
        "modelo": "us.anthropic.claude-sonnet-4-6",
        "sugerir_config": False,
        "explicar": True,
    },
}

PERFILES_DIR = Path(__file__).parent / "perfiles"

# Valores permitidos para las opciones de pipeline (se validan al cargar).
OPCIONES = {
    "red": {"haversine", "osm"},
    "energia": {"plano", "pendiente"},
    "cargadores": {"todos", "dominancia", "top_r"},
    "inicial": {"insercion", "ninguna"},
    "solver": {"milp", "heuristica"},
}


def fusionar(base: dict, extra: dict) -> dict:
    """Fusión recursiva: los dicts se mezclan, el resto se reemplaza."""
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = fusionar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def validar(cfg: dict) -> dict:
    for clave, permitidas in OPCIONES.items():
        valor = cfg["pipeline"].get(clave)
        if valor not in permitidas:
            raise ValueError(f"pipeline.{clave}={valor!r} no válido; opciones: {sorted(permitidas)}")
    if not cfg["flota"]:
        raise ValueError("La flota está vacía")
    for g in cfg["flota"]:
        if g["tipo"] not in cfg["tipos_vehiculo"]:
            raise ValueError(f"Tipo de vehículo desconocido en flota: {g['tipo']!r}")
        if int(g.get("cantidad", 1)) < 1:
            raise ValueError("cantidad de vehículos debe ser >= 1")
    for nombre, t in cfg["tipos_vehiculo"].items():
        if t["bateria_kwh"] <= 0:
            raise ValueError(f"{nombre}: bateria_kwh debe ser > 0")
        reserva = reserva_kwh(t)
        if not 0 <= reserva <= t["soc_inicial"] * t["bateria_kwh"] or not 0 <= t["soc_inicial"] <= 1:
            raise ValueError(f"{nombre}: se requiere 0 <= reserva <= soc_inicial·B y 0 <= soc_inicial <= 1")
    return cfg


def reserva_kwh(t: dict) -> float:
    """Reserva absoluta: `reserva_kwh` si está definida; si no, `reserva_frac` · B."""
    if t.get("reserva_kwh") is not None:
        return float(t["reserva_kwh"])
    return float(t["reserva_frac"]) * float(t["bateria_kwh"])


def perfiles_disponibles() -> list[str]:
    return sorted(p.stem for p in PERFILES_DIR.glob("*.yaml"))


def _leer_yaml(ruta: Path) -> dict:
    import yaml

    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cargar(ruta: str | Path | None = None, sobrescribir: dict | None = None,
           perfiles: list[str] | None = None) -> dict:
    """DEFAULTS ← perfiles (en orden) ← archivo YAML ← sobrescribir."""
    cfg = copy.deepcopy(DEFAULTS)
    for p in perfiles or []:
        archivo = PERFILES_DIR / f"{p}.yaml"
        if not archivo.exists():
            raise ValueError(f"Perfil desconocido {p!r}; disponibles: {perfiles_disponibles()}")
        cfg = fusionar(cfg, _leer_yaml(archivo))
    if ruta:
        cfg = fusionar(cfg, _leer_yaml(Path(ruta)))
    if sobrescribir:
        cfg = fusionar(cfg, sobrescribir)
    return validar(cfg)
