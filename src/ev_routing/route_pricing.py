"""Pricing por coste reducido y búsqueda física de secuencias sobre nodos de pricing.

Las colas priorizan; solo las cotas conservadoras de ReducedCostOracle podan.
Cada consulta dual usa su propio oráculo: una poda nunca se reutiliza con otro dual.
"""

from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
from itertools import count
from math import inf

import networkx as nx
import numpy as np

from ev_routing.operations import arc_energy, arc_key, travel_seconds
from ev_routing.route_resources import RouteOracle


class LabelQueue:
    def __init__(self, priority):
        self.priority, self.serial, self.heap = priority, count(), []

    def append(self, label):
        heappush(self.heap, (self.priority(label), next(self.serial), label))

    def popleft(self):
        return heappop(self.heap)[2]

    pop = popleft

    def __len__(self):
        return len(self.heap)


class PricingNetwork:
    """Potenciales sobre el multigrafo recibido; no reemplaza sus alternativas."""

    def __init__(self, instance):
        self.instance = instance
        self.outgoing = defaultdict(list)
        self.arc_lookup = {}
        self.graph = nx.DiGraph()
        self.graph.add_nodes_from(n.node_id for n in instance.nodes)
        self.nonnegative = all(arc_energy(a, instance.operations) >= 0 for a in instance.arcs)
        for arc in instance.arcs:
            self.outgoing[arc.from_node_id].append(arc)
            self.arc_lookup[arc_key(arc)] = arc
            # Solo para orden heurístico en el caso regenerativo. No es una
            # transformación física ni una cota energética para ese caso.
            energy = max(0.0, arc_energy(arc, instance.operations))
            time = travel_seconds(arc, instance.operations) if instance.operations.timing_enabled else 0
            a, b = arc.from_node_id, arc.to_node_id
            previous = self.graph.get_edge_data(a, b, {})
            self.graph.add_edge(a, b, energy=min(energy, previous.get("energy", inf)),
                                time=min(time, previous.get("time", inf)))
        self.reverse = self.graph.reverse(copy=False)
        self.cache = {}

    def distances(self, target, weight="energy"):
        key = target, weight
        if key not in self.cache:
            self.cache[key] = nx.single_source_dijkstra_path_length(
                self.reverse, target, weight=weight,
            )
        return self.cache[key]


class SequenceOracle(RouteOracle):
    """Repara una secuencia de entregas sin fijar calles, estaciones ni recargas."""

    def __init__(self, instance, vehicle, sequence, network, *, path_order="energy"):
        super().__init__(instance, vehicle, network=network)
        self.sequence, self.network = tuple(sequence), network
        self.path_order = path_order
        self.target_mask = sum(self.bits[i] for i in sequence)
        initial = self.queue.popleft()
        self.queue = LabelQueue(self.priority)
        self.queue.append(initial)

    def priority(self, label):
        done = label.mask.bit_count()
        target = self.sequence[done] if done < len(self.sequence) else self.instance.depot_id
        weight = "time" if self.timed and self.path_order == "time" else "energy"
        remaining = self.network.distances(target, weight).get(label.walk[-1], inf)
        spent = (float(label.resources.points[:, 1].min()) if weight == "time" else
                 float((label.resources.points[:, 2] - label.resources.points[:, 0]).min()))
        return -done, spent + remaining

    def _service(self, label):
        target = (self.sequence[label.mask.bit_count()]
                  if label.mask.bit_count() < len(self.sequence) else None)
        for mask, services, resources in super()._service(label):
            if mask == label.mask or label.walk[-1] == target:
                yield mask, services, resources


class ReducedCostOracle(RouteOracle):
    """Consulta exacta con cota optimista de continuaciones y duales fijos.

    Se conserva servicio único, recarga continua y revisitas. No se usa ng-route
    que cobre repetidamente un premio dual ni un límite de movimientos.
    """

    def __init__(self, instance, vehicle, rewards, cuts, convex_dual, energy_weight,
                 tolerance, network, *, dominance="convex"):
        super().__init__(instance, vehicle, dominance=dominance, network=network)
        self.rewards = np.asarray(rewards, dtype=float)
        self.cuts, self.convex_dual, self.energy_weight = cuts, convex_dual, energy_weight
        self.tolerance, self.network = tolerance, network
        self.pruned_bound = self.pruned_return = 0
        self.return_energy = network.distances(instance.depot_id)
        self.return_time = network.distances(instance.depot_id, "time") if self.timed else {}
        self.mask_cost = {}
        initial = self.queue.popleft()
        self.queue = LabelQueue(self.lower_bound)
        self.queue.append(initial)

    def lower_bound(self, label):
        node, params = label.walk[-1], self.instance.parameters
        if node not in self.return_energy:
            return inf
        if label.mask not in self.mask_cost:
            reward = sum(value if label.mask & (1 << i) else max(0, value)
                         for i, value in enumerate(self.rewards))
            reward += sum(
                value * ((subset.bit_count() // 2) if value > 0
                         else ((label.mask & subset).bit_count() // 2))
                for subset, value in self.cuts
            )
            self.mask_cost[label.mask] = -self.convex_dual - reward
        energy = 0.0
        if self.energy_weight:
            points = label.resources.points
            if self.network.nonnegative:
                energy = (params.initial_energy_kwh
                          + float((points[:, 2] - points[:, 0]).min())
                          + self.return_energy.get(node, inf))
            else:
                # Q no disminuye y b_final <= B, incluso en ciclos regenerativos.
                energy = (params.initial_energy_kwh + float(points[:, 2].min())
                          - params.battery_capacity_kwh)
        bound = self.mask_cost[label.mask] + self.energy_weight * energy
        # Margen conservador SOLO de cota numérica; no relaja la física.
        scale = 1 + abs(energy) + abs(self.convex_dual) + sum(abs(self.rewards))
        scale += sum(abs(value) * subset.bit_count() for subset, value in self.cuts)
        return bound - 1e-9 * scale

    def _insert(self, label):
        node = label.walk[-1]
        if self.timed and (
            label.resources.points[:, 1].min() + self.return_time.get(node, inf)
            > self.instance.operations.max_route_seconds + 1e-9
        ):
            self.pruned_return += 1
            return
        if self.lower_bound(label) >= -self.tolerance:
            self.pruned_bound += 1
            return
        super()._insert(label)
