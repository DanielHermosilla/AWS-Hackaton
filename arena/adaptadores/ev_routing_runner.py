"""Runner de ev_routing para la arena. Se ejecuta DENTRO del entorno del companero
(`uv run --project <ruta> --with highspy==1.11.0 python arena/adaptadores/ev_routing_runner.py ...`).

NO modifica el codigo de ev_routing: importa su API publica (inputs, network, model,
contracts) y conduce la resolucion lexicografica en dos fases con un backend Pyomo
elegido (appsi_highs por defecto; scip si hubiera ejecutable). Emite un JSON por stdout
con rutas condensadas a nodos clave y los tramos (km, desnivel) por paso, para que la
arena los revalide con su validador neutral.

Entrada: argumentos --csv, --graphml, --out, y los supuestos fisicos / solver.
Las rutas de ev_routing son calle a calle; aqui se colapsan a la secuencia de nodos de
servicio (base, visit, charger) manteniendo la energia real de cada arco intermedio.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _parse():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--graphml", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--bateria-kwh", type=float, required=True)
    p.add_argument("--reserva-kwh", type=float, required=True)
    p.add_argument("--soc-inicial", type=float, required=True)
    p.add_argument("--consumo-kwh-km", type=float, required=True)
    p.add_argument("--conectores", default="J1772,CHAdeMO")
    p.add_argument("--vehiculos", type=int, default=2)
    p.add_argument("--movement-limit", type=int, default=30)
    p.add_argument("--presupuesto-s", type=float, default=60.0)
    p.add_argument("--hilos", type=int, default=1)
    p.add_argument("--max-snap-m", type=float, default=100.0)
    p.add_argument("--solver-pyomo", default="appsi_highs")
    return p.parse_args()


def main() -> int:
    a = _parse()
    t0 = time.perf_counter()
    salida = {"motor": "ev_routing", "estado": "error", "movement_limit": a.movement_limit,
              "solver": a.solver_pyomo}
    try:
        from ev_routing.contracts import ModelParameters, SolverConfig
        from ev_routing.inputs import load_routing_nodes
        from ev_routing.network import build_osm_instance

        nodes = load_routing_nodes(a.csv)
        params = ModelParameters(
            vehicle_count=a.vehiculos,
            battery_capacity_kwh=a.bateria_kwh,
            reserve_kwh=a.reserva_kwh,
            initial_soc=a.soc_inicial,
            movement_limit=a.movement_limit,
            vehicle_connector_types=[c.strip() for c in a.conectores.split(",") if c.strip()],
        )
        instance = build_osm_instance(
            nodes, params, a.consumo_kwh_km,
            graphml_path=a.graphml, allow_download=False,
            max_snap_distance_m=a.max_snap_m, name=Path(a.csv).stem)
        salida["nodos_red"] = len(instance.nodes)
        salida["arcos_red"] = len(instance.arcs)

        res = _resolver_lexicografico(instance, a, SolverConfig)
        salida.update(res)
    except Exception as exc:  # noqa: BLE001  -- la arena lo registra como resultado
        salida["estado"] = "error"
        salida["error"] = f"{type(exc).__name__}: {exc}"[:800]
    salida["tiempo_s"] = round(time.perf_counter() - t0, 3)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"estado": salida["estado"], "entregas": salida.get("entregas"),
                      "tiempo_s": salida["tiempo_s"]}, ensure_ascii=False))
    return 0


def _resolver_lexicografico(instance, a, SolverConfig) -> dict:
    """Dos fases (max entregas, luego min energia) con el backend Pyomo elegido.

    Reproduce la logica de ev_routing.solve pero permitiendo appsi_highs sin editar su
    codigo. Usa su build_model/activate_energy_phase/extract_solution tal cual.
    """
    import pyomo.environ as pyo
    from ev_routing.model import activate_energy_phase, build_model, extract_solution

    t0 = time.perf_counter()
    model = build_model(instance)
    solver = pyo.SolverFactory(a.solver_pyomo)
    if not solver.available(exception_flag=False):
        return {"estado": "solver_no_disponible",
                "detalle": f"backend {a.solver_pyomo} no disponible en el entorno"}

    presupuesto = float(a.presupuesto_s)
    # Fase 1: 70% del presupuesto para entregas (como en su solve.py).
    def set_opts(seconds):
        seconds = max(0.5, seconds)
        if a.solver_pyomo == "appsi_highs":
            solver.config.time_limit = seconds
            try:
                solver.config.mip_gap = 0.0
            except Exception:
                pass
            if a.hilos:
                solver.highs_options = {"threads": int(a.hilos)}
        elif a.solver_pyomo == "scip":
            solver.options["limits/time"] = seconds
            solver.options["limits/gap"] = 0.0
            if a.hilos:
                solver.options["parallel/maxnthreads"] = int(a.hilos)

    estado_fase = {}
    # ---- Fase 1: entregas
    set_opts(0.7 * presupuesto)
    r1 = _resolver(solver, model, a.solver_pyomo)
    estado_fase["fase1"] = r1["resumen"]
    if not r1["factible"]:
        return {"estado": "infactible", "entregas": 0, "fases": estado_fase,
                "tiempo_solver_s": round(time.perf_counter() - t0, 3)}
    sol1 = extract_solution(model, instance)
    n_entregas = len(sol1.served_visit_ids)

    # ---- Fase 2: energia con entregas fijas
    restante = presupuesto - (time.perf_counter() - t0)
    mejor = sol1
    if restante > 0.5:
        activate_energy_phase(model, n_entregas)
        set_opts(restante)
        r2 = _resolver(solver, model, a.solver_pyomo)
        estado_fase["fase2"] = r2["resumen"]
        if r2["factible"]:
            sol2 = extract_solution(model, instance)
            if (len(sol2.served_visit_ids) == n_entregas
                    and sol2.net_energy_kwh <= sol1.net_energy_kwh):
                mejor = sol2
    else:
        estado_fase["fase2"] = {"estado": "omitida", "motivo": "sin presupuesto"}

    rutas, tramos = _rutas_clave(mejor, instance)
    return {
        "estado": "ok",
        "entregas": len(mejor.served_visit_ids),
        "entregas_ids": list(mejor.served_visit_ids),
        "energia_neta_motor_kwh": round(float(mejor.net_energy_kwh), 4),
        "rutas": rutas,
        "tramos_por_paso": tramos,
        "tipo_rutas": "calle",
        "fases": estado_fase,
        "gap": r2["resumen"].get("gap") if restante > 0.5 and estado_fase.get("fase2", {}).get("factible") else None,
        "tiempo_solver_s": round(time.perf_counter() - t0, 3),
    }


def _resolver(solver, model, backend) -> dict:
    """Resuelve el modelo con el estado actual de objetivos; devuelve factibilidad y resumen."""
    from pyomo.opt import TerminationCondition
    try:
        results = solver.solve(model, load_solutions=False)
    except Exception as exc:  # noqa: BLE001
        return {"factible": False, "resumen": {"estado": "error", "error": str(exc)[:300]}}
    tc = results.solver.termination_condition
    no_sol = {TerminationCondition.infeasible, TerminationCondition.unbounded,
              TerminationCondition.infeasibleOrUnbounded, TerminationCondition.noSolution,
              TerminationCondition.invalidProblem}
    resumen = {"estado": str(tc)}
    try:
        resumen["cota"] = _finito(results.problem.lower_bound) or _finito(results.problem.upper_bound)
    except Exception:
        resumen["cota"] = None
    if tc in no_sol:
        return {"factible": False, "resumen": resumen}
    try:
        if not len(results.solution):
            return {"factible": False, "resumen": resumen}
        model.solutions.load_from(results)
    except Exception as exc:  # noqa: BLE001
        return {"factible": False, "resumen": {**resumen, "carga": str(exc)[:200]}}
    resumen["factible"] = True
    return {"factible": True, "resumen": resumen}


def _finito(v):
    try:
        f = float(v)
        return f if abs(f) < 1e19 else None
    except (TypeError, ValueError):
        return None


def _rutas_clave(solution, instance) -> tuple[dict, dict]:
    """Colapsa cada ruta calle-a-calle a la secuencia de nodos de servicio (base/visit/charger),
    acumulando los tramos (km, desnivel=0) de los arcos intermedios entre servicios.

    Devuelve (rutas{veh:[node_id]}, tramos_por_paso{veh:[[(km,0.0),...], ...]}).
    """
    tipo = {n.node_id: n.node_type for n in instance.nodes}
    base = instance.depot_id
    dist = {(arc.from_node_id, arc.to_node_id): arc.distance_m for arc in instance.arcs}
    dist[(base, base)] = 0.0

    rutas, tramos_all = {}, {}
    for ruta in solution.routes:
        secuencia = [paso.node_id for paso in ruta.steps]
        # Comprimir permanencias consecutivas en el mismo nodo.
        comprimida = []
        km_acum = []  # km de arcos desde el ultimo servicio
        servicios = [base]
        buffer_km = 0.0
        tramos_veh = []
        prev = secuencia[0]
        for nodo in secuencia[1:]:
            d = dist.get((prev, nodo))
            if d is None:
                buffer_km += 0.0  # arco no mapeado (no deberia pasar)
            else:
                buffer_km += d / 1000.0
            if tipo.get(nodo) in ("base", "visit", "charger") and nodo != prev:
                servicios.append(nodo)
                tramos_veh.append([(round(buffer_km, 6), 0.0)] if buffer_km > 0 else [])
                buffer_km = 0.0
            prev = nodo
        # Normalizar: asegurar inicio/fin en base; recortar permanencias finales en base.
        servicios = _recortar_base(servicios, base)
        tramos_veh = tramos_veh[: max(0, len(servicios) - 1)]
        # Omitir vehiculos que no salieron de la base.
        if len(servicios) <= 1:
            continue
        veh = ruta.vehicle_id
        rutas[veh] = servicios
        tramos_all[veh] = tramos_veh
    if not rutas:  # ningun vehiculo se movio: ruta trivial
        rutas["vehicle_1"] = [base, base]
        tramos_all["vehicle_1"] = [[]]
    return rutas, tramos_all


def _recortar_base(servicios, base):
    """Quita permanencias iniciales/finales repetidas en la base, dejando [base, ..., base]."""
    i = 0
    while i + 1 < len(servicios) and servicios[i] == base and servicios[i + 1] == base:
        i += 1
    j = len(servicios) - 1
    while j - 1 > i and servicios[j] == base and servicios[j - 1] == base:
        j -= 1
    out = servicios[i:j + 1]
    if not out or out[0] != base:
        out = [base, *out]
    if out[-1] != base:
        out = [*out, base]
    return out


if __name__ == "__main__":
    sys.exit(main())
