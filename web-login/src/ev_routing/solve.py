import time
from typing import Any, List, Optional, Tuple

from pyomo.environ import SolverFactory, value
from pyomo.opt import TerminationCondition

from .contracts import PhaseResult, ProblemInstance, SolverConfig, VehicleRoute, RouteStep, RunResult, ValidationResult
from .model import build_model, set_phase_objective
from .validation import validate_solution


def _solver(solver_config: SolverConfig):
    solver = SolverFactory(solver_config.backend or "highs")
    opts = dict(solver_config.options or {})
    if solver_config.time_limit_seconds is not None:
        opts.setdefault("time_limit", float(solver_config.time_limit_seconds))
    if solver_config.mip_gap is not None:
        opts.setdefault("mip_rel_gap", float(solver_config.mip_gap))
    if solver_config.threads is not None:
        opts.setdefault("threads", int(solver_config.threads))
    if solver_config.seed is not None:
        opts.setdefault("random_seed", int(solver_config.seed))
    for k, v in opts.items():
        try:
            solver.options[k] = v
        except Exception:
            pass
    return solver


def _term_str(tc) -> str:
    try:
        return str(tc).lower()
    except Exception:
        return "unknown"


def extract_solution(model: Any, instance: ProblemInstance) -> tuple[List[VehicleRoute], int, float]:
    nodes = [n.node_id for n in instance.nodes]
    vehicles = list(range(instance.fleet.num_vehicles))
    H = instance.movement_limit
    base = instance.base_nodes()[0]
    clients = set(instance.visit_nodes())
    capacity = instance.fleet.battery_capacity_kwh
    energy_map = {}
    for arc in instance.network.arcs:
        energy_map[(arc.origin, arc.destination)] = arc.energy_kwh

    routes: List[VehicleRoute] = []
    all_served: List[str] = []

    for k in vehicles:
        # z location per position
        locs = []
        for r in range(H + 1):
            nid = None
            for i in nodes:
                try:
                    if value(model.z[i, k, r]) > 0.5:
                        nid = i
                        break
                except Exception:
                    pass
            if nid is None:
                nid = base
            locs.append(nid)

        steps: List[RouteStep] = []
        served_this: List[str] = []
        total_energy = 0.0
        dist_km = 0.0
        for r in range(H):
            i = locs[r]
            j = locs[r + 1]
            try:
                ae = float(value(model.b[k, r]))
            except Exception:
                ae = None
            try:
                de = float(value(model.bbar[k, r]))
            except Exception:
                de = None
            try:
                charge = float(value(model.q[k, r]))
            except Exception:
                charge = 0.0
            delivered: List[str] = []
            for c in clients:
                try:
                    if value(model.a[c, k, r]) > 0.5:
                        delivered.append(c)
                except Exception:
                    pass
            served_this.extend(delivered)
            # arc energy
            arc_e = None
            try:
                arc_e = float(energy_map.get((i, j), 0.0))
            except Exception:
                pass
            # actual selected? use x
            try:
                # find selected arc
                sel = None
                for arc in [(i, j)]:
                    try:
                        if value(model.x[arc, k, r]) > 0.5:
                            sel = arc
                    except Exception:
                        pass
                if sel is not None and sel in energy_map:
                    arc_e = float(energy_map[sel])
            except Exception:
                pass
            if arc_e is not None:
                total_energy += float(arc_e)
            step = RouteStep(
                position=r,
                node_id=i,
                arrival_energy_kwh=ae,
                departure_energy_kwh=de,
                charge_kwh=charge,
                delivered_visit_ids=delivered,
                arc_energy_kwh=arc_e,
            )
            steps.append(step)
        # last position step without move
        try:
            last_e = float(value(model.b[k, H]))
        except Exception:
            last_e = None
        steps.append(RouteStep(position=H, node_id=locs[H], arrival_energy_kwh=last_e, departure_energy_kwh=last_e))
        # served unique
        uniq = []
        for v in served_this:
            if v not in uniq:
                uniq.append(v)
        all_served.extend(uniq)
        routes.append(VehicleRoute(
            vehicle_index=k,
            steps=steps,
            served_visit_ids=uniq,
            distance_km=None,
            total_energy_kwh=float(value(model.Etotal)) if k == 0 and vehicles else None,
        ))
    served_count = len(set(all_served))
    total_e = float(value(model.Etotal))
    return routes, served_count, total_e


