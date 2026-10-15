"""Harness: construye instancias infactibles-para-todos, corre el motor (compacta y
completa) y, en instancias pequeñas, el oráculo independiente. Reporta N* y energía.

Usa RedHaversine (sin internet) con coordenadas controladas para fijar distancias y, con
ellas, el alcance de la batería. Independiente del mapa OSM empaquetado.

Ejecutar:
    uv run python experimentos/max_clientes/harness.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from evrp import config as cfgmod
from evrp import heuristica
from evrp.datos import cargar_nodos, Nodo
from evrp.instancia import construir, tipos_desde_config
from evrp.red import RedHaversine

CABECERA = ("node_id,node_type,latitude,longitude,address,network,total_ports,"
            "dc_fast_ports,level2_ports,connector_types,max_power_kw")


def _nodo(nid, tipo, lat, lon, conector="", puertos="", pot=""):
    dc = "1" if conector in ("CHAdeMO", "CCS", "NACS") else ("0" if conector else "")
    l2 = "1" if conector == "J1772" else ("0" if conector else "")
    return {"node_id": nid, "node_type": tipo, "latitude": f"{lat:.6f}", "longitude": f"{lon:.6f}",
            "address": "", "network": "", "total_ports": puertos, "dc_fast_ports": dc,
            "level2_ports": l2, "connector_types": conector, "max_power_kw": pot}


def _escribir_csv(filas, ruta):
    import csv
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECERA.split(","))
        w.writeheader()
        w.writerows(filas)
    return ruta


# ----------------------------------------------------------- construcción de inst
def construir_inst(filas, bateria_kwh, reserva_kwh, n_veh, formulacion="compacta",
                   tiempo=20.0, factor_vial=1.3):
    """Devuelve (inst, cfg, nodos) con RedHaversine y batería/flota dadas."""
    import tempfile
    import os
    fd, ruta = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    _escribir_csv(filas, ruta)
    extra = {
        "pipeline": {"red": "haversine"},
        "red": {"factor_vial": factor_vial, "respaldo_linea_recta": True},
        "tipos_vehiculo": {"leaf2013": {"bateria_kwh": float(bateria_kwh),
                                        "reserva_kwh": float(reserva_kwh)}},
        "flota": [{"tipo": "leaf2013", "cantidad": int(n_veh)}],
        "solver": {"tiempo_limite_s": float(tiempo), "presupuesto_total_s": None,
                   "formulacion": formulacion, "hilos": 1},
    }
    cfg = cfgmod.cargar(None, extra)
    nodos = cargar_nodos(ruta)
    red = RedHaversine(factor_vial)
    red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
    inst = construir(nodos, red, cfg)
    os.remove(ruta)
    return inst, cfg, nodos


# ------------------------------------------------------------- correr el motor
def correr_motor(inst, cfg, con_fallback=True):
    """Corre la fase 1 (max entregas) y fase 2 (min energía) del MILP con la formulación
    indicada en cfg. Devuelve dict con N*, energía, tiempos por fase, gap, formulación.
    Si con_fallback y la compacta deja clientes sin atender, intenta la completa."""
    inicial = heuristica.resolver(inst, bool(cfg["solver"].get("usar_todos_vehiculos")))
    certificado = len(inicial.atendidos) == len(inst.clientes)
    cfg_solver = {**cfg["solver"], "escala": cfg.get("escala", {})}
    t0 = time.perf_counter()
    if cfg["solver"].get("formulacion", "compacta") == "compacta":
        from evrp.milp_compacto import ModeloCompacto
        modelo = ModeloCompacto(inst, cfg_solver, inicial)
    else:
        from evrp.milp import ModeloMILP
        modelo = ModeloMILP(inst, cfg_solver)
    sol, traza = modelo.optimizar(inicial, certificado)
    formulacion = cfg["solver"].get("formulacion", "compacta")
    activo_fallback = False
    if (con_fallback and formulacion == "compacta"
            and (sol is None or len(sol.atendidos) < len(inst.clientes))):
        from evrp.milp import ModeloMILP
        sol_c, traza_c = ModeloMILP(inst, cfg_solver).optimizar(sol or inicial, False)
        if sol_c is not None and (sol is None or (len(sol_c.atendidos), -sol_c.energia) >
                                  (len(sol.atendidos), -sol.energia)):
            sol = sol_c
            traza = {"compacta": traza, "completa": traza_c}
            formulacion = "compacta+completa"
            activo_fallback = True
        else:
            traza = {"compacta": traza, "completa": traza_c}
    t_total = time.perf_counter() - t0
    n_motor = len(sol.atendidos) if sol else 0
    energia = round(sol.energia, 6) if sol else None
    return {"n_motor": n_motor, "energia": energia, "formulacion": formulacion,
            "fallback": activo_fallback, "heur_entregas": len(inicial.atendidos),
            "t_total_s": round(t_total, 3), "traza": traza}
