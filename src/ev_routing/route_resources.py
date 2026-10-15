"""Pricing de recorridos sin horizonte, con recursos continuos.

Una etiqueta conserva un poliedro de (batería, tiempo, carga acumulada).
No discretiza la recarga, no limita visitas ni elimina ciclos por su longitud.
La saturación y las ventanas se separan en ramas afines antes de convexificar.
Solo agotar las etiquetas no dominadas acredita pricing completo.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic

import numpy as np
from scipy.optimize import linprog
from scipy.spatial import ConvexHull, QhullError

from ev_routing.contracts import ProblemInstance, RouteStep, Solution, VehicleRoute
from ev_routing.operations import arc_energy, charge_seconds, schedule_solution, travel_seconds


@dataclass
class Polytope:
    points: np.ndarray
    charges: np.ndarray

    def subset(self, indices) -> Polytope:
        return Polytope(self.points[indices], self.charges[indices])

    def hull(self) -> Polytope:
        if len(self.points) < 3:
            return self
        # No Qhull "joggle": perturbar recursos podría crear rutas infactibles.
        _, indices = np.unique(self.points, axis=0, return_index=True)
        p = self.subset(sorted(indices))
        centered = p.points - p.points[0]
        _, singular, axes = np.linalg.svd(centered, full_matrices=False)
        rank = int(np.sum(singular > 1e-12))
        if rank == 0:
            return p.subset([0])
        projection = centered @ axes[:rank].T
        if rank == 1:
            return p.subset(np.unique([projection[:, 0].argmin(), projection[:, 0].argmax()]))
        if len(p.points) <= rank + 1:
            return p
        try:
            return p.subset(ConvexHull(projection).vertices)
        except QhullError:
            # Conservar vértices redundantes es seguro; descartarlos no lo sería.
            return p

    def clip(self, axis: int, bound: float, *, upper: bool = True) -> Polytope | None:
        delta = (self.points[:, axis] - bound) * (1 if upper else -1)
        inside, outside = np.flatnonzero(delta <= 0), np.flatnonzero(delta > 0)
        if not len(inside):
            return None
        if not len(outside):
            return self
        points, charges = [self.points[inside]], [self.charges[inside]]
        # Todos los pares incluyen las aristas verdaderas. Intersecciones de
        # diagonales son puntos interiores válidos, eliminables por convex hull.
        for i in inside:
            for j in outside:
                weight = delta[i] / (delta[i] - delta[j])
                points.append((self.points[i] + weight * (self.points[j] - self.points[i]))[None])
                charges.append((self.charges[i] + weight * (self.charges[j] - self.charges[i]))[None])
        return Polytope(np.vstack(points), np.vstack(charges)).hull()

    def dominates(self, other: Polytope) -> bool:
        # Menos carga acumulada, más batería y menor tiempo dominan incluso con
        # regeneración: E_final = b_inicial + Q_total - b_final.
        signs = np.array([-1.0, 1.0, 1.0])
        a, b = self.points * signs, other.points * signs
        for target in b:
            if np.any(np.all(a <= target, axis=1)):
                continue
            if len(a) == 1:
                return False
            result = linprog(
                np.zeros(len(a)), A_ub=a.T, b_ub=target,
                A_eq=np.ones((1, len(a))), b_eq=[1.0],
                bounds=(0, None), method="highs",
            )
            # Revalidar el testigo sin relajar la dominancia física. Un falso
            # negativo solo retiene etiquetas; un falso positivo pierde rutas.
            if (
                not result.success or np.any(result.x < 0)
                or abs(sum(result.x) - 1) > 1e-12
                or not np.all((result.x @ a) <= target)
            ):
                return False
        return True


@dataclass
class Label:
    walk: tuple[str, ...]
    services: tuple[int, ...]
    mask: int
    resources: Polytope
    active: bool = True


def route_from_walk(
    instance: ProblemInstance, vehicle: str, walk, services, charges,
) -> VehicleRoute:
    arcs = {(a.from_node_id, a.to_node_id): a for a in instance.arcs}
    b = instance.parameters.initial_energy_kwh
    steps, energy = [], 0.0
    for index, node in enumerate(walk):
        q = float(charges[index])
        departure = b + q
        target = walk[index + 1] if index + 1 < len(walk) else None
        predicted = None if target is None else (
            0.0 if node == target == instance.depot_id else arc_energy(arcs[node, target], instance.operations)
        )
        arrival = None if target is None else min(
            instance.parameters.battery_capacity_kwh, departure - predicted,
        )
        effective = None if arrival is None else departure - arrival
        steps.append(RouteStep(
            position=index, node_id=node, battery_arrival_kwh=b,
            charged_to_battery_kwh=q, battery_departure_kwh=departure,
            delivered_visit_ids=[node] if index in services else [],
            next_node_id=target, predicted_arc_energy_kwh=predicted,
            effective_arc_energy_kwh=effective,
        ))
        if arrival is not None:
            b = arrival
            energy += effective
    return VehicleRoute(vehicle_id=vehicle, steps=steps, net_energy_kwh=energy)


def assemble_solution(instance: ProblemInstance, routes: list[VehicleRoute]) -> Solution:
    served = sorted({i for r in routes for s in r.steps for i in s.delivered_visit_ids})
    return schedule_solution(instance, Solution(
        routes=routes, served_visit_ids=served,
        unserved_visit_ids=sorted(set(instance.customer_ids) - set(served)),
        net_energy_kwh=sum(r.net_energy_kwh for r in routes),
    ))


class RouteOracle:
    """Exploración reutilizable entre duales y fases; ninguna cota de movimientos."""

    def __init__(self, instance: ProblemInstance, vehicle: str):
        self.instance, self.vehicle = instance, vehicle
        self.bits = {node: 1 << i for i, node in enumerate(instance.customer_ids)}
        self.outgoing = defaultdict(list)
        for arc in instance.arcs:
            self.outgoing[arc.from_node_id].append(arc)
        self.chargers = set(instance.chargers_for(vehicle))
        self.timed = instance.operations.max_route_seconds is not None
        initial = Label((instance.depot_id,), (), 0, Polytope(
            np.array([[instance.parameters.initial_energy_kwh, 0.0, 0.0]]), np.zeros((1, 1)),
        ))
        self.queue = deque([initial])
        self.frontiers = defaultdict(list)
        self.frontiers[instance.depot_id, 0].append(initial)
        self.routes: dict[int, VehicleRoute] = {}
        self.expanded = 0
        self.complete = False

    def _insert(self, label: Label) -> None:
        key = label.walk[-1], label.mask
        frontier = self.frontiers[key]
        if any(old.resources.dominates(label.resources) for old in frontier):
            return
        kept = []
        for old in frontier:
            if label.resources.dominates(old.resources):
                old.active = False
            else:
                kept.append(old)
        self.frontiers[key] = [*kept, label]
        self.queue.append(label)

    def _service(self, label: Label):
        yield label.mask, label.services, label.resources
        node = label.walk[-1]
        bit = self.bits.get(node, 0)
        if not bit or label.mask & bit:
            return
        ops = self.instance.operations
        variants = [label.resources]
        window = ops.customer_time_windows.get(node) if ops.use_customer_time_windows else None
        if self.timed and window is not None:
            early = label.resources.clip(1, window.open_seconds)
            late = label.resources.clip(1, window.open_seconds, upper=False)
            variants = []
            if early is not None:
                points = early.points.copy()
                points[:, 1] = window.open_seconds
                variants.append(Polytope(points, early.charges))
            if late is not None:
                variants.append(late)
        for poly in variants:
            if self.timed:
                points = poly.points.copy()
                points[:, 1] += ops.service_duration(node)
                poly = Polytope(points, poly.charges)
                if window is not None:
                    poly = poly.clip(1, window.close_seconds)
                    if poly is None:
                        continue
            yield label.mask | bit, (*label.services, len(label.walk) - 1), poly

    def advance(self) -> dict[int, VehicleRoute]:
        """Expandir una etiqueta y devolver rutas nuevas/mejoradas."""
        changed = {}
        if not self.queue:
            self.complete = True
            return changed
        label = self.queue.popleft()
        if not label.active:
            return changed
        self.expanded += 1
        instance, node = self.instance, label.walk[-1]
        params, ops = instance.parameters, instance.operations
        capacity, reserve = params.battery_capacity_kwh, params.reserve_kwh
        if node == instance.depot_id:
            final_reserve = max(reserve, (ops.final_reserve_soc or 0) * capacity)
            poly = label.resources.clip(0, final_reserve, upper=False)
            if poly is not None:
                values = params.initial_energy_kwh + poly.points[:, 2] - poly.points[:, 0]
                index = int(values.argmin())
                previous = self.routes.get(label.mask)
                if previous is None or values[index] < previous.net_energy_kwh - 1e-9:
                    route = route_from_walk(
                        instance, self.vehicle, label.walk, label.services, poly.charges[index],
                    )
                    self.routes[label.mask] = changed[label.mask] = route
        for mask, services, poly in self._service(label):
            if node in self.chargers:
                full, charges = poly.points.copy(), poly.charges.copy()
                q = capacity - full[:, 0]
                full[:, 0] = capacity
                full[:, 2] += q
                if self.timed:
                    full[:, 1] += q * charge_seconds(1, node, ops)
                charges[:, -1] += q
                poly = Polytope(
                    np.vstack([poly.points, full]), np.vstack([poly.charges, charges]),
                ).hull()
            for arc in self.outgoing[node]:
                energy = arc_energy(arc, ops)
                feasible = poly.clip(0, reserve + energy, upper=False) if energy >= 0 else poly
                if feasible is None:
                    continue
                if energy < 0:
                    parts = [
                        (feasible.clip(0, capacity + energy), False),
                        (feasible.clip(0, capacity + energy, upper=False), True),
                    ]
                else:
                    parts = [(feasible, False)]
                for part, saturated in parts:
                    if part is None:
                        continue
                    points = part.points.copy()
                    points[:, 0] = capacity if saturated else points[:, 0] - energy
                    if self.timed:
                        points[:, 1] += travel_seconds(arc, ops)
                    following = Polytope(
                        points, np.pad(part.charges, ((0, 0), (0, 1))),
                    )
                    if self.timed:
                        following = following.clip(1, ops.max_route_seconds)
                        if following is None:
                            continue
                    self._insert(Label(
                        (*label.walk, arc.to_node_id), services, mask, following.hull(),
                    ))
        self.complete = not self.queue
        return changed

    def exhaust(self, deadline: float) -> None:
        while not self.complete and monotonic() < deadline:
            self.advance()
