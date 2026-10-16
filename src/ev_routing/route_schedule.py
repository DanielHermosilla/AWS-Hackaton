"""Reparación primal rápida: caminos candidatos y recarga continua mediante LP.

Solo propone rutas. Un fracaso no prueba infactibilidad y no afecta al pricing
exacto. El LP prueba la rama sin saturación; el oráculo general conserva el resto.
"""

from __future__ import annotations

from math import inf
from time import monotonic

import networkx as nx
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from ev_routing.operations import arc_energy, charge_seconds, travel_seconds
from ev_routing.route_resources import assemble_solution, route_from_walk
from ev_routing.validation import validate_solution


class FixedPathRepair:
    def __init__(self, instance, network):
        self.instance, self.network = instance, network
        self.paths = {}
        self.supported = all(
            arc_energy(a, instance.operations) >= 0
            for a in instance.arcs
        )

    def path(self, source, target, weight):
        key = source, target, weight
        if key not in self.paths:
            try:
                nodes = nx.shortest_path(self.network.graph, source, target, weight=weight)
            except nx.NetworkXNoPath:
                self.paths[key] = None
            else:
                arcs = []
                for a, b in zip(nodes, nodes[1:]):
                    arcs.append(min(
                        (arc for arc in self.network.outgoing[a] if arc.to_node_id == b),
                        key=lambda arc: (
                            travel_seconds(arc, self.instance.operations) if weight == "time"
                            else arc_energy(arc, self.instance.operations),
                            arc_energy(arc, self.instance.operations),
                        ),
                    ))
                self.paths[key] = arcs
        return self.paths[key]

    def route(self, vehicle, sequence, deadline, path_order="energy"):
        if not self.supported or vehicle not in self.instance.vehicle_ids:
            return None
        modes = [path_order]
        if self.instance.operations.timing_enabled:
            modes += [mode for mode in ("energy", "time") if mode != path_order]
        for mode in modes:
            if monotonic() >= deadline:
                break
            walk, arcs, services = [self.instance.depot_id], [], []
            for target in [*sequence, self.instance.depot_id]:
                path = self.path(walk[-1], target, mode)
                if path is None:
                    break
                arcs += path
                walk += [a.to_node_id for a in path]
                if target != self.instance.depot_id:
                    services.append(len(walk) - 1)
            else:
                candidate = self._schedule(vehicle, walk, arcs, services, deadline)
                if candidate is not None:
                    return candidate
        return None

    def _schedule(self, vehicle, walk, arcs, services, deadline):
        instance, params, ops = self.instance, self.instance.parameters, self.instance.operations
        compatible = set(instance.chargers_for(vehicle))
        positions = [i for i, node in enumerate(walk[:-1]) if node in compatible]
        q_index = {position: j for j, position in enumerate(positions)}
        timed, nq, size = ops.timing_enabled, len(positions), len(walk)
        charges = np.zeros(size)
        if nq:
            # La batería en j es b_ini - E_prefijo + suma(q_anteriores).
            # Los límites del perfil conservan los déficits dentro de cada arco.
            variables = nq + (size if timed else 0)
            rows, columns, values, rhs = [], [], [], []
            def upper(coefficients, bound):
                row = len(rhs)
                for column, value in coefficients:
                    rows.append(row)
                    columns.append(column)
                    values.append(value)
                rhs.append(bound)
            prefix, available = 0.0, []
            for i, arc in enumerate(arcs):
                if i in q_index:
                    available.append(q_index[i])
                energy = arc_energy(arc, ops)
                required = (arc.battery_profile.minimum_departure_kwh if arc.battery_profile
                            else params.reserve_kwh + energy)
                upper([(j, -1) for j in available], params.initial_energy_kwh - prefix - required)
                maximum_departure = min(
                    params.battery_capacity_kwh,
                    arc.battery_profile.maximum_arrival_kwh + energy
                    if arc.battery_profile else params.battery_capacity_kwh,
                )
                upper([(j, 1) for j in available], maximum_departure - params.initial_energy_kwh + prefix)
                prefix += energy
                if timed:
                    coefficients = [(nq+i, 1), (nq+i+1, -1)]
                    if i in q_index:
                        coefficients.append((q_index[i], charge_seconds(1, walk[i], ops)))
                    service = ops.service_duration(walk[i]) if i in services else 0
                    upper(coefficients, -travel_seconds(arc, ops) - service)
            reserve = max(params.reserve_kwh, (ops.final_reserve_soc or 0) * params.battery_capacity_kwh)
            upper([(j, -1) for j in range(nq)], params.initial_energy_kwh - prefix - reserve)
            bounds = [(0, params.battery_capacity_kwh)] * nq
            if timed:
                horizon = ops.max_route_seconds
                bounds += [(0, horizon)] * size
                bounds[nq] = (0, 0)
                if ops.use_customer_time_windows:
                    for i in services:
                        window = ops.customer_time_windows.get(walk[i])
                        if window:
                            lower = window.open_seconds
                            upper_time = min(window.close_seconds - ops.service_duration(walk[i]),
                                             horizon if horizon is not None else inf)
                            if lower > upper_time:
                                return None
                            bounds[nq+i] = (lower, upper_time)
            if monotonic() >= deadline:
                return None
            objective = np.zeros(variables)
            objective[:nq] = 1
            matrix = coo_matrix((values, (rows, columns)), shape=(len(rhs), variables)).tocsr()
            result = linprog(
                objective, A_ub=matrix, b_ub=np.asarray(rhs), bounds=bounds, method="highs",
                options={"time_limit": max(.001, deadline - monotonic())},
            )
            if not result.success:
                return None
            for position, j in q_index.items():
                charges[position] = max(0.0, result.x[j])
        route = route_from_walk(
            instance, vehicle, walk, services, charges,
            arc_ids=[a.arc_id for a in arcs], arc_lookup=self.network.arc_lookup,
        )
        # Se comprueba la ruta aislada con el mismo checker físico independiente.
        # Solo se omite la exigencia de presentar aquí las demás rutas de flota.
        solution = assemble_solution(instance, [route])
        report = validate_solution(instance, solution, enforce_movement_limit=False)
        if any(not passed for name, passed in report.checks.items() if name != "fleet"):
            return None
        return solution.routes[0]
