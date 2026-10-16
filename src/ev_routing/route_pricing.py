"""Pricing por coste reducido y búsqueda física de secuencias sobre nodos de pricing.

Las colas priorizan; solo las cotas conservadoras de ReducedCostOracle podan.
Cada consulta dual usa su propio oráculo: una poda nunca se reutiliza con otro dual.
"""

from __future__ import annotations

from bisect import bisect_left
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
        self.escape_cache = {}

    def distances(self, target, weight="energy"):
        key = target, weight
        if key not in self.cache:
            self.cache[key] = nx.single_source_dijkstra_path_length(
                self.reverse, target, weight=weight,
            )
        return self.cache[key]

    def escape_energy(self, vehicle):
        """Cota hasta la próxima carga o el retorno; no fija caminos ni estaciones."""
        stations = tuple(sorted(self.instance.chargers_for(vehicle)))
        if stations not in self.escape_cache:
            targets = (*stations, self.instance.depot_id)
            self.escape_cache[stations] = {
                node: min(self.distances(target).get(node, inf) for target in targets)
                for node in self.graph
            }
        return self.escape_cache[stations]

    def sequence_time_possible(self, sequence):
        """Calendario optimista sin batería/recarga: rechazo necesario, no certificado."""
        ops, node, time = self.instance.operations, self.instance.depot_id, 0.0
        if not ops.timing_enabled:
            return True
        for target in sequence:
            time += self.distances(target, "time").get(node, inf)
            window = ops.customer_time_windows.get(target) if ops.use_customer_time_windows else None
            time = max(time, window.open_seconds if window else 0) + ops.service_duration(target)
            if window and time > window.close_seconds + 1e-8:
                return False
            node = target
        return (time + self.distances(self.instance.depot_id, "time").get(node, inf)
                <= (ops.max_route_seconds if ops.max_route_seconds is not None else inf) + 1e-8)


class SequenceOracle(RouteOracle):
    """Repara una secuencia de entregas sin fijar calles, estaciones ni recargas."""

    def __init__(self, instance, vehicle, sequence, network, *, path_order="energy"):
        super().__init__(instance, vehicle, network=network)
        self.sequence, self.network = tuple(sequence), network
        self.path_order = path_order
        self.target_mask = sum(self.bits[i] for i in sequence)
        self.pruned_time = self.pruned_energy = 0
        self.escape_energy = network.escape_energy(vehicle) if network.nonnegative else {}
        # Última llegada posible a cada servicio bajo tiempos mínimos sin
        # batería ni recarga. Es una relajación: solo descarta imposibilidades.
        self.latest = [inf] * len(self.sequence)
        if self.timed:
            ops = instance.operations
            following, latest = instance.depot_id, ops.max_route_seconds
            for i in reversed(range(len(self.sequence))):
                node = self.sequence[i]
                window = ops.customer_time_windows.get(node) if ops.use_customer_time_windows else None
                latest = min(
                    latest - network.distances(following, "time").get(node, inf),
                    window.close_seconds if window else inf,
                ) - ops.service_duration(node)
                if window and latest < window.open_seconds - 1e-8:
                    latest = -inf
                self.latest[i] = latest
                following = node
        initial = self.queue.popleft()
        self.queue = LabelQueue(self.priority)
        self._insert(initial, initial=True)
        self.complete = not self.queue

    def _insert(self, label, *, initial=False):
        done, node = label.mask.bit_count(), label.walk[-1]
        if self.timed:
            target = self.sequence[done] if done < len(self.sequence) else self.instance.depot_id
            latest = (self.latest[done] if done < len(self.sequence)
                      else self.instance.operations.max_route_seconds)
            earliest = float(label.resources.points[:, 1].min())
            if earliest + self.network.distances(target, "time").get(node, inf) > latest + 1e-8:
                self.pruned_time += 1
                return
        if self.escape_energy and (
            float(label.resources.points[:, 0].max()) - self.instance.parameters.reserve_kwh
            < self.escape_energy.get(node, inf) - 1e-8
        ):
            self.pruned_energy += 1
            return
        if initial:
            self.queue.append(label)
        else:
            super()._insert(label)

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
        self.escape_energy = network.escape_energy(vehicle) if network.nonnegative else {}
        self.reachable_times = {}
        if self.timed:
            ops = instance.operations
            # Un premio de un cliente que ya no puede alcanzarse antes de su
            # cierre no pertenece a ninguna continuación. Viaje mínimo y sin
            # recarga siguen siendo una relajación, incluso con regeneración.
            for node in network.graph:
                deadlines = []
                for customer, bit in self.bits.items():
                    window = ops.customer_time_windows.get(customer) if ops.use_customer_time_windows else None
                    latest = min(
                        window.close_seconds if window else inf,
                        ops.max_route_seconds - self.return_time.get(customer, inf),
                    ) - ops.service_duration(customer)
                    latest -= network.distances(customer, "time").get(node, inf)
                    deadlines.append((latest, bit))
                deadlines.sort()
                masks = [sum(bit for _, bit in deadlines)]
                for _, bit in deadlines:
                    masks.append(masks[-1] ^ bit)
                self.reachable_times[node] = ([t for t, _ in deadlines], masks)
        self.mask_cost = {}
        initial = self.queue.popleft()
        self.queue = LabelQueue(self.lower_bound)
        self.queue.append(initial)

    def lower_bound(self, label):
        node, params = label.walk[-1], self.instance.parameters
        if node not in self.return_energy:
            return inf
        reachable = (1 << len(self.rewards)) - 1
        if self.timed:
            times, masks = self.reachable_times[node]
            reachable = masks[bisect_left(times, float(label.resources.points[:, 1].min()) - 1e-8)]
        key = label.mask, reachable
        if key not in self.mask_cost:
            reward = sum(value if label.mask & (1 << i) else max(0, value)
                         if reachable & (1 << i) else 0
                         for i, value in enumerate(self.rewards))
            reward += sum(
                value * (((subset & (reachable | label.mask)).bit_count() // 2) if value > 0
                         else ((label.mask & subset).bit_count() // 2))
                for subset, value in self.cuts
            )
            self.mask_cost[key] = -self.convex_dual - reward
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
        bound = self.mask_cost[key] + self.energy_weight * energy
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
        if self.escape_energy and (
            float(label.resources.points[:, 0].max()) - self.instance.parameters.reserve_kwh
            < self.escape_energy.get(node, inf) - 1e-8
        ):
            self.pruned_return += 1
            return
        if self.lower_bound(label) >= -self.tolerance:
            self.pruned_bound += 1
            return
        super()._insert(label)