def solve_lexicographic(
    model: Any,
    instance: ProblemInstance,
    solver_config: SolverConfig,
) -> Tuple[Any, List[PhaseResult], int, float]:
    solver = _solver(solver_config)
    phases: List[PhaseResult] = []

    # Phase 1: maximize deliveries
    phase1_start = time.time()
    set_phase_objective(model, "max_deliveries")
    res1 = solver.solve(model, tee=False)
    phase1_time = time.time() - phase1_start
    tc1 = getattr(res1.solver, "termination_condition", None)
    incumb1 = None
    bound1 = None
    try:
        incumb1 = float(value(model.objective))
        # objective is -deliveries
        incumb1 = -incumb1
    except Exception:
        pass
    try:
        bound1 = getattr(res1.problem, "upper_bound", None)
        if bound1 is None:
            bound1 = getattr(res1.solver, "best_bound", None)
    except Exception:
        pass
    # gap
    gap1 = None
    try:
        if incumb1 is not None and bound1 is not None:
            gap1 = (bound1 - incumb1) / max(abs(incumb1), 1e-9)
    except Exception:
        pass

    Nstar = 0
    try:
        Nstar = int(round(sum(value(model.y[i]) for i in model.CLIENTS)))
    except Exception:
        if incumb1 is not None:
            Nstar = int(round(incumb1))

    phases.append(PhaseResult(
        name="maximize_deliveries",
        objective_sense="maximize_deliveries",
        incumbent_objective=float(Nstar),
        bound=(float(bound1) if bound1 is not None else None),
        gap=gap1,
        termination=_term_str(tc1),
        runtime_seconds=phase1_time,
    ))

    # Phase 2: minimize energy with deliveries fixed
    phase2_start = time.time()
    set_phase_objective(model, "min_energy", target_deliveries=Nstar)
    res2 = solver.solve(model, tee=False)
    phase2_time = time.time() - phase2_start
    tc2 = getattr(res2.solver, "termination_condition", None)
    incumb2 = None
    bound2 = None
    try:
        incumb2 = float(value(model.Etotal))
    except Exception:
        pass
    try:
        bound2 = getattr(res2.problem, "lower_bound", None)
        if bound2 is None:
            bound2 = getattr(res2.solver, "best_bound", None)
    except Exception:
        pass
    gap2 = None
    try:
        if incumb2 is not None and bound2 is not None:
            gap2 = (incumb2 - bound2) / max(abs(incumb2), 1e-9)
    except Exception:
        pass
    phases.append(PhaseResult(
        name="minimize_energy",
        objective_sense="minimize_energy",
        incumbent_objective=incumb2,
        bound=(float(bound2) if bound2 is not None else None),
        gap=gap2,
        termination=_term_str(tc2),
        runtime_seconds=phase2_time,
    ))

    routes, served_count, total_energy = extract_solution(model, instance)
    return model, phases, Nstar, total_energy


def run_pipeline(
    instance: ProblemInstance,
    solver_config: Optional[SolverConfig] = None,
    run_id: Optional[str] = None,
) -> RunResult:
    if solver_config is None:
        solver_config = SolverConfig()
    warnings: List[str] = []
    total_start = time.time()
    model_start = time.time()
    model = build_model(instance)
    model_time = time.time() - model_start

    solve_start = time.time()
    model, phases, Nstar, total_energy = solve_lexicographic(model, instance, solver_config)
    solve_time = time.time() - solve_start

    routes, served_count, _ = extract_solution(model, instance)
    validation_time_start = time.time()
    validation = validate_solution(model, instance)
    validation_time = time.time() - validation_time_start

    unserved = [v for v in instance.visit_nodes() if v not in {s for r in routes for s in r.served_visit_ids}]
    kpis = {
        "delivered_visits": served_count,
        "total_visits": len(instance.visit_nodes()),
        "total_energy_kwh": total_energy,
    }
    run = RunResult(
        run_id=run_id,
        instance_id=instance.instance_id,
        phases=phases,
        routes=routes,
        unserved_visit_ids=unserved,
        validation=validation,
        kpis=kpis,
        runtime_seconds={
            "model_seconds": model_time,
            "solver_seconds": solve_time,
            "validation_seconds": validation_time,
            "total_seconds": time.time() - total_start,
        },
        warnings=warnings,
        served_count=served_count,
        total_energy_kwh=total_energy,
        delivered_count=served_count,
        metadata={
            "solver": solver_config.backend,
            "movement_limit": instance.movement_limit,
        },
    )
    return run


# aliases
def solve_instance(instance, solver_config=None, run_id=None):
    return run_pipeline(instance, solver_config, run_id)

solve_problem = run_pipeline
solve_model = run_pipeline
