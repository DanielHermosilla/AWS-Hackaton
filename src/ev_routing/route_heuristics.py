"""Columnas factibles rápidas; nunca sustituyen la prueba del pricing exacto."""

from __future__ import annotations

from math import inf
from random import Random
from time import monotonic

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
        return route_from_walk(
            self.instance, vehicle, walk, range(1, len(walk) - 1), np.zeros(len(walk)),
        )

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
            result = assemble_solution(self.instance, [
                self.route(k, walk) for k, walk in zip(self.instance.vehicle_ids, walks)
            ])
            if validate_solution(self.instance, result, enforce_movement_limit=False).feasible:
                if best is None or (len(result.served_visit_ids), -result.net_energy_kwh) > (
                    len(best.served_visit_ids), -best.net_energy_kwh,
                ):
                    best = result
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
            if mask not in routes or route.net_energy_kwh < routes[mask].net_energy_kwh:
                routes[mask] = route
        return routes
