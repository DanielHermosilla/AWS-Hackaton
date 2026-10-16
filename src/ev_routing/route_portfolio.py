"""Whole-fleet primal neighborhoods; physical repair remains authoritative.

The grouping/permutation budgets limit optional heuristic work only. They never
restrict exact pricing, allowable routes, or a proof of infeasibility.
"""

from __future__ import annotations

from itertools import combinations, permutations
from math import inf
from random import Random
from time import monotonic

import networkx as nx


def energy_groups(network, count=4):
    customers = sorted(network.instance.customer_ids)
    graph = nx.Graph()
    graph.add_nodes_from(customers)
    for i, a in enumerate(customers):
        for b in customers[i + 1:]:
            cost = (network.distances(b).get(a, inf) + network.distances(a).get(b, inf)) / 2
            if cost < inf:
                graph.add_edge(a, b, weight=cost)
    tree = nx.minimum_spanning_tree(graph)
    for a, b, _ in sorted(tree.edges(data=True), key=lambda e: -e[2]["weight"])[:max(0, count - 1)]:
        tree.remove_edge(a, b)
    return sorted((sorted(group) for group in nx.connected_components(tree)), key=lambda g: g[0])


def _nearest(network, customers, start):
    todo, walk = set(customers), []
    while todo:
        nxt = min(todo, key=lambda c: (network.distances(c).get(start, inf), c))
        todo.remove(nxt)
        walk.append(nxt)
        start = nxt
    return walk


def candidate_orders(search, strategy, clusters, deadline, seed):
    instance, network = search.instance, search.network
    customers, depot, fleet = instance.customer_ids, instance.depot_id, len(instance.vehicle_ids)
    windows = (instance.operations.customer_time_windows
               if instance.operations.use_customer_time_windows else {})
    def close(c):
        return windows[c].close_seconds if c in windows else inf

    if strategy == "deadline":
        # Global deadlines, then cyclic fleet assignment to avoid one vehicle
        # consuming all early slots. Alternative contiguous partitions follow.
        order = sorted(customers, key=lambda c: (close(c), c))
        yield [order[k::fleet] for k in range(fleet)]
        blocks = [[c] for c in order]
        tours = [blocks]
    elif strategy == "nearest":
        tours = [[[c] for c in _nearest(network, customers, depot)]]
    else:
        key = clusters
        if key not in search.portfolio_groups:
            search.portfolio_groups[key] = energy_groups(network, clusters)
        groups = search.portfolio_groups[key]
        blocks = []
        for group in groups:
            if strategy == "window_blocks":
                # Only windows actually supplied; broad windows are inserted
                # afterward in inexpensive positions using optimistic timing.
                horizon = instance.operations.max_route_seconds or inf
                tight = [c for c in group if c in windows
                         and windows[c].close_seconds - windows[c].open_seconds < horizon * .6]
                flexible = set(group) - set(tight)
                tight.sort(key=lambda c: (close(c), c))
                order = list(tight)
                for customer in _nearest(network, flexible, depot):
                    ranked = sorted(range(len(order) + 1), key=lambda pos: (
                        network.distances(customer).get(order[pos-1] if pos else depot, inf)
                        + network.distances(order[pos] if pos < len(order) else depot).get(customer, inf)
                        - network.distances(order[pos] if pos < len(order) else depot).get(
                            order[pos-1] if pos else depot, inf), pos,
                    ))
                    for pos in ranked:
                        trial = [*order[:pos], customer, *order[pos:]]
                        if network.sequence_time_possible(trial):
                            order = trial
                            break
                    else:
                        order.append(customer)
                blocks.append(order)
            else:
                blocks.append(_nearest(network, group, depot))
        # Enumerate a small block neighborhood; exact pricing has no such cap.
        if len(blocks) <= 6:
            tours = permutations(blocks)
        else:
            rng = Random(seed)
            tours = []
            for _ in range(24):
                trial = list(blocks)
                rng.shuffle(trial)
                tours.append(trial)
    seen = set()
    for blocks in tours:
        if monotonic() >= deadline:
            return
        blocks = list(blocks)
        tour = [c for block in blocks for c in block]
        boundaries, pos = [0], 0
        for block in blocks:
            pos += len(block)
            boundaries.append(pos)
        # Large singleton orders use sampled cuts; small block orders use all.
        if len(boundaries) > 17:
            boundaries = sorted({0, len(tour), *(round(len(tour)*i/16) for i in range(1, 16))})
        cuts = combinations(boundaries, fleet - 1) if fleet > 1 else [()]
        for cut in cuts:
            positions = [0, *cut, len(tour)]
            orders = [tour[a:b] for a, b in zip(positions, positions[1:])]
            signature = tuple(tuple(order) for order in orders)
            if signature not in seen and all(network.sequence_time_possible(order) for order in orders):
                seen.add(signature)
                yield orders
            if monotonic() >= deadline:
                return


