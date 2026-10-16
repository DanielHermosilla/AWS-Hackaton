"""Dantzig–Wolfe por rutas, sin H; SCIP ramifica en asignaciones de clientes.

lambda es continua. Si todas las asignaciones z_ki son enteras, todas las
columnas positivas de cada vehículo atienden el mismo subconjunto. Escoger la
de menor energía recupera una ruta entera sin empeorar el objetivo. Por eso no
se ramifica sobre columnas que todavía no existen.
"""

from __future__ import annotations

from itertools import combinations, islice
from math import isfinite
from pathlib import Path
from time import monotonic

import networkx as nx
import numpy as np
from pyscipopt import SCIP_PARAMSETTING, SCIP_RESULT, Model, Pricer, quicksum

from ev_routing.contracts import PhaseResult, ProblemInstance, SolverConfig, SolveResult
from ev_routing.llm_head import LLMHead
from ev_routing.operations import arc_energy
from ev_routing.route_callbacks import install_callbacks
from ev_routing.route_hybrid import HybridRoutes
from ev_routing.route_pricing import PricingNetwork, ReducedCostOracle
from ev_routing.route_relaxation import energy_relaxation
from ev_routing.route_resources import RouteOracle, assemble_solution, route_from_walk
from ev_routing.scip_tuning import apply_parameters
from ev_routing.search_policy import SearchConfig
from ev_routing.validation import validate_solution


def _configure(model, config, policy, log_directory=None, name="solve", *, single_tour=False,
               energy_phase=False):
    model.hideOutput(not config.tee)
    model.setIntParam("parallel/maxnthreads", config.threads)
    model.setIntParam("lp/threads", config.threads)
    model.setIntParam("randomization/randomseedshift", config.seed)
    model.setRealParam("limits/gap", config.energy_relative_gap if energy_phase else config.relative_gap)
    model.setIntParam(f"branching/{policy.branching}/priority", 1000000)
    if log_directory:
        directory = Path(log_directory)
        directory.mkdir(parents=True, exist_ok=True)
        model.setLogfile(str(directory / f"{name}.scip.log"))
    return apply_parameters(model, policy, single_tour=single_tour)


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
        any(a.battery_profile is not None for a in instance.arcs)
        or
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
    if value is not None and bound is not None and (
        (name == "energy" and bound > value + 1e-7)
        or (name == "deliveries" and bound < value - 1e-7)
    ):
        bound = None
        termination = "inconsistent_bound"
        message = "Cota incompatible con el incumbente validado; se conserva la solución sin certificado."
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


def _energy_gap_reached(best, bound, tolerance):
    """Misma definición que PhaseResult; solo recibe cotas globales válidas."""
    if best is None or bound is None or tolerance <= 0:
        return False
    value = best.net_energy_kwh
    if not isfinite(value) or not isfinite(bound) or bound > value + 1e-7:
        return False
    return abs(value - bound) / max(abs(value), 1e-10) <= tolerance


def _tour_solve(instance, config, policy, deadline, best, log_directory=None, controller=None):
    """DFJ dirigido. Cada relajación conserva una cota, incluso con subtours."""
    started = monotonic()
    nodes = [instance.depot_id, *instance.customer_ids]
    costs = {(a.from_node_id, a.to_node_id): arc_energy(a, instance.operations)
             for a in instance.arcs if a.from_node_id in nodes and a.to_node_id in nodes}
    model = Model("certified_directed_tour")
    native_changes = _configure(model, config, policy, log_directory, "energy", single_tour=True,
                                energy_phase=True)
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
    hub = None
    if controller is not None:
        controller.current_phase = "energy"
        controller.attach_master(model, "certified-tour")
        if controller.config.tree_control:
            hub = install_callbacks(model, controller, "energy", deadline, instance)
    bound, rounds, count, native_seconds = 0.0, 0, 0, 0.0
    termination = "budget_exhausted"
    while monotonic() < deadline:
        model.setRealParam("limits/time", max(0.001, deadline - monotonic()))
        optimizing = monotonic()
        model.optimizeNogil()
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
            if _energy_gap_reached(best, bound, config.energy_relative_gap):
                termination = "energy_gap_limit"
            break
        if _energy_gap_reached(best, bound, config.energy_relative_gap):
            termination = "energy_gap_limit"
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
        "native_parameter_changes": native_changes,
        "callback_control": hub.report() if hub else None,
    }
    model.freeProb()
    return best, _phase("energy", best, bound, termination, monotonic() - started), stat


