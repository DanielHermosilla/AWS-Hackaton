"""Cotas energéticas: quitar batería y flota amplía el conjunto factible."""

from __future__ import annotations

from time import monotonic

import networkx as nx
import numpy as np
from pyscipopt import Model, quicksum
from scipy.optimize import linear_sum_assignment
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from ev_routing.operations import arc_energy
from ev_routing.scip_tuning import apply_parameters


def energy_relaxation(instance, config, policy, deadline, *, complete_service):
    """Toda flota completa induce un tour no más caro en la clausura de energía.

    Concatenar retornos en el depósito y atajar entre eventos usando caminos
    mínimos relaja batería, recargas, jornada y vehículos. No se afirma que el
    tour relajado sea una ruta física factible. No admite regeneración ni un
    objetivo con clientes opcionales: para esos casos se conserva la cota previa.
    """
    started = monotonic()
    report = {"applicable": False, "bound_kwh": 0.0, "source": "nonnegative_energy",
              "runtime_seconds": 0.0, "tour": None}
    if (not complete_service or policy.bound_strategy == "none" or
            any(n.node_type == "junction" for n in instance.nodes) or
            any(arc_energy(a, instance.operations) < 0 for a in instance.arcs) or
            len(instance.customer_ids) < 2 or monotonic() >= deadline):
        return report
    ids = {n.node_id: i for i, n in enumerate(instance.nodes)}
    required = [instance.depot_id, *instance.customer_ids]
    graph = csr_matrix((
        [arc_energy(a, instance.operations) for a in instance.arcs],
        ([ids[a.from_node_id] for a in instance.arcs],
         [ids[a.to_node_id] for a in instance.arcs]),
    ), shape=(len(ids), len(ids)))
    distances = np.empty((len(required), len(required)))
    targets = [ids[n] for n in required]
    for i, node in enumerate(required):
        if monotonic() >= deadline:
            report["runtime_seconds"] = monotonic()-started
            return report
        distances[i] = dijkstra(graph, directed=True, indices=ids[node])[targets]
    if not np.isfinite(distances).all():
        report["runtime_seconds"] = monotonic()-started
        return report
    # Error de acumulación conservador para caminos simples no negativos.
    maximum = max((arc_energy(a, instance.operations) for a in instance.arcs), default=0)
    guard = 4*np.finfo(float).eps*max(1, len(ids)**2)*max(1, maximum)
    costs = np.maximum(0, distances-guard)
    np.fill_diagonal(costs, np.inf)
    rows, cols = linear_sum_assignment(costs)
    bound = max(0.0, float(costs[rows, cols].sum())-len(required)*guard)
    report.update(applicable=True, bound_kwh=bound, source="assignment_relaxation",
                  rounding_guard_per_arc_kwh=guard)
    if policy.bound_strategy == "assignment" or monotonic() >= deadline:
        report["runtime_seconds"] = monotonic()-started
        return report
    model = Model("energy_relaxation_without_resources")
    model.hideOutput(not config.tee)
    model.setIntParam("parallel/maxnthreads", config.threads)
    model.setIntParam("lp/threads", config.threads)
    model.setIntParam("randomization/randomseedshift", config.seed)
    changes = apply_parameters(model, policy, single_tour=True)
    n = len(required)
    arcs = {(i, j): model.addVar(vtype="B", obj=float(costs[i, j]))
            for i in range(n) for j in range(n) if i != j}
    for i in range(n):
        model.addCons(quicksum(arcs[i, j] for j in range(n) if i != j) == 1)
        model.addCons(quicksum(arcs[j, i] for j in range(n) if i != j) == 1)
    rounds, cuts = 0, 0
    try:
        while monotonic() < deadline:
            model.setRealParam("limits/time", max(.001, deadline-monotonic()))
            model.optimize()
            rounds += 1
            native = model.getDualbound()
            if abs(native) < model.infinity():
                bound = max(bound, native-n*guard)
            report["termination"] = str(model.getStatus())
            if not model.getNSols():
                break
            sol = model.getBestSol()
            successor = {i: j for (i, j), var in arcs.items() if model.getSolVal(sol, var) > .5}
            components = list(nx.strongly_connected_components(nx.DiGraph(successor.items())))
            if len(components) == 1:
                walk = [0]
                while successor[walk[-1]] != 0:
                    walk.append(successor[walk[-1]])
                report["tour"] = [required[i] for i in [*walk, 0]]
                break
            model.freeTransform()
            for component in components[:policy.subtour_batch_size]:
                model.addCons(quicksum(var for (i, j), var in arcs.items()
                                       if i in component and j in component) <= len(component)-1)
                cuts += 1
    finally:
        model.freeProb()
    report.update(bound_kwh=bound, source="scip_tour_relaxation", rounds=rounds, cuts=cuts,
                  runtime_seconds=monotonic()-started, native_parameter_changes=changes)
    return report
