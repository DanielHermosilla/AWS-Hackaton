"""Dantzig–Wolfe por rutas, sin H; SCIP ramifica en asignaciones de clientes.

lambda es continua. Si todas las asignaciones z_ki son enteras, todas las
columnas positivas de cada vehículo atienden el mismo subconjunto. Escoger la
de menor energía recupera una ruta entera sin empeorar el objetivo. Por eso no
se ramifica sobre columnas que todavía no existen.
"""

from __future__ import annotations

from itertools import combinations, islice
from pathlib import Path
from time import monotonic

import networkx as nx
import numpy as np
from pyscipopt import SCIP_PARAMSETTING, SCIP_RESULT, Model, Pricer, quicksum

from ev_routing.contracts import PhaseResult, ProblemInstance, SolverConfig, SolveResult
from ev_routing.operations import arc_energy
from ev_routing.route_policy import choose_route_policy
from ev_routing.route_resources import RouteOracle, assemble_solution, route_from_walk
from ev_routing.search_policy import SearchConfig
from ev_routing.validation import validate_solution


def _configure(model, config, policy, log_directory=None, name="solve"):
    model.hideOutput(not config.tee)
    model.setIntParam("parallel/maxnthreads", config.threads)
    model.setIntParam("lp/threads", config.threads)
    model.setIntParam("randomization/randomseedshift", config.seed)
    model.setRealParam("limits/gap", config.relative_gap)
    model.setIntParam(f"branching/{policy.branching}/priority", 1000000)
    if log_directory:
        directory = Path(log_directory)
        directory.mkdir(parents=True, exist_ok=True)
        model.setLogfile(str(directory / f"{name}.scip.log"))


def _valid(instance, solution):
    return validate_solution(instance, solution, enforce_movement_limit=False)


def certify_single_tour(instance: ProblemInstance, deadline: float):
    """Probar existencia de un óptimo de flota representable por un solo tour.

    Con U <= b_ini-reserva, costes no negativos y métrica dirigida, fusionar
    rutas y quitar visitas sin entrega no aumenta el consumo. Toda solución
    mejor que el testigo cabe entonces en la batería inicial. No se elige H.
    """
    ops, params = instance.operations, instance.parameters
    certificate = {"applicable": False, "reason": "hypotheses_not_verified"}
    if (
        any(n.node_type == "junction" for n in instance.nodes)
        or ops.max_route_seconds is not None or ops.use_customer_time_windows
        or (ops.final_reserve_soc or 0) * params.battery_capacity_kwh > params.reserve_kwh
        or any(arc_energy(a, ops) < 0 for a in instance.arcs)
        or not instance.customer_ids
    ):
        return certificate, None
    ids = {n.node_id: i for i, n in enumerate(instance.nodes)}
    energy = np.full((len(ids), len(ids)), np.inf)
    np.fill_diagonal(energy, 0)
    for a in instance.arcs:
        energy[ids[a.from_node_id], ids[a.to_node_id]] = arc_energy(a, ops)
    for middle in range(len(ids)):
        if monotonic() >= deadline:
            return {**certificate, "reason": "verification_budget"}, None
        if np.any(energy > energy[:, middle, None] + energy[middle, None, :]):
            return {**certificate, "reason": "not_directed_metric"}, None
    graph = nx.DiGraph()
    nodes = [instance.depot_id, *sorted(instance.customer_ids)]
    graph.add_nodes_from(nodes)
    graph.add_weighted_edges_from(
        (a.from_node_id, a.to_node_id, arc_energy(a, ops))
        for a in instance.arcs if a.from_node_id in graph and a.to_node_id in graph
    )
    if graph.number_of_edges() != len(nodes) * (len(nodes) - 1):
        return {**certificate, "reason": "customers_not_strongly_connected"}, None
    usable = params.initial_energy_kwh - params.reserve_kwh
    for source in nodes:
        if monotonic() >= deadline:
            break
        walk = nx.approximation.greedy_tsp(graph, source=source)
        cycle = walk[:-1]
        index = cycle.index(instance.depot_id)
        walk = cycle[index:] + cycle[:index] + [instance.depot_id]
        cost = sum(graph[a][b]["weight"] for a, b in zip(walk, walk[1:]))
        if cost <= usable:
            routes = [
                route_from_walk(instance, instance.vehicle_ids[0], walk, range(1, len(walk) - 1),
                                np.zeros(len(walk))),
                *[route_from_walk(instance, k, [instance.depot_id], [], [0])
                  for k in instance.vehicle_ids[1:]],
            ]
            solution = assemble_solution(instance, routes)
            if _valid(instance, solution).feasible:
                return {
                    "applicable": True, "reason": "nonnegative_metric_tour_fits_initial_battery",
                    "witness_energy_kwh": cost, "usable_initial_energy_kwh": usable,
                    "directed_triangle_verified": True, "movement_limit_used": None,
                }, solution
    return {**certificate, "reason": "no_complete_battery_feasible_witness"}, None


