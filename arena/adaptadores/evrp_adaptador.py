"""Adaptador del motor evrp (in-process, via evrp.MotorEvrp).

Entrada: csv_nodos ya materializado, supuestos comunes, flota, presupuesto, hilos.
Salida (dict comun):
  {motor, estado, rutas{veh:[node_id]}, tiempo_s, tiempo_solver_s, gap, energia_kwh,
   entregas, detalles{...}}
Las rutas se devuelven en nodos clave; la arena las revalida con el validador neutral.
"""
from __future__ import annotations

import time

from arena.supuestos import SupuestosComunes


def resolver(csv_nodos: str, sup: SupuestosComunes, vehiculos: int, presupuesto_s: float,
             hilos: int, opciones: dict | None = None,
             osm_cache: str = "results/arena/.cache/osm") -> dict:
    import evrp
    opciones = opciones or {}
    grafo = None
    if sup.red == "osm":
        from arena.instancias import grafo_osm_descomprimido
        grafo = str(grafo_osm_descomprimido())

    tipo = {"bateria_kwh": sup.bateria_kwh, "soc_inicial": sup.soc_inicial,
            "reserva_kwh": sup.reserva_kwh, "consumo_kwh_km": sup.consumo_kwh_km,
            "conectores": list(sup.conectores)}
    extra: dict = {
        "flota": [{"tipo": "leaf2013", "cantidad": int(vehiculos)}],
        "tipos_vehiculo": {"leaf2013": tipo},
        "pipeline": {"red": sup.red,
                     "energia": "pendiente" if sup.pendiente else "plano",
                     "solver": "milp"},
        "solver": {"tiempo_limite_s": float(presupuesto_s), "hilos": int(hilos),
                   "formulacion": opciones.get("formulacion", "compacta")},
        "red": {"osm_cache": osm_cache, "osm_grafo": grafo,
                "osm_permitir_descarga": False, "max_acceso_m": sup.max_acceso_m},
    }
    t0 = time.perf_counter()
    try:
        r = evrp.resolver(csv_nodos, extra, perfiles=None, salida=None)
    except Exception as exc:  # la arena registra, no aborta
        return {"motor": "evrp", "estado": "error", "error": str(exc)[:500],
                "tiempo_s": round(time.perf_counter() - t0, 3)}
    k = r.kpis
    traza = k.get("solver") or {}
    gap, t_solver = _extraer_solver(traza)
    return {
        "motor": "evrp",
        "estado": "ok" if k["factible"] else "infactible",
        "rutas": r.rutas,
        "tipo_rutas": "clave",
        "energia_kwh": k.get("energia_total_kwh"),
        "entregas": k.get("entregas"),
        "tiempo_s": round(time.perf_counter() - t0, 3),
        "tiempo_solver_s": t_solver,
        "gap": gap,
        "detalles": {"km_motor": k.get("km_total"), "red": k.get("red"),
                     "solver": "highs", "N*": _n_estrella(traza)},
    }


def _extraer_solver(traza: dict):
    """Devuelve (gap, tiempo_solver_s) de la traza del MILP compacto/completo."""
    if not isinstance(traza, dict):
        return None, None
    # traza puede ser {compacta:{...}, completa:{...}} o directa.
    candidatos = []
    if "fase2" in traza or "tiempo_s" in traza:
        candidatos.append(traza)
    for v in traza.values():
        if isinstance(v, dict) and ("fase2" in v or "tiempo_s" in v):
            candidatos.append(v)
    gap = None
    t_solver = None
    for c in candidatos:
        f2 = c.get("fase2") if isinstance(c.get("fase2"), dict) else None
        if f2 and f2.get("gap") is not None:
            gap = f2["gap"] if gap is None else min(gap, f2["gap"])
        if c.get("tiempo_s") is not None:
            t_solver = (c["tiempo_s"] if t_solver is None else t_solver + c["tiempo_s"])
    return gap, t_solver


def _n_estrella(traza: dict):
    if not isinstance(traza, dict):
        return None
    if "N*" in traza:
        return traza["N*"]
    for v in traza.values():
        if isinstance(v, dict) and "N*" in v:
            return v["N*"]
    return None