def rebuild(search, best, policy, deadline, seed):
    from ev_routing.route_hybrid import quality, sequences

    if policy.rebuild_strategy == "none" or monotonic() >= deadline:
        return best
    state = (policy.rebuild_strategy, policy.rebuild_clusters,
             tuple(sorted(best.served_visit_ids)) if best else ())
    if policy.rebuild_strategy == "electric_local":
        state = (policy.rebuild_strategy,
                 tuple(tuple(order) for order in sequences(best)) if best else (),
                 policy.resource_path_order, policy.resource_repair_seconds)
    if state in search.consumed_rebuilds:
        return best
    search.consumed_rebuilds.add(state)
    started = monotonic()
    stop = min(deadline, started + policy.rebuild_seconds)
    search.stats["portfolio_calls"] += 1
    if policy.rebuild_strategy == "window_waves":
        from ev_routing.route_wave_schedule import rebuild_waves
        result = rebuild_waves(search, best, policy, stop)
        search.stats["portfolio_seconds"] += monotonic() - started
        return result
    if policy.rebuild_strategy == "electric_local":
        from ev_routing.route_electric_local import improve_electric
        interrupted = search.stats["electric_local_interrupted"]
        result = improve_electric(search, best, stop)
        if search.stats["electric_local_interrupted"] > interrupted:
            # A short heuristic slice must not consume the neighborhood forever.
            search.consumed_rebuilds.discard(state)
        elif result is not None:
            search.consumed_rebuilds.add((
                policy.rebuild_strategy,
                tuple(tuple(order) for order in sequences(result)),
                policy.resource_path_order, policy.resource_repair_seconds,
            ))
        search.stats["portfolio_seconds"] += monotonic() - started
        return result
    network, depot = search.network, search.instance.depot_id
    candidates = []
    for orders in candidate_orders(search, policy.rebuild_strategy, policy.rebuild_clusters,
                                   min(stop, started + policy.rebuild_seconds * .3), seed):
        cost = sum(network.distances(b).get(a, inf) for order in orders
                   for a, b in zip([depot, *order], [*order, depot]) if a != b)
        candidates.append((cost, orders))
    old_seconds = search.evaluation_seconds
    try:
        search.evaluation_seconds = max(old_seconds, min(1, policy.rebuild_seconds / 4))
        for _, orders in sorted(candidates, key=lambda item: item[0])[:24]:
            if monotonic() >= stop:
                break
            candidate = search.solution(orders, stop)
            search.stats["portfolio_candidates"] += 1
            if candidate is None:
                continue
            search.stats["portfolio_feasible"] += 1
            search._survive(candidate, policy.population_size)
            if quality(candidate) > quality(best):
                before = quality(best)
                best = candidate
                search.stats["portfolio_improvements"] += 1
                search._record("portfolio_incumbent", best, strategy=policy.rebuild_strategy,
                               previous_quality=before if before[0] >= 0 else None)
    finally:
        search.evaluation_seconds = old_seconds
    search.stats["portfolio_seconds"] += monotonic() - started
    return best
