"""Competencia de solvers sobre el MILP de evrp exportado a MPS.

Se construye la fase 1 del modelo compacto de evrp (maximizar entregas) mediante su
clase ModeloCompacto SIN modificar su archivo, y se exporta a MPS con highspy.writeModel.
Luego cada backend resuelve el MISMO MPS con el mismo limite de tiempo e hilos:

  - highs: highspy (readModel + run)
  - scip:  pyscipopt (readProblem + optimize)
  - cbc:   pulp.COIN_CMD (requiere cbc.exe; en 4.0.1 no viene empaquetado -> se registra
           como no disponible si no hay ejecutable)

Metricas por solver: estado, objetivo, cota, gap (|obj-cota|/max(1,|obj|,|cota|)), tiempo.

NOTA: el modelo Pyomo del companero tambien puede exportarse a MPS, pero su resolucion
es por posicion (H) y vive en otro entorno; su exportacion se intenta en el runner
externo (bandera aparte) y queda documentada como limitacion si no se logra aqui.
"""
from __future__ import annotations

import time
from pathlib import Path


def construir_mps_evrp(csv_nodos: str, sup, vehiculos: int, osm_cache: str,
                       destino_mps: Path, fase: str = "entregas") -> dict:
    """Construye el MILP compacto de evrp y lo escribe a MPS. Devuelve metadatos.

    fase='entregas' exporta la fase 1 (max sum y_i). fase='energia' fija Y>=N* (de la
    heuristica inicial) y exporta la minimizacion de energia.
    """
    import evrp.config as cfgmod
    from evrp.datos import cargar_nodos
    from evrp.instancia import construir
    from evrp.milp_compacto import ModeloCompacto
    from evrp.red import crear_red

    grafo = None
    if sup.red == "osm":
        from arena.instancias import grafo_osm_descomprimido
        grafo = str(grafo_osm_descomprimido())

    extra = {
        "flota": [{"tipo": "leaf2013", "cantidad": int(vehiculos)}],
        "tipos_vehiculo": {"leaf2013": {
            "bateria_kwh": sup.bateria_kwh, "soc_inicial": sup.soc_inicial,
            "reserva_kwh": sup.reserva_kwh, "consumo_kwh_km": sup.consumo_kwh_km,
            "conectores": list(sup.conectores)}},
        "pipeline": {"red": sup.red, "energia": "pendiente" if sup.pendiente else "plano",
                     "solver": "milp"},
        "red": {"osm_cache": osm_cache, "osm_grafo": grafo, "osm_permitir_descarga": False,
                "max_acceso_m": sup.max_acceso_m},
        "solver": {"formulacion": "compacta"},
    }
    cfg = cfgmod.cargar(None, extra, None)
    nodos = cargar_nodos(csv_nodos)
    red = crear_red(cfg)
    from evrp.instancia import tipos_desde_config
    red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
    inst = construir(nodos, red, cfg)

    # Heuristica inicial para la fase de energia (y para sembrar arcos).
    inicial = None
    try:
        from evrp import heuristica
        inicial = heuristica.resolver(inst, False)
    except Exception:
        inicial = None

    modelo = ModeloCompacto(inst, cfg["solver"], inicial)
    if fase == "entregas":
        modelo._objetivo("max", modelo.Y)
    else:
        import highspy
        n_est = len(inicial.atendidos) if inicial else 0
        modelo.h.addConstr(modelo.Y >= n_est)
        modelo._objetivo("min", modelo.E)
    destino_mps.parent.mkdir(parents=True, exist_ok=True)
    modelo.h.writeModel(str(destino_mps))
    return {"columnas": modelo.h.getNumCol(), "filas": modelo.h.getNumRow(),
            "clientes": len(inst.clientes), "fase": fase,
            "mps": str(destino_mps)}