def _phase(name, best, bound, termination, seconds, *, valid_bound=True, message=""):
    value = None if best is None else (
        float(len(best.served_visit_ids)) if name == "deliveries" else best.net_energy_kwh
    )
    bound = bound if valid_bound else None
    proven = value is not None and bound is not None and abs(value - bound) <= 1e-7
    gap = None if value is None or bound is None else abs(value - bound)
    return PhaseResult(
        name=name, sense="maximize" if name == "deliveries" else "minimize",
        status="optimal" if proven else "feasible" if best else (
            "infeasible" if termination == "infeasible" and valid_bound else
            "error" if termination == "error" else "time_limit"
        ),
        termination_condition=termination, incumbent=value, best_bound=bound,
        absolute_gap=gap, relative_gap=None if gap is None else gap / max(abs(value), 1e-10),
        has_solution=best is not None, proven_optimal=proven, runtime_seconds=seconds,
        incumbent_source="provided_incumbent" if termination == "witness_and_cardinality_bound"
        else "solver" if best else None, message=message,
    )


def _tour_solve(instance, config, policy, deadline, best, log_directory=None):
    """DFJ dirigido. Cada relajación conserva una cota, incluso con subtours."""
    started = monotonic()
    nodes = [instance.depot_id, *instance.customer_ids]
    costs = {(a.from_node_id, a.to_node_id): arc_energy(a, instance.operations)
             for a in instance.arcs if a.from_node_id in nodes and a.to_node_id in nodes}
    model = Model("certified_directed_tour")
    _configure(model, config, policy, log_directory, "energy")
    x = {ij: model.addVar(vtype="B", obj=c, name=f"arc_{n}")
         for n, (ij, c) in enumerate(costs.items())}
    for node in nodes:
        model.addCons(quicksum(x[i, j] for i, j in x if i == node) == 1)
        model.addCons(quicksum(x[i, j] for i, j in x if j == node) == 1)
    model.addCons(quicksum(costs[ij] * x[ij] for ij in x) <= best.net_energy_kwh)
    seed = model.createSol()
    selected = {(s.node_id, s.next_node_id) for s in best.routes[0].steps if s.next_node_id}
    for ij, variable in x.items():
        model.setSolVal(seed, variable, int(ij in selected))
    model.addSol(seed)
    bound, rounds, count, native_seconds = 0.0, 0, 0, 0.0
    termination = "budget_exhausted"
    while monotonic() < deadline:
        model.setRealParam("limits/time", max(0.001, deadline - monotonic()))
        optimizing = monotonic()
        model.optimize()
        native_seconds += monotonic() - optimizing
        rounds += 1
        termination = str(model.getStatus())
        native_bound = model.getDualbound()
        if abs(native_bound) < model.infinity():
            bound = max(bound, native_bound)
        if not model.getNSols():
            break
        sol = model.getBestSol()
        successor = {i: j for (i, j), variable in x.items()
                     if model.getSolVal(sol, variable) > 0.5}
        graph = nx.DiGraph(successor.items())
        components = list(nx.strongly_connected_components(graph))
        if len(components) == 1:
            walk = [instance.depot_id]
            while successor[walk[-1]] != instance.depot_id:
                walk.append(successor[walk[-1]])
            walk.append(instance.depot_id)
            route = route_from_walk(
                instance, instance.vehicle_ids[0], walk, range(1, len(walk) - 1), np.zeros(len(walk)),
            )
            candidate = assemble_solution(instance, [route, *best.routes[1:]])
            if _valid(instance, candidate).feasible and candidate.net_energy_kwh <= best.net_energy_kwh:
                best = candidate
            break
        model.freeTransform()
        for component in components[:policy.subtour_batch_size]:
            model.addCons(quicksum(x[i, j] for i, j in x if i in component and j in component)
                          <= len(component) - 1)
            count += 1
    stat = {
        "algorithm": "certified_single_tour_dfj", "binary_arc_variables": len(x),
        "subtour_rounds": rounds, "subtour_cuts": count, "movement_limit_used": None,
        "native_optimize_seconds": native_seconds,
    }
    model.freeProb()
    return best, _phase("energy", best, bound, termination, monotonic() - started), stat