class RoutePricer(Pricer):
    def __init__(self, instance, oracles, convex, links, cuts, columns, phase, deadline, policy,
                 heuristics=None):
        self.instance, self.oracles = instance, oracles
        self.convex, self.links, self.cuts, self.columns = convex, links, cuts, columns
        self.phase, self.deadline, self.policy = phase, deadline, policy
        self.keys = set()
        self.incomplete = False
        self.error = None
        self.calls = 0
        self.farkas_calls = 0
        self.max_columns_added_per_call = 0
        self.heuristics = heuristics
        self.heuristic_calls = 0
        self.heuristic_columns = 0
        self.heuristic_seconds = 0.0
        self.exact_seconds = 0.0
        self.network = getattr(heuristics, "network", None) or PricingNetwork(instance)
        self.dual_labels = self.bound_prunes = self.return_prunes = 0
        self.exact_queries = self.completed_queries = 0
        self.last_rewards = {}
        self.hub = None
        self.integrality_columns = 0
        self.last_query_complete = False

    def pricerinit(self):
        self.convex = {k: self.model.getTransformedCons(c) for k, c in self.convex.items()}
        self.links = {ki: self.model.getTransformedCons(c) for ki, c in self.links.items()}
        self.cuts = [(mask, self.model.getTransformedCons(c)) for mask, c in self.cuts]

    def add(self, vehicle, mask, route, *, priced):
        key = vehicle, mask, route.net_energy_kwh
        if key in self.keys:
            return False
        self.keys.add(key)
        if route.vehicle_id != vehicle:
            route = route.model_copy(update={"vehicle_id": vehicle})
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
        self.last_query_complete = False
        self.calls += 1
        self.farkas_calls += int(farkas)
        model = self.model
        dual = model.getDualfarkasLinear if farkas else model.getDualsolLinear
        convex = {k: dual(c) for k, c in self.convex.items()}
        links = {ki: dual(c) for ki, c in self.links.items()}
        cuts = [(mask, dual(c)) for mask, c in self.cuts]
        self.last_rewards = {
            k: sorted(((node, links[k, i]) for i, node in enumerate(self.instance.customer_ids)),
                      key=lambda row: -abs(row[1]))[:12]
            for k in self.oracles
        }
        if self.hub:
            self.hub.observe("pricing_farkas" if farkas else "pricing_reduced_cost")
        for oracle in self.oracles.values():
            oracle.dominance = self.policy.dominance
            if self.policy.pricing_search != "reduced_cost":
                oracle.search = self.policy.pricing_search
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
        if self.heuristics is not None and self.policy.pricing_strategy == "heuristic_then_exact":
            started = monotonic()
            for vehicle in self.oracles:
                if added >= self.policy.columns_per_round or monotonic() >= self.deadline:
                    break
                prizes = {
                    node: links[vehicle, i] for i, node in enumerate(self.instance.customer_ids)
                }
                routes = self.heuristics.price(
                    vehicle, prizes, cuts, int(self.phase == "energy" and not farkas),
                    self.policy.pricing_heuristic_starts,
                    min(self.deadline, started + self.policy.pricing_heuristic_seconds),
                )
                before = added
                consider(vehicle, routes)
                self.heuristic_columns += added - before
                self.heuristic_calls += 1
            self.heuristic_seconds += monotonic() - started
        if added:
            return {"result": SCIP_RESULT.SUCCESS}
        if (not farkas and self.heuristics is not None
                and self.integrality_columns < self.policy.integrality_pricing_columns):
            # Completar cobertura de una selección parcial de rutas del LP.
            # Las columnas son físicas; su admisión NO sustituye pricing exacto.
            ordered = sorted(self.columns, key=lambda row: -model.getSolVal(None, row[3]))
            used_vehicles, covered = set(), 0
            for vehicle, mask, _, _ in ordered:
                if vehicle not in used_vehicles and not mask & covered and mask:
                    used_vehicles.add(vehicle)
                    covered |= mask
            for vehicle in self.oracles:
                targets = {
                    node: (10.0 if not covered & (1 << i) else -10.0)
                    for i, node in enumerate(self.instance.customer_ids)
                }
                # Si la cobertura LP parcial ya es completa, explorar una ruta
                # distinta conservando los premios duales del vehículo.
                if covered.bit_count() == len(self.instance.customer_ids):
                    targets = {node: links[vehicle, i]
                               for i, node in enumerate(self.instance.customer_ids)}
                routes = self.heuristics.price(
                    vehicle, targets, [], .1, 1,
                    min(self.deadline, monotonic()+self.policy.pricing_heuristic_seconds),
                )
                for mask, route in routes.items():
                    if self.add(vehicle, mask, route, priced=True):
                        self.integrality_columns += 1
                        added += 1
                        if self.integrality_columns >= self.policy.integrality_pricing_columns:
                            break
                if added:
                    return {"result": SCIP_RESULT.SUCCESS}
        if self.policy.pricing_search == "reduced_cost":
            started = monotonic()
            for vehicle in self.oracles:
                query = ReducedCostOracle(
                    self.instance, vehicle,
                    [links[vehicle, i] for i in range(len(self.instance.customer_ids))],
                    cuts, convex[vehicle], int(self.phase == "energy" and not farkas),
                    model.getParam("numerics/dualfeastol"), self.network,
                    dominance=self.policy.dominance,
                )
                self.exact_queries += 1
                while not query.complete and added < self.policy.columns_per_round:
                    if monotonic() >= self.deadline:
                        self.incomplete = True
                        model.interruptSolve()
                        break
                    consider(vehicle, query.advance())
                    if self.hub and query.expanded % 64 == 0:
                        self.hub.observe("pricing_progress")
                    if added:
                        break
                self.dual_labels += query.expanded
                self.bound_prunes += query.pruned_bound
                self.return_prunes += query.pruned_return
                self.completed_queries += int(query.complete)
                if self.incomplete or added:
                    break
            self.exact_seconds += monotonic() - started
            self.last_query_complete = not self.incomplete and not added
            return {"result": SCIP_RESULT.SUCCESS if added or not self.incomplete else SCIP_RESULT.DIDNOTRUN}
        while added < self.policy.columns_per_round and not all(o.complete for o in self.oracles.values()):
            if monotonic() >= self.deadline:
                self.incomplete = True
                model.interruptSolve()
                return {"result": SCIP_RESULT.SUCCESS if added else SCIP_RESULT.DIDNOTRUN}
            expanded = set()
            started = monotonic()
            for vehicle, oracle in self.oracles.items():
                if id(oracle) in expanded:
                    continue
                expanded.add(id(oracle))
                if not oracle.complete:
                    routes = oracle.advance()
                    for other, same in self.oracles.items():
                        if same is oracle:
                            consider(other, routes)
                    if self.hub and oracle.expanded % 64 == 0:
                        self.hub.observe("pricing_progress")
            self.exact_seconds += monotonic() - started
            if monotonic() >= self.deadline:
                self.incomplete = not all(o.complete for o in self.oracles.values())
                model.interruptSolve()
                return {"result": SCIP_RESULT.SUCCESS if added else SCIP_RESULT.DIDNOTRUN}
            # Devolver pronto columnas: el siguiente dual puede ser muy distinto.
            if added:
                break
        self.last_query_complete = not added and all(o.complete for o in self.oracles.values())
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


