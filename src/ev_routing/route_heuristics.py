"""Columnas factibles rápidas; nunca sustituyen la prueba del pricing exacto."""

from __future__ import annotations

from math import inf
from random import Random
from time import monotonic

import networkx as nx
import numpy as np

from ev_routing.operations import arc_energy
from ev_routing.route_resources import assemble_solution, route_from_walk
from ev_routing.validation import validate_solution


class InsertionRoutes:
    """Inserción sin recargas para el caso no negativo y sin restricciones temporales."""

    def __init__(self, instance):
        self.instance = instance
        self.costs = {(a.from_node_id, a.to_node_id): arc_energy(a, instance.operations)
                      for a in instance.arcs}
        self.depot = instance.depot_id
        self.costs[self.depot, self.depot] = 0.0
        final = max(instance.parameters.reserve_kwh,
                    (instance.operations.final_reserve_soc or 0) *
                    instance.parameters.battery_capacity_kwh)
        self.usable = instance.parameters.initial_energy_kwh - final
        self.supported = (
            not instance.operations.timing_enabled and self.usable >= 0
            and all(e >= 0 for e in self.costs.values())
        )
        self.pool = {}
        self.pool_limit = 2000
        self.trace = []

    def cost(self, walk):
        return sum(self.costs.get((a, b), inf) for a, b in zip(walk, walk[1:]))

    def options(self, walks, customer):
        choices = []
        for k, walk in enumerate(walks):
            total = self.cost(walk)
            for pos, (a, b) in enumerate(zip(walk, walk[1:]), 1):
                delta = (self.costs.get((a, customer), inf) +
                         self.costs.get((customer, b), inf) - self.costs[a, b])
                if total + delta <= self.usable:
                    choices.append((delta, k, pos))
        return sorted(choices)

    def route(self, vehicle, walk):
        if walk == [self.depot, self.depot]:
            walk = [self.depot]
        result = route_from_walk(
            self.instance, vehicle, walk, range(1, len(walk) - 1), np.zeros(len(walk)),
        )
        return result

    def remember(self, route):
        served = frozenset(i for s in route.steps for i in s.delivered_visit_ids)
        key = route.vehicle_id, served
        if key not in self.pool or route.net_energy_kwh < self.pool[key].net_energy_kwh:
            self.pool[key] = route
        while len(self.pool) > self.pool_limit:
            self.pool.pop(next(iter(self.pool)))

    def solution(self, walks):
        result = assemble_solution(self.instance, [
            self.route(k, walk) for k, walk in zip(self.instance.vehicle_ids, walks)
        ])
        if validate_solution(self.instance, result, enforce_movement_limit=False).feasible:
            for route in result.routes:
                self.remember(route)
            return result
        return None

    def seed(self, strategy, starts, deadline, seed=0):
        if not self.supported or strategy == "none":
            return None
        best = None
        order = sorted(self.instance.customer_ids)
        Random(seed).shuffle(order)
        for attempt in range(starts):
            if monotonic() >= deadline:
                break
            walks = [[self.depot, self.depot] for _ in self.instance.vehicle_ids]
            pending = set(order)
            if attempt and order:
                customer = order[(attempt - 1) % len(order)]
                options = self.options(walks, customer)
                if options:
                    _, k, pos = options[0]
                    walks[k].insert(pos, customer)
                    pending.remove(customer)
            while pending and monotonic() < deadline:
                choices = []
                for customer in sorted(pending):
                    options = self.options(walks, customer)
                    if not options:
                        continue
                    first = options[0]
                    regret = (options[1][0] - first[0]) if len(options) > 1 else inf
                    score = -regret if strategy == "regret_insertion" else first[0]
                    choices.append((score, first, customer))
                if not choices:
                    break
                _, (_, k, pos), customer = min(choices)
                walks[k].insert(pos, customer)
                pending.remove(customer)
            result = self.solution(walks)
            if result is not None:
                if best is None or (len(result.served_visit_ids), -result.net_energy_kwh) > (
                    len(best.served_visit_ids), -best.net_energy_kwh,
                ):
                    best = result
                    self.trace.append({"event": "seed", "attempt": attempt,
                                       "deliveries": len(result.served_visit_ids),
                                       "energy_kwh": result.net_energy_kwh})
        return best

    def _repair(self, walks, pending, strategy, deadline, random=None):
        while pending and monotonic() < deadline:
            choices = []
            for customer in sorted(pending):
                options = self.options(walks, customer)
                if not options:
                    continue
                first = options[0]
                regret = options[1][0] - first[0] if len(options) > 1 else inf
                score = -regret if strategy == "regret_insertion" else first[0]
                choices.append((score, first, customer))
            if not choices:
                break
            choices.sort()
            selected = random.randrange(min(3, len(choices))) if random else 0
            _, (_, vehicle, position), customer = choices[selected]
            walks[vehicle].insert(position, customer)
            pending.remove(customer)

    def _descent(self, walks, operators, passes, deadline):
        """Vecindades dirigidas: recalcular costes también al invertir segmentos."""
        for _ in range(passes):
            changed = False
            for operator in operators:
                if monotonic() >= deadline:
                    return walks
                totals = [self.cost(w) for w in walks]
                if operator == "two_opt":
                    for k, walk in enumerate(walks):
                        for i in range(1, len(walk) - 2):
                            if monotonic() >= deadline:
                                return walks
                            for j in range(i + 1, len(walk) - 1):
                                candidate = walk[:i] + walk[i:j+1][::-1] + walk[j+1:]
                                cost = self.cost(candidate)
                                if cost < totals[k] - 1e-10 and cost <= self.usable:
                                    walks[k] = walk = candidate
                                    totals[k] = cost
                                    changed = True
                elif operator == "relocate":
                    for k in range(len(walks)):
                        for i in range(len(walks[k]) - 2, 0, -1):
                            if monotonic() >= deadline:
                                return walks
                            customer = walks[k][i]
                            shortened = walks[k][:i] + walks[k][i+1:]
                            saving = totals[k] - self.cost(shortened)
                            for other in range(len(walks)):
                                base = shortened if other == k else walks[other]
                                options = self.options([base], customer)
                                if options and options[0][0] < saving - 1e-10:
                                    _, _, pos = options[0]
                                    candidate = base[:pos] + [customer] + base[pos:]
                                    walks[k] = shortened
                                    walks[other] = candidate
                                    totals = [self.cost(w) for w in walks]
                                    changed = True
                                    break
                elif operator == "swap":
                    for k in range(len(walks)):
                        for other in range(k+1, len(walks)):
                            for i in range(1, len(walks[k])-1):
                                if monotonic() >= deadline:
                                    return walks
                                for j in range(1, len(walks[other])-1):
                                    left, right = walks[k].copy(), walks[other].copy()
                                    left[i], right[j] = right[j], left[i]
                                    a, b = self.cost(left), self.cost(right)
                                    if max(a, b) <= self.usable and a+b < totals[k]+totals[other]-1e-10:
                                        walks[k], walks[other] = left, right
                                        totals[k], totals[other] = a, b
                                        changed = True
            if not changed:
                break
        return walks

    def improve(self, best, policy, deadline, seed=0):
        """Ruin/repair y búsqueda local; conserva siempre el mejor testigo validado."""
        if best is None or not self.supported or any(
            s.charged_to_battery_kwh > 0 for r in best.routes for s in r.steps
        ):
            return best
        # Las vecindades rápidas solo operan sobre paradas con entrega y depósito.
        walks = []
        for route in best.routes:
            walk = [s.node_id for s in route.steps]
            if any(s.node_id != self.depot and not s.delivered_visit_ids for s in route.steps):
                return best
            walks.append(walk if len(walk) > 1 else [self.depot, self.depot])
        rng = Random(seed)
        for attempt in range(policy.ruin_rounds + 1):
            if monotonic() >= deadline:
                break
            candidate = [w.copy() for w in walks]
            removed = set(best.unserved_visit_ids)
            if attempt:
                served = sorted(best.served_visit_ids)
                removed.update(rng.sample(
                    served, min(len(served), max(1, int(len(served)*policy.ruin_fraction))),
                ))
                candidate = [[n for n in w if n not in removed] for w in candidate]
                self._repair(candidate, removed, policy.seed_strategy, deadline,
                             rng if attempt % 3 == 0 else None)
            candidate = self._descent(candidate, policy.local_search, policy.local_search_passes, deadline)
            result = self.solution(candidate)
            if result is not None and (len(result.served_visit_ids), -result.net_energy_kwh) > (
                len(best.served_visit_ids), -best.net_energy_kwh
            ):
                best, walks = result, candidate
                self.trace.append({"event": "local_improvement", "attempt": attempt,
                                   "deliveries": len(best.served_visit_ids),
                                   "energy_kwh": best.net_energy_kwh})
        return best

    def split_tour(self, tour, deadline):
        """Partición óptima de un orden fijo entre los vehículos, sin recargas."""
        if not self.supported:
            return None
        order = tour[1:-1]
        best = None
        for rotation in range(len(order)):
            if monotonic() >= deadline:
                break
            sequence = order[rotation:]+order[:rotation]
            n, fleet = len(sequence), len(self.instance.vehicle_ids)
            costs = {}
            for i in range(n):
                for j in range(i+1, n+1):
                    walk = [self.depot, *sequence[i:j], self.depot]
                    value = self.cost(walk)
                    if value <= self.usable:
                        costs[i, j] = value
            dp = {(0, 0): (0.0, [])}
            for k in range(1, fleet+1):
                for j in range(n+1):
                    choices = [
                        (previous[0]+costs[i, j], [*previous[1], (i, j)])
                        for i in range(j) if (i, j) in costs
                        and (previous := dp.get((k-1, i))) is not None
                    ]
                    if (k-1, j) in dp:
                        value, segments = dp[k-1, j]
                        choices.append((value, [*segments, (j, j)]))
                    if choices:
                        dp[k, j] = min(choices, key=lambda x: x[0])
            if (fleet, n) in dp:
                value, segments = dp[fleet, n]
                if best is None or value < best.net_energy_kwh:
                    result = self.solution([
                        [self.depot, *sequence[i:j], self.depot] for i, j in segments
                    ])
                    if result is not None:
                        best = result
        return best

    def charging_seed(self, starts, deadline, *, tours=None):
        """Tours con una recarga parcial opcional; solo genera incumbentes.

        Esta vecindad no limita el maestro ni su pricing exacto: los recorridos
        con más recargas y revisitas permanecen en el oráculo físico.
        """
        if not self.supported:
            return None
        nodes = [self.depot, *sorted(self.instance.customer_ids)]
        graph = nx.DiGraph()
        graph.add_nodes_from(nodes)
        graph.add_weighted_edges_from(
            (i, j, value) for (i, j), value in self.costs.items()
            if i != j and i in graph and j in graph
        )
        if graph.number_of_edges() != len(nodes)*(len(nodes)-1) or len(nodes) < 2:
            return None
        params = self.instance.parameters
        final_reserve = max(params.reserve_kwh,
                            (self.instance.operations.final_reserve_soc or 0)*params.battery_capacity_kwh)
        best = None
        for source in (tours if tours is not None else nodes[:starts]):
            if monotonic() >= deadline:
                break
            if tours is not None:
                walk = source
            else:
                cycle = nx.approximation.greedy_tsp(graph, source=source)[:-1]
                index = cycle.index(self.depot)
                walk = cycle[index:] + cycle[:index] + [self.depot]
            total = self.cost(walk)
            prefix = 0.0
            for position, (a, b) in enumerate(zip(walk, walk[1:]), 1):
                if monotonic() >= deadline:
                    break
                for vehicle in self.instance.vehicle_ids:
                    for station in sorted(self.instance.chargers_for(vehicle)):
                        to_station = self.costs.get((a, station), inf)
                        from_station = self.costs.get((station, b), inf)
                        before = prefix + to_station
                        after = total-prefix-self.costs[a, b]+from_station
                        if (before > params.initial_energy_kwh-params.reserve_kwh or
                                after > params.battery_capacity_kwh-final_reserve):
                            continue
                        if best is not None and before+after >= best.net_energy_kwh:
                            continue
                        extended = walk[:position]+[station]+walk[position:]
                        charges = np.zeros(len(extended))
                        charges[position] = max(0, before+after+final_reserve-params.initial_energy_kwh)
                        route = route_from_walk(
                            self.instance, vehicle, extended,
                            [i for i, node in enumerate(extended) if node in self.instance.customer_ids],
                            charges,
                        )
                        routes = [
                            route if k == vehicle else self.route(k, [self.depot])
                            for k in self.instance.vehicle_ids
                        ]
                        result = assemble_solution(self.instance, routes)
                        if validate_solution(self.instance, result, enforce_movement_limit=False).feasible:
                            for r in routes:
                                self.remember(r)
                            if best is None or result.net_energy_kwh < best.net_energy_kwh:
                                best = result
                prefix += self.costs[a, b]
        if best is not None:
            self.trace.append({"event": "charging_seed", "deliveries": len(best.served_visit_ids),
                               "energy_kwh": best.net_energy_kwh})
        return best

    def price(self, vehicle, prizes, cuts, energy_weight, starts, deadline):
        """Inserciones guiadas por duales; los cortes de ternas incluyen su coeficiente."""
        if not self.supported:
            return {}
        bits = {node: 1 << i for i, node in enumerate(self.instance.customer_ids)}
        ordered = sorted(bits, key=lambda c: (-prizes[c], c))
        routes = {}
        for attempt in range(starts):
            if monotonic() >= deadline:
                break
            walk, mask = [self.depot, self.depot], 0
            pending = set(ordered)
            if attempt and ordered:
                customer = ordered[(attempt - 1) % len(ordered)]
                choices = self.options([walk], customer)
                if choices:
                    walk.insert(choices[0][2], customer)
                    mask |= bits[customer]
                    pending.remove(customer)
            while pending and monotonic() < deadline:
                choices = []
                for customer in sorted(pending):
                    options = self.options([walk], customer)
                    if not options:
                        continue
                    delta, _, pos = options[0]
                    next_mask = mask | bits[customer]
                    gain = prizes[customer] - energy_weight * delta + sum(
                        dual * (((next_mask & subset).bit_count() // 2) -
                                ((mask & subset).bit_count() // 2))
                        for subset, dual in cuts
                    )
                    if gain > 0:
                        choices.append((-gain, delta, customer, pos))
                if not choices:
                    break
                _, _, customer, pos = min(choices)
                walk.insert(pos, customer)
                mask |= bits[customer]
                pending.remove(customer)
            route = self.route(vehicle, walk)
            self.remember(route)
            if mask not in routes or route.net_energy_kwh < routes[mask].net_energy_kwh:
                routes[mask] = route
        return routes