class RoutePricer(Pricer):
    def __init__(self, instance, oracles, convex, links, cuts, columns, phase, deadline, policy):
        self.instance, self.oracles = instance, oracles
        self.convex, self.links, self.cuts, self.columns = convex, links, cuts, columns
        self.phase, self.deadline, self.policy = phase, deadline, policy
        self.keys = set()
        self.incomplete = False
        self.error = None
        self.calls = 0
        self.farkas_calls = 0
        self.max_columns_added_per_call = 0

    def pricerinit(self):
        self.convex = {k: self.model.getTransformedCons(c) for k, c in self.convex.items()}
        self.links = {ki: self.model.getTransformedCons(c) for ki, c in self.links.items()}
        self.cuts = [(mask, self.model.getTransformedCons(c)) for mask, c in self.cuts]

    def add(self, vehicle, mask, route, *, priced):
        key = vehicle, mask, route.net_energy_kwh
        if key in self.keys:
            return False
        self.keys.add(key)
        model = self.model
        var = model.addVar(
            name=f"route_{len(self.columns)}", vtype="C", lb=0,
            obj=route.net_energy_kwh if self.phase == "energy" else 0,
            pricedVar=priced,
        )
        model.addConsCoeff(self.convex[vehicle], var, 1)
        for i in range(len(self.instance.customer_ids)):
            if mask & (1 << i):
                model.addConsCoeff(self.links[vehicle, i], var, 1)
        for subset, cons in self.cuts:
            coef = (mask & subset).bit_count() // 2
            if coef:
                model.addConsCoeff(cons, var, coef)
        self.columns.append((vehicle, mask, route, var))
        return True

    def _price(self, farkas):
        self.calls += 1
        self.farkas_calls += int(farkas)
        model = self.model
        dual = model.getDualfarkasLinear if farkas else model.getDualsolLinear
        convex = {k: dual(c) for k, c in self.convex.items()}
        links = {ki: dual(c) for ki, c in self.links.items()}
        cuts = [(mask, dual(c)) for mask, c in self.cuts]
        added = 0

        def consider(vehicle, routes):
            nonlocal added
            for mask, route in routes.items():
                if added >= self.policy.columns_per_round:
                    break
                reduced = route.net_energy_kwh if self.phase == "energy" and not farkas else 0.0
                reduced -= convex[vehicle]
                reduced -= sum(links[vehicle, i] for i in range(len(self.instance.customer_ids))
                               if mask & (1 << i))
                reduced -= sum(value * ((mask & subset).bit_count() // 2) for subset, value in cuts)
                if reduced < -model.getParam("numerics/dualfeastol"):
                    added += int(self.add(vehicle, mask, route, priced=True))
                    self.max_columns_added_per_call = max(
                        self.max_columns_added_per_call, added,
                    )

        for vehicle, oracle in self.oracles.items():
            consider(vehicle, oracle.routes)
        while added < self.policy.columns_per_round and not all(o.complete for o in self.oracles.values()):
            if monotonic() >= self.deadline:
                self.incomplete = True
                model.interruptSolve()
                return {"result": SCIP_RESULT.SUCCESS if added else SCIP_RESULT.DIDNOTRUN}
            for vehicle, oracle in self.oracles.items():
                if not oracle.complete:
                    consider(vehicle, oracle.advance())
            if monotonic() >= self.deadline:
                self.incomplete = not all(o.complete for o in self.oracles.values())
                model.interruptSolve()
                return {"result": SCIP_RESULT.SUCCESS if added else SCIP_RESULT.DIDNOTRUN}
            # Devolver pronto columnas: el siguiente dual puede ser muy distinto.
            if added:
                break
        return {"result": SCIP_RESULT.SUCCESS}

    def _safe_price(self, farkas):
        try:
            return self._price(farkas)
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            self.incomplete = True
            self.model.interruptSolve()
            return {"result": SCIP_RESULT.DIDNOTRUN}

    def pricerredcost(self):
        return self._safe_price(False)

    def pricerfarkas(self):
        return self._safe_price(True)


def _master_phase(instance, config, policy, oracles, name, deadline, best, log_directory=None):
    started = monotonic()
    model = Model(f"routes_{name}")
    _configure(model, config, policy, log_directory, name)
    model.setPresolve(SCIP_PARAMSETTING.OFF)
    model.setSeparating(SCIP_PARAMSETTING.OFF)
    model.setIntParam("propagating/rootredcost/freq", -1)
    n = len(instance.customer_ids)
    z = {(k, i): model.addVar(vtype="B", obj=-1 if name == "deliveries" else 0,
                             name=f"serve_{k}_{i}")
         for k in instance.vehicle_ids for i in range(n)}
    for i in range(n):
        model.addCons(quicksum(z[k, i] for k in instance.vehicle_ids) <= 1)
    if name == "energy":
        model.addCons(quicksum(z.values()) == len(best.served_visit_ids))
    convex = {k: model.addCons(quicksum([]) == 1, modifiable=True, name=f"vehicle_{k}")
              for k in instance.vehicle_ids}
    links = {(k, i): model.addCons(-var == 0, modifiable=True, name=f"link_{k}_{i}")
             for (k, i), var in z.items()}
    cuts = []
    if policy.route_cuts == "subset_row_triples":
        for triple in islice(combinations(range(n), 3), policy.max_subset_rows):
            mask = sum(1 << i for i in triple)
            cuts.append((mask, model.addCons(quicksum([]) <= 1, modifiable=True)))
    columns = []
    pricer = RoutePricer(instance, oracles, convex, links, cuts, columns, name, deadline, policy)
    model.includePricer(pricer, "physical_routes", "Continuous-resource route pricing", delay=True)
    if best is not None:
        seed = model.createSol()
        for route in best.routes:
            served = {i for step in route.steps for i in step.delivered_visit_ids}
            mask = sum(1 << i for i, node in enumerate(instance.customer_ids) if node in served)
            pricer.add(route.vehicle_id, mask, route, priced=False)
            model.setSolVal(seed, columns[-1][3], 1)
            for i, node in enumerate(instance.customer_ids):
                model.setSolVal(seed, z[route.vehicle_id, i], int(node in served))
        model.addSol(seed)
    model.setRealParam("limits/time", max(0.001, deadline - monotonic()))
    optimizing = monotonic()
    model.optimize()
    native_seconds = monotonic() - optimizing
    termination = "error" if pricer.error else (
        "pricing_incomplete" if pricer.incomplete else str(model.getStatus())
    )
    valid_bound = not pricer.incomplete
    bound = model.getDualbound()
    if abs(bound) >= model.infinity() or not valid_bound:
        bound = None
    elif name == "deliveries":
        bound = min(n, -bound)
    if model.getNSols():
        sol = model.getBestSol()
        routes = []
        for vehicle in instance.vehicle_ids:
            mask = sum(1 << i for i in range(n) if model.getSolVal(sol, z[vehicle, i]) > 0.5)
            candidates = [route for k, subset, route, var in columns if k == vehicle and subset == mask]
            if not candidates:
                raise RuntimeError("Asignación integral sin columna compatible")
            routes.append(min(candidates, key=lambda r: r.net_energy_kwh))
        candidate = assemble_solution(instance, routes)
        report = _valid(instance, candidate)
        if not report.feasible:
            raise ValueError(f"Columna físicamente inválida: {report.violations}")
        if best is None or (len(candidate.served_visit_ids), -candidate.net_energy_kwh) >= (
            len(best.served_visit_ids), -best.net_energy_kwh
        ):
            best = candidate
    # Cotas analíticas siguen siendo válidas si el pricing agota su presupuesto.
    if bound is None:
        bound = float(n) if name == "deliveries" else (
            0.0 if all(arc_energy(a, instance.operations) >= 0 for a in instance.arcs) else
            len(instance.vehicle_ids) * (instance.parameters.initial_energy_kwh
                                        - instance.parameters.battery_capacity_kwh)
        )
    phase = _phase(
        name, best, bound, termination, monotonic() - started,
        message=pricer.error or ("Pricing incompleto; solo cota analítica." if pricer.incomplete else ""),
    )
    stat = {
        "name": name, "columns": len(columns), "subset_row_cuts": len(cuts),
        "pricing_calls": pricer.calls, "farkas_calls": pricer.farkas_calls,
        "max_columns_added_per_call": pricer.max_columns_added_per_call,
        "pricing_interrupted": pricer.incomplete, "pricing_error": pricer.error,
        "oracle_complete": {k: o.complete for k, o in oracles.items()},
        "labels_expanded": {k: o.expanded for k, o in oracles.items()},
        "branch_nodes": model.getNNodes(), "movement_limit_used": None,
        "native_optimize_seconds": native_seconds,
        "bound_source": "analytic" if pricer.incomplete else "SCIP_with_exact_pricing_or_analytic",
    }
    model.freeProb()
    return best, phase, stat


def solve_routes(instance, config: SolverConfig, search_config=None, *, initial_solution=None,
                 policy_provider=None):
    started = monotonic()
    deadline = started + config.time_limit_seconds
    search_config = search_config or SearchConfig()
    if initial_solution is not None and not _valid(instance, initial_solution).feasible:
        raise ValueError("Solución inicial inválida para el modelo sin H")
    certificate, witness = certify_single_tour(instance, min(deadline, started + 0.5))
    best = witness or initial_solution
    profile = {
        "formulation": "complete_feasible_routes_without_H",
        "customers": len(instance.customer_ids), "vehicles": len(instance.vehicle_ids),
        "nodes": len(instance.nodes), "arcs": len(instance.arcs),
        "single_tour_certificate": certificate,
        "operations": instance.operations.model_dump(exclude={
            "customer_time_windows", "service_seconds_by_customer", "charging_power_kw_by_station",
        }),
        "applicable_actions": ["subtour_batch_size", "branching"] if witness else
        ["route_cuts", "columns_per_round", "max_subset_rows", "branching"],
    }
    policy, tuning = choose_route_policy(search_config, profile, deadline, policy_provider)
    phases, stats = [], []
    if witness is not None:
        phases.append(_phase(
            "deliveries", best, float(len(instance.customer_ids)), "witness_and_cardinality_bound",
            monotonic() - started,
        ))
        best, phase, stat = _tour_solve(
            instance, config, policy, deadline, best, search_config.log_directory,
        )
        phases.append(phase)
        stats.append(stat)
    else:
        oracles = {k: RouteOracle(instance, k) for k in instance.vehicle_ids}
        for name in ("deliveries", "energy"):
            if name == "energy" and best is None:
                break
            phase_deadline = (monotonic() + 0.7 * max(0, deadline - monotonic())
                              if name == "deliveries" else deadline)
            best, phase, stat = _master_phase(
                instance, config, policy, oracles, name, phase_deadline, best,
                search_config.log_directory,
            )
            phases.append(phase)
            stats.append(stat)
            if phase.status in {"infeasible", "error"}:
                break
    optimal = len(phases) == 2 and all(p.proven_optimal for p in phases)
    return SolveResult(
        requested_solver=config.solver, used_solver="scip-routes",
        solver_version="SCIP 10.0.0 / PySCIPOpt 6.0.0",
        phases=phases, solution=best, lexicographic_optimal=optimal,
        status="optimal" if optimal else "feasible" if best else phases[-1].status,
        solution_source=(
            "initial_solution" if best is initial_solution else "heuristic" if best is witness
            else "solver"
        ) if best else None,
        runtime_seconds=monotonic() - started,
        message="Formulación por rutas sin H. El certificado se refiere al grafo y energía de entrada.",
        search={
            "engine": "scip_routes_without_h", "movement_limit_used": None,
            "single_tour_certificate": certificate, "phases": stats,
            "controller": tuning, "configuration": search_config.model_dump(),
        },
    )