# ----------------------------------------------------------------- solvers
def _gap(obj, cota):
    if obj is None or cota is None:
        return None
    return abs(obj - cota) / max(1.0, abs(obj), abs(cota))


def resolver_highs(mps: str, limite: float, hilos: int) -> dict:
    import highspy
    h = highspy.Highs()
    h.silent()
    h.setOptionValue("time_limit", max(0.5, float(limite)))
    if hilos:
        h.setOptionValue("threads", int(hilos))
    h.setOptionValue("mip_rel_gap", 0.0)
    t0 = time.perf_counter()
    h.readModel(mps)
    h.run()
    dt = time.perf_counter() - t0
    info = h.getInfo()
    obj = info.objective_function_value
    cota = info.mip_dual_bound
    estado = h.modelStatusToString(h.getModelStatus())
    return {"solver": "highs", "estado": estado, "objetivo": _fin(obj), "cota": _fin(cota),
            "gap": _fin(info.mip_gap) if _fin(info.mip_gap) is not None else _gap(_fin(obj), _fin(cota)),
            "tiempo_s": round(dt, 3)}


def resolver_scip(mps: str, limite: float, hilos: int) -> dict:
    import pyscipopt
    m = pyscipopt.Model()
    m.hideOutput()
    m.readProblem(mps)
    m.setParam("limits/time", max(0.5, float(limite)))
    m.setParam("limits/gap", 0.0)
    if hilos:
        try:
            m.setParam("parallel/maxnthreads", int(hilos))
        except Exception:
            pass
    t0 = time.perf_counter()
    m.optimize()
    dt = time.perf_counter() - t0
    estado = m.getStatus()
    obj = cota = None
    try:
        if m.getNSols() > 0:
            obj = m.getObjVal()
        cota = m.getDualbound()
    except Exception:
        pass
    return {"solver": "scip", "estado": estado, "objetivo": _fin(obj), "cota": _fin(cota),
            "gap": _gap(_fin(obj), _fin(cota)), "tiempo_s": round(dt, 3)}


def resolver_cbc(mps: str, limite: float, hilos: int) -> dict:
    """Intenta CBC via pulp.COIN_CMD. En pulp 4.0.1 no viene empaquetado; si no hay
    ejecutable cbc en PATH, se registra como no disponible."""
    try:
        import pulp
        from pulp.apis import COIN_CMD
    except Exception as exc:  # noqa: BLE001
        return {"solver": "cbc", "estado": "no_disponible", "error": str(exc)[:200]}
    cmd = COIN_CMD(msg=0, timeLimit=float(limite), threads=int(hilos) or 1)
    if not cmd.available():
        return {"solver": "cbc", "estado": "no_disponible",
                "error": "cbc.exe no encontrado (pulp 4.0.1 no empaqueta CBC en esta plataforma)"}
    var, prob = pulp.LpProblem.fromMPS(mps)
    t0 = time.perf_counter()
    prob.solve(cmd)
    dt = time.perf_counter() - t0
    obj = pulp.value(prob.objective)
    estado = pulp.LpStatus[prob.status]
    return {"solver": "cbc", "estado": estado, "objetivo": _fin(obj), "cota": None,
            "gap": None, "tiempo_s": round(dt, 3)}


SOLVERS = {"highs": resolver_highs, "scip": resolver_scip, "cbc": resolver_cbc}


def competir(mps: str, solvers: list[str], limite: float, hilos: int) -> list[dict]:
    salidas = []
    for s in solvers:
        fn = SOLVERS.get(s)
        if fn is None:
            salidas.append({"solver": s, "estado": "desconocido"})
            continue
        try:
            salidas.append(fn(mps, limite, hilos))
        except Exception as exc:  # noqa: BLE001
            salidas.append({"solver": s, "estado": "error", "error": str(exc)[:300]})
    return salidas


def _fin(v):
    try:
        f = float(v)
        return f if abs(f) < 1e19 else None
    except (TypeError, ValueError):
        return None
