"""ALNS, población memética y reparación física sobre el multigrafo de pricing."""

from __future__ import annotations

from collections import Counter
from math import inf
from random import Random
from time import monotonic

from ev_routing.route_heuristics import InsertionRoutes
from ev_routing.route_pricing import PricingNetwork, SequenceOracle
from ev_routing.route_resources import assemble_solution
from ev_routing.validation import validate_solution


def quality(solution):
    return (-1, -inf) if solution is None else (
        len(solution.served_visit_ids), -solution.net_energy_kwh,
    )


def sequences(solution):
    return [[i for step in route.steps for i in step.delivered_visit_ids]
            for route in solution.routes]


class HybridRoutes:
    """La caché limita heurísticas; el pricing exacto mantiene su espacio completo."""

    def __init__(self, instance):
        self.instance, self.network = instance, PricingNetwork(instance)
        self.fast = InsertionRoutes(instance)
        self.fast.supported &= not any(
            a.battery_profile is not None or a.arc_id is not None for a in instance.arcs
        ) and not any(n.node_type == "junction" for n in instance.nodes)
        self.supported = True
        self.pool = self.fast.pool
        self.trace = self.fast.trace
        self.cache, self.population = {}, []
        self.operator_scores, self.operator_counts = Counter(), Counter()
        self.stats = Counter()
        self.pool_limit = 2000
        self.evaluation_seconds = .04
        self.policy = None
        self.observer = None
        self.last_observation = -inf

    def _observe(self):
        if self.observer is None:
            return
        now = monotonic()
        if now - self.last_observation < .25:
            return
        self.last_observation = now
        self.observer("heuristic_progress", self.telemetry())
        if self.policy is not None:
            self.evaluation_seconds = self.policy.resource_repair_seconds

    def remember(self, route):
        self.fast.pool_limit = self.pool_limit
        self.fast.remember(route)

    def evaluate(self, vehicle, order, deadline):
        path_order = self.policy.resource_path_order if self.policy else "energy"
        key = vehicle, tuple(order), path_order
        if key in self.cache:
            self.stats["cache_hits"] += 1
            return self.cache[key]
        if len(set(order)) != len(order) or monotonic() >= deadline:
            return None
        started = monotonic()
        route = None
        if self.fast.supported:
            walk = [self.instance.depot_id, *order, self.instance.depot_id]
            if self.fast.cost(walk) <= self.fast.usable:
                route = self.fast.route(vehicle, walk)
        if route is None:
            oracle = SequenceOracle(self.instance, vehicle, order, self.network, path_order=path_order)
            stop = min(deadline, started + self.evaluation_seconds)
            while monotonic() < stop and not oracle.complete:
                found = oracle.advance()
                if oracle.target_mask in found:
                    route = found[oracle.target_mask]
                    break
            self.stats["repair_labels"] += oracle.expanded
        self.stats["route_evaluations"] += 1
        self.stats["route_evaluation_seconds"] += monotonic() - started
        if route is not None:
            self.cache[key] = route
            self.remember(route)
            while len(self.cache) > self.pool_limit:
                self.cache.pop(next(iter(self.cache)))
        # Un timeout no se memoriza como infactibilidad de la secuencia.
        return route

    def solution(self, orders, deadline):
        routes = []
        for vehicle, order in zip(self.instance.vehicle_ids, orders):
            route = self.evaluate(vehicle, order, deadline)
            if route is None:
                return None
            routes.append(route)
        solution = assemble_solution(self.instance, routes)
        if validate_solution(self.instance, solution, enforce_movement_limit=False).feasible:
            return solution
        self.stats["rejected_candidates"] += 1
        return None

    def _options(self, orders, customer, deadline, *, all_positions=True):
        choices = []
        for k, order in enumerate(orders):
            previous = self.evaluate(self.instance.vehicle_ids[k], order, deadline)
            if previous is None:
                continue
            positions = range(len(order) + 1) if all_positions else [len(order)]
            # Cerca del cliente primero: el límite es de trabajo heurístico.
            positions = sorted(positions, key=lambda pos: self.network.distances(customer).get(
                order[pos - 1] if pos else self.instance.depot_id, inf,
            ))
            for pos in positions:
                if monotonic() >= deadline:
                    return sorted(choices)
                # Una reparación puede ocupar toda la etapa. Recoger respuestas
                # listas entre inserciones, sin esperar inferencia remota.
                self._observe()
                candidate = self.evaluate(
                    self.instance.vehicle_ids[k], order[:pos] + [customer] + order[pos:], deadline,
                )
                if candidate is not None:
                    choices.append((candidate.net_energy_kwh - previous.net_energy_kwh, k, pos))
        return sorted(choices)

    def _repair(self, orders, pending, deadline, rng, *, regret=True, ranked=None):
        pending = set(pending)
        while pending and monotonic() < deadline:
            choices = []
            nodes = list(ranked or sorted(pending))
            nodes = [i for i in nodes if i in pending]
            nodes += sorted(pending - set(nodes))
            # Un lote configurable busca inserciones prometedoras; no limita
            # clientes del modelo ni modifica una prueba de optimalidad.
            batch = self.policy.repair_candidates if self.policy else 8
            for customer in nodes[:batch]:
                options = self._options(orders, customer, deadline)
                if not options:
                    continue
                delta, k, pos = options[0]
                second = options[1][0] if len(options) > 1 else delta + 1
                score = delta - second if regret else delta
                choices.append((score + rng.random() * 1e-10, delta, customer, k, pos))
            if not choices:
                # Continuar con otro lote antes de concluir fracaso heurístico.
                remaining = nodes[batch:]
                for customer in remaining:
                    options = self._options(orders, customer, deadline, all_positions=False)
                    if options:
                        delta, k, pos = options[0]
                        choices.append((delta, delta, customer, k, pos))
                        break
                if not choices:
                    break
            _, _, customer, k, pos = min(choices)
            orders[k].insert(pos, customer)
            pending.remove(customer)
        return orders

    def seed(self, strategy, starts, deadline, seed=0):
        best = self.fast.seed(strategy, starts, deadline, seed) if self.fast.supported else None
        if best is not None:
            self._survive(best, 12)
            return best
        rng = Random(seed)
        if strategy == "none":
            return None
        for attempt in range(starts):
            if monotonic() >= deadline:
                break
            orders = [[] for _ in self.instance.vehicle_ids]
            pending = list(self.instance.customer_ids)
            rng.shuffle(pending)
            # Construcción por extensiones para no gastar todo el arranque en
            # evaluar n^3 inserciones con recursos.
            while pending and monotonic() < deadline:
                progress = False
                for k, order in enumerate(orders):
                    origin = order[-1] if order else self.instance.depot_id
                    ranked = sorted(pending, key=lambda i: self.network.distances(i).get(origin, inf))
                    if attempt and len(ranked) > 2:
                        ranked[:3] = rng.sample(ranked[:3], 3)
                    for customer in ranked:
                        route = self.evaluate(self.instance.vehicle_ids[k], order + [customer], deadline)
                        if route is not None:
                            order.append(customer)
                            pending.remove(customer)
                            progress = True
                            break
                        if monotonic() >= deadline:
                            break
                if not progress:
                    break
            candidate = self.solution(orders, deadline)
            if quality(candidate) > quality(best):
                best = candidate
                self._survive(best, 12)
                self.trace.append({"event": "resource_seed", "deliveries": quality(best)[0],
                                   "energy_kwh": best.net_energy_kwh})
        return best

    def charging_seed(self, starts, deadline, tours=None):
        if self.fast.supported:
            return self.fast.charging_seed(starts, deadline, tours=tours)
        return self.seed("regret_insertion", starts, deadline)

    def split_tour(self, tour, deadline):
        if self.fast.supported:
            return self.fast.split_tour(tour, deadline)
        customers = [i for i in tour if i in self.instance.customer_ids]
        old = self.evaluation_seconds
        self.evaluation_seconds = min(1.0, max(old, deadline-monotonic()))
        best = None
        try:
            for k in range(len(self.instance.vehicle_ids)):
                orders = [[] for _ in self.instance.vehicle_ids]
                orders[k] = customers
                candidate = self.solution(orders, deadline)
                if quality(candidate) > quality(best):
                    best = candidate
                if monotonic() >= deadline:
                    break
            return best
        finally:
            self.evaluation_seconds = old

    def _survive(self, candidate, size):
        if candidate is None:
            return
        signature = tuple(tuple(s) for s in sequences(candidate))
        if any(tuple(tuple(s) for s in sequences(old)) == signature for old in self.population):
            return
        self.population.append(candidate)
        self.population.sort(key=quality, reverse=True)
        if len(self.population) > size:
            # Elitismo; eliminar el individuo no élite más redundante en aristas.
            def edges(sol):
                return {(k, a, b) for k, order in enumerate(sequences(sol))
                        for a, b in zip(order, order[1:])}
            sets = [edges(sol) for sol in self.population]
            similarities = [
                (max((len(s & other) / max(1, len(s | other))
                      for j, other in enumerate(sets) if j != i), default=0), i)
                for i, s in enumerate(sets) if i
            ]
            self.population.pop(max(similarities)[1])

    def _destroy(self, orders, operator, fraction, rng):
        items = [(k, i) for k, order in enumerate(orders) for i in order]
        if not items:
            return orders
        count = max(1, int(len(items) * fraction))
        if operator == "related":
            anchor = rng.choice(items)[1]
            items.sort(key=lambda ki: self.network.distances(anchor).get(ki[1], inf))
        elif operator == "route":
            chosen = rng.randrange(len(orders))
            items.sort(key=lambda ki: ki[0] != chosen)
        elif operator == "worst":
            def detour(ki):
                k, i = ki
                order = [self.instance.depot_id, *orders[k], self.instance.depot_id]
                j = order.index(i)
                a, b = order[j-1], order[j+1]
                return (self.network.distances(i).get(a, inf)
                        + self.network.distances(b).get(i, inf)
                        - self.network.distances(b).get(a, inf))
            items.sort(key=detour, reverse=True)
        else:
            rng.shuffle(items)
        removed = {i for _, i in items[:count]}
        return [[i for i in order if i not in removed] for order in orders]

    def improve(self, best, policy, deadline, seed):
        self.policy = policy
        self.evaluation_seconds = policy.resource_repair_seconds
        if best is None:
            best = self.seed(policy.seed_strategy, policy.seed_starts, deadline, seed)
        if best is None:
            return None
        if self.fast.supported:
            legacy_deadline = min(deadline, monotonic() + max(0, deadline-monotonic())*.25)
            best = self.fast.improve(best, policy, legacy_deadline, seed)
        self._survive(best, policy.population_size)
        current, rng = best, Random(seed)
        for iteration in range(policy.alns_iterations):
            if monotonic() >= deadline:
                break
            self._observe()
            operators = policy.destroy_operators
            weights = [1 + self.operator_scores[op] / (1 + self.operator_counts[op]) for op in operators]
            operator = rng.choices(operators, weights=weights)[0]
            orders = self._destroy(sequences(current), operator, policy.ruin_fraction, rng)
            if policy.memetic_enabled and len(self.population) > 1 and iteration % 3 == 2:
                first, second = rng.sample(self.population, 2)
                orders = [[] for _ in self.instance.vehicle_ids]
                k = rng.randrange(len(orders))
                orders[k] = sequences(first)[k]
                inherited = set(orders[k])
                for j, order in enumerate(sequences(second)):
                    if j != k:
                        orders[j] = [i for i in order if i not in inherited]
                        inherited.update(orders[j])
                operator = "crossover"
                self.stats["crossovers"] += 1
            present = {i for order in orders for i in order}
            pending = set(self.instance.customer_ids) - present
            ranked = [i for i in policy.focus_customers if i in pending]
            if not ranked:
                ranked = sorted(pending)
                rng.shuffle(ranked)
            self._repair(orders, pending, deadline, rng, regret=policy.repair_strategy == "regret",
                         ranked=ranked)
            candidate = self.solution(orders, deadline)
            self.operator_counts[operator] += 1
            if candidate is not None:
                self._survive(candidate, policy.population_size)
                gain = quality(candidate) > quality(current)
                self.operator_scores[operator] += 5 if gain else 0
                if gain or rng.random() < policy.diversification_probability:
                    current = candidate
                if quality(candidate) > quality(best):
                    best = candidate
                    self.operator_scores[operator] += 10
                    self.trace.append({"event": "hybrid_improvement", "operator": operator,
                                       "deliveries": quality(best)[0], "energy_kwh": best.net_energy_kwh})
        return best

    def price(self, vehicle, prizes, cuts, energy_weight, starts, deadline):
        routes = self.fast.price(vehicle, prizes, cuts, energy_weight, starts, deadline) if self.fast.supported else {}
        if monotonic() >= deadline:
            return routes
        bits = {node: 1 << i for i, node in enumerate(self.instance.customer_ids)}
        for attempt in range(starts):
            if monotonic() >= deadline:
                break
            ranked = sorted(prizes, key=lambda i: (-prizes[i], i))
            if ranked:
                ranked = ranked[attempt % len(ranked):] + ranked[:attempt % len(ranked)]
            order, previous_score = [], 0.0
            for customer in ranked:
                if monotonic() >= deadline:
                    break
                candidate = self.evaluate(vehicle, order + [customer], deadline)
                if candidate is None:
                    continue
                mask = sum(bits[i] for i in order + [customer])
                score = (sum(prizes[i] for i in order + [customer])
                         + sum(value * ((mask & subset).bit_count() // 2) for subset, value in cuts)
                         - energy_weight * candidate.net_energy_kwh)
                if score > previous_score or not order:
                    order.append(customer)
                    previous_score = score
                    routes[mask] = candidate
        return routes

    def telemetry(self):
        return {"heuristics": dict(self.stats), "operator_attempts": dict(self.operator_counts),
                "operator_rewards": dict(self.operator_scores), "population": len(self.population),
                "route_pool": len(self.pool)}