def _master_phase(instance, config, policy, oracles, name, deadline, best, log_directory=None,
                  heuristics=None, epoch=0, restricted=False, controller=None):
    started = monotonic()
    model = Model(f"routes_{name}")
    native_changes = _configure(
        model, config, policy, log_directory, f"{name}-{'pool' if restricted else 'exact'}-{epoch:02d}",
        energy_phase=name == "energy",
    )
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
    if policy.route_cuts == "subset_row_triples" and controller is None:
        for triple in islice(combinations(range(n), 3), policy.max_subset_rows):
            mask = sum(1 << i for i in triple)
            cuts.append((mask, model.addCons(quicksum([]) <= 1, modifiable=True)))
    columns = []
    pricer = RoutePricer(instance, oracles, convex, links, cuts, columns, name, deadline, policy,
                         heuristics)
    model.includePricer(pricer, "physical_routes", "Continuous-resource route pricing", delay=True)
    if restricted:
        model.deactivatePricer(pricer)
    seed_accepted = None
    prior_best = best
    if best is not None:
        seed = model.createSol()
        for route in best.routes:
            served = {i for step in route.steps for i in step.delivered_visit_ids}
            mask = sum(1 << i for i, node in enumerate(instance.customer_ids) if node in served)
            pricer.add(route.vehicle_id, mask, route, priced=False)
            model.setSolVal(seed, columns[-1][3], 1)
            for i, node in enumerate(instance.customer_ids):
                model.setSolVal(seed, z[route.vehicle_id, i], int(node in served))
        seed_accepted = bool(model.addSol(seed))
    if heuristics is not None:
        for route in list(heuristics.pool.values())[:policy.pricing_pool_limit]:
            served = {i for step in route.steps for i in step.delivered_visit_ids}
            mask = sum(1 << i for i, node in enumerate(instance.customer_ids) if node in served)
            pricer.add(route.vehicle_id, mask, route, priced=False)
    hub = None
    if controller is not None:
        controller.attach_master(model, f"{name}-{'pool' if restricted else 'priced'}-{epoch}")
        if controller.config.tree_control:
            hub = install_callbacks(
                model, controller, name, deadline, instance, z=z,
                pricer=None if restricted else pricer,
                target_deliveries=len(best.served_visit_ids) if best else None,
            )
    model.setRealParam("limits/time", max(0.001, deadline - monotonic()))
    optimizing = monotonic()
    # optimize() retains Python's GIL: Bedrock threads can otherwise receive
    # their response tens of seconds late despite low provider latency.
    model.optimizeNogil()
    native_seconds = monotonic() - optimizing
    termination = "error" if pricer.error else (
        "pricing_incomplete" if pricer.incomplete else str(model.getStatus())
    )
    if restricted:
        termination = "restricted_pool_heuristic"
    valid_bound = not pricer.incomplete and not restricted and pricer.last_query_complete
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
    phase.warm_start = "submitted" if prior_best is not None else "not_requested"
    if best is prior_best and best is not None:
        phase.incumbent_source = "provided_incumbent"
    stat = {
        "name": name, "columns": len(columns), "subset_row_cuts": len(pricer.cuts),
        "pricing_calls": pricer.calls, "farkas_calls": pricer.farkas_calls,
        "max_columns_added_per_call": pricer.max_columns_added_per_call,
        "pricing_interrupted": pricer.incomplete, "pricing_error": pricer.error,
        "oracle_complete": {k: o.complete for k, o in oracles.items()},
        "labels_expanded": {k: o.expanded for k, o in oracles.items()},
        "branch_nodes": model.getNNodes(), "movement_limit_used": None,
        "native_optimize_seconds": native_seconds,
        "epoch": epoch, "native_parameter_changes": native_changes,
        "heuristic_pricing_calls": pricer.heuristic_calls,
        "heuristic_pricing_columns": pricer.heuristic_columns,
        "heuristic_pricing_seconds": pricer.heuristic_seconds,
        "exact_pricing_seconds": pricer.exact_seconds,
        "dual_pricing_labels": pricer.dual_labels,
        "completion_bound_prunes": pricer.bound_prunes,
        "return_time_prunes": pricer.return_prunes,
        "exact_dual_queries": pricer.exact_queries,
        "completed_dual_queries": pricer.completed_queries,
        "integrality_pricing_columns": pricer.integrality_columns,
        "last_pricing_query_complete": pricer.last_query_complete,
        "callback_control": hub.report() if hub else None,
        "physical_oracles": len({id(o) for o in oracles.values()}),
        "restricted_pool": restricted, "warm_start_accepted": seed_accepted,
        "bound_source": "SCIP_with_exact_pricing_or_analytic" if valid_bound else "analytic",
        "queued_labels": {k: len(o.queue) for k, o in oracles.items()},
    }
    if best is not None and heuristics is not None:
        for route in best.routes:
            heuristics.remember(route)
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
        "chargers": len(instance.charger_ids),
        "nodes": len(instance.nodes), "arcs": len(instance.arcs),
        "energy_relative_gap_target": config.energy_relative_gap,
        "single_tour_certificate": certificate,
        "operations": instance.operations.model_dump(exclude={
            "customer_time_windows", "service_seconds_by_customer", "charging_power_kw_by_station",
        }),
        "applicable_actions": ["subtour_batch_size", "branching", "heuristics",
                               "presolve", "separation", "scip_parameters"] if witness else
        ["initial_routes", "local_search", "stage_allocation", "route_cuts",
         "pricing", "branching", "heuristics", "scip_parameters"],
    }
    construction = HybridRoutes(instance) if witness is None else None
    controller = LLMHead(
        search_config, profile, deadline, config.time_limit_seconds, policy_provider,
        instance=instance,
    )
    if construction is not None and not construction.fast.supported:
        controller.unsupported_settings.update({
            "local_search", "local_search_passes", "ruin_rounds",
        })
    policy = controller.decide("before_search", {"phase": "planning"})
    phases, stats = [], []
    heuristic_trace = []
    relaxation = None
    heuristic_incumbent = witness
    first_full_seconds = monotonic() - started if best and len(best.served_visit_ids) == len(instance.customer_ids) else None
    def record_full_service():
        nonlocal first_full_seconds
        if first_full_seconds is None and best and len(best.served_visit_ids) == len(instance.customer_ids):
            first_full_seconds = monotonic() - started

    if witness is not None:
        phases.append(_phase(
            "deliveries", best, float(len(instance.customer_ids)), "witness_and_cardinality_bound",
            monotonic() - started,
        ))
        best, phase, stat = _tour_solve(
            instance, config, policy, deadline, best, search_config.log_directory, controller,
        )
        phases.append(phase)
        stats.append(stat)
    else:
        construction.policy = policy
        construction.evaluation_seconds = policy.resource_repair_seconds
        def observe_construction(event, state):
            nonlocal first_full_seconds
            if (event == "heuristic_incumbent" and first_full_seconds is None
                    and state.get("deliveries") == len(instance.customer_ids)):
                first_full_seconds = monotonic() - started
            return controller.decide(event, {"phase": controller.current_phase, **state})
        construction.observer = observe_construction
        construction.pool_limit = policy.pricing_pool_limit
        seed_started = monotonic()
        seed_deadline = min(deadline, seed_started + config.time_limit_seconds*policy.seed_time_fraction)
        controller.locked_settings.update({
            "seed_strategy", "seed_starts", "seed_time_fraction",
        })
        seed = construction.seed(policy.seed_strategy, policy.seed_starts, seed_deadline, config.seed)
        if policy.seed_charging and monotonic() < seed_deadline:
            controller.locked_settings.update({"seed_charging", "charging_seed_starts"})
            charged = construction.charging_seed(policy.charging_seed_starts, seed_deadline)
            if charged is not None and (seed is None or (
                len(charged.served_visit_ids), -charged.net_energy_kwh
            ) > (len(seed.served_visit_ids), -seed.net_energy_kwh)):
                seed = charged
        if seed is not None and (best is None or (
            len(seed.served_visit_ids), -seed.net_energy_kwh
        ) > (len(best.served_visit_ids), -best.net_energy_kwh)):
            best = heuristic_incumbent = seed
        record_full_service()
        policy = controller.decide("after_seed", {
            "phase": "planning", "deliveries": len(best.served_visit_ids) if best else 0,
            "energy_kwh": best.net_energy_kwh if best else None,
            "seed_seconds": monotonic() - seed_started,
            "delivery_optimum_proven": first_full_seconds is not None,
            "seed_supported": construction.supported,
            "heuristic_pool_columns": len(construction.pool),
        })
        improvement_deadline = min(
            deadline, monotonic() + config.time_limit_seconds*policy.improvement_time_fraction,
        )
        improved = construction.improve(best, policy, improvement_deadline, config.seed)
        if improved is not best:
            best = heuristic_incumbent = improved
        record_full_service()
        if best is not None and len(best.served_visit_ids) == len(instance.customer_ids):
            policy = controller.decide("first_full_service", {
                "phase": "energy", "deliveries": len(best.served_visit_ids),
                "energy_kwh": best.net_energy_kwh, "delivery_optimum_proven": True,
                "orders": {
                    route.vehicle_id: [i for step in route.steps for i in step.delivered_visit_ids]
                    for route in best.routes
                },
                "hybrid_search": construction.telemetry(),
                "first_full_delivery_seconds": first_full_seconds,
            })
        controller.locked_settings.add("share_vehicle_oracles")
        oracles, shared = {}, {}
        for vehicle in instance.vehicle_ids:
            key = tuple(sorted(instance.chargers_for(vehicle))) if policy.share_vehicle_oracles else vehicle
            if key not in shared:
                shared[key] = RouteOracle(
                    instance, vehicle, search=policy.pricing_search, dominance=policy.dominance,
                    network=construction.network,
                )
            oracles[vehicle] = shared[key]
        for name in ("deliveries", "energy"):
            controller.current_phase = name
            if name == "energy" and best is None:
                break
            if name == "deliveries" and best is not None and len(best.served_visit_ids) == len(instance.customer_ids):
                first_full_seconds = first_full_seconds or monotonic() - started
                phases.append(_phase(
                    name, best, float(len(instance.customer_ids)), "witness_and_cardinality_bound",
                    monotonic() - started,
                ))
                continue
            phase_started = monotonic()
            phase_deadline = (monotonic() + policy.deliveries_time_fraction * max(0, deadline - monotonic())
                              if name == "deliveries" else deadline)
            if name == "deliveries":
                controller.locked_settings.add("deliveries_time_fraction")
            bound = float(len(instance.customer_ids)) if name == "deliveries" else (
                0.0 if all(arc_energy(a, instance.operations) >= 0 for a in instance.arcs)
                else len(instance.vehicle_ids)*(instance.parameters.initial_energy_kwh-instance.parameters.battery_capacity_kwh)
            )
            if name == "energy":
                controller.locked_settings.update({"bound_strategy", "bound_time_fraction"})
                relaxation = energy_relaxation(
                    instance, config, policy,
                    min(phase_deadline, monotonic()+config.time_limit_seconds*policy.bound_time_fraction),
                    complete_service=len(best.served_visit_ids) == len(instance.customer_ids),
                )
                controller.finished_stages.add("bound_relaxation")
                if relaxation["applicable"]:
                    bound = max(bound, relaxation["bound_kwh"])
                if relaxation.get("tour") is not None:
                    repair_deadline = min(phase_deadline, monotonic()+policy.epoch_seconds*.1)
                    candidates = [
                        construction.split_tour(relaxation["tour"], repair_deadline),
                    ]
                    if policy.seed_charging and construction.fast.supported:
                        candidates.append(construction.charging_seed(
                            1, repair_deadline, tours=[relaxation["tour"]],
                        ))
                    for candidate in candidates:
                        if (candidate is not None
                                and len(candidate.served_visit_ids) == len(best.served_visit_ids)
                                and candidate.net_energy_kwh < best.net_energy_kwh):
                            best = heuristic_incumbent = candidate
            epoch, termination, message = 0, "budget_exhausted", ""
            while monotonic() < phase_deadline:
                if best is not None and name == "energy" and abs(best.net_energy_kwh-bound) <= 1e-7:
                    termination = "validated_route_and_relaxation_bound"
                    break
                if name == "energy" and _energy_gap_reached(best, bound, config.energy_relative_gap):
                    termination = "energy_gap_limit"
                    break
                for oracle in shared.values():
                    oracle.search, oracle.dominance = policy.pricing_search, policy.dominance
                construction.pool_limit = policy.pricing_pool_limit
                before = (len(best.served_visit_ids), best.net_energy_kwh) if best else None
                if best is not None and policy.restricted_master_seconds > 0:
                    best, _, pool_stat = _master_phase(
                        instance, config, policy, oracles, name,
                        min(phase_deadline, monotonic()+policy.restricted_master_seconds),
                        best, search_config.log_directory, construction, epoch, restricted=True,
                        controller=controller,
                    )
                    stats.append(pool_stat)
                    record_full_service()
                    if name == "deliveries" and first_full_seconds is not None:
                        termination = "witness_and_cardinality_bound"
                        break
                    if name == "energy" and _energy_gap_reached(best, bound, config.energy_relative_gap):
                        termination = "energy_gap_limit"
                        break
                if monotonic() >= phase_deadline:
                    break
                best, phase, stat = _master_phase(
                    instance, config, policy, oracles, name,
                    min(phase_deadline, monotonic()+policy.epoch_seconds), best,
                    search_config.log_directory, construction, epoch,
                    controller=controller,
                )
                stats.append(stat)
                record_full_service()
                if phase.best_bound is not None:
                    bound = min(bound, phase.best_bound) if name == "deliveries" else max(bound, phase.best_bound)
                termination, message = phase.termination_condition, phase.message
                epoch += 1
                if phase.proven_optimal or phase.status in {"infeasible", "error"}:
                    break
                if name == "energy" and _energy_gap_reached(best, bound, config.energy_relative_gap):
                    termination = "energy_gap_limit"
                    break
                after = (len(best.served_visit_ids), best.net_energy_kwh) if best else None
                if after == before:
                    policy = controller.decide("search_stagnation", {
                        "phase": name, "epoch": epoch, "deliveries": after[0] if after else 0,
                        "energy_kwh": after[1] if after else None,
                        "bound": bound, "columns": stat["columns"],
                        "heuristic_columns": stat["heuristic_pricing_columns"],
                        "exact_pricing_seconds": stat["exact_pricing_seconds"],
                        "heuristic_pricing_seconds": stat["heuristic_pricing_seconds"],
                        "labels_expanded": stat["labels_expanded"],
                        "dual_pricing_labels": stat["dual_pricing_labels"],
                        "exact_dual_queries": stat["exact_dual_queries"],
                        "completed_dual_queries": stat["completed_dual_queries"],
                        "completion_bound_prunes": stat["completion_bound_prunes"],
                        "return_time_prunes": stat["return_time_prunes"],
                        "pricing_interrupted": stat["pricing_interrupted"],
                        "hybrid_search": construction.telemetry(),
                        "first_full_delivery_seconds": first_full_seconds,
                    })
                improved = construction.improve(
                    best, policy, min(phase_deadline, monotonic()+policy.epoch_seconds*policy.improvement_time_fraction),
                    config.seed+epoch,
                )
                if improved is not best:
                    if (name == "energy" and improved is not None and best is not None
                            and len(improved.served_visit_ids) > len(best.served_visit_ids)):
                        # Cambió el cumplimiento condicionado: las cotas de la
                        # fase energética anterior ya no certifican este problema.
                        bound = (
                            0.0 if all(arc_energy(a, instance.operations) >= 0 for a in instance.arcs)
                            else len(instance.vehicle_ids) * (
                                instance.parameters.initial_energy_kwh
                                - instance.parameters.battery_capacity_kwh
                            )
                        )
                        if relaxation is not None:
                            relaxation = {**relaxation, "applicable": False,
                                          "invalidated_by": "increased_deliveries"}
                        phases[0] = _phase(
                            "deliveries", improved, float(len(instance.customer_ids)),
                            "coverage_improved_during_energy", phases[0].runtime_seconds,
                            message="Una heurística posterior aumentó el cumplimiento; cota cardinal.",
                        )
                    best = heuristic_incumbent = improved
                record_full_service()
                if name == "deliveries" and best and len(best.served_visit_ids) == len(instance.customer_ids):
                    first_full_seconds = first_full_seconds or monotonic()-started
                    termination = "witness_and_cardinality_bound"
                    break
            if name == "energy" and relaxation and relaxation["applicable"] and termination == "pricing_incomplete":
                message = "Pricing incompleto; cota válida de la relajación energética sin recursos."
            if termination == "energy_gap_limit":
                message = (
                    f"Gap energético <= {config.energy_relative_gap:.6g} con cota global válida; "
                    "no implica optimalidad energética exacta. Condicionado a las entregas fijadas."
                )
            phase = _phase(name, best, bound, termination, monotonic()-phase_started, message=message)
            phases.append(phase)
            if phase.status in {"infeasible", "error"}:
                break
        heuristic_trace = construction.trace
    controller.close()
    tuning = controller.report()
    from ev_routing.route_policy import _save_decision
    _save_decision(search_config, tuning)
    optimal = len(phases) == 2 and all(p.proven_optimal for p in phases)
    return SolveResult(
        requested_solver=config.solver, used_solver="scip-routes",
        solver_version="SCIP 10.0.0 / PySCIPOpt 6.0.0",
        phases=phases, solution=best, lexicographic_optimal=optimal,
        status="optimal" if optimal else "feasible" if best else phases[-1].status,
        solution_source=(
            "initial_solution" if best is initial_solution else "heuristic" if best is heuristic_incumbent
            else "solver"
        ) if best else None,
        runtime_seconds=monotonic() - started,
        message="Formulación por rutas sin H. El certificado se refiere al grafo y energía de entrada.",
        search={
            "engine": "scip_routes_without_h", "movement_limit_used": None,
            "single_tour_certificate": certificate, "phases": stats,
            "controller": tuning, "configuration": search_config.model_dump(),
            "first_full_delivery_seconds": first_full_seconds,
            "heuristic_progress": heuristic_trace,
            "energy_relaxation": relaxation,
            "hybrid_search": construction.telemetry() if witness is None else None,
        },
    )
