"""Primal construction for geographic areas with repeated deadline waves."""

from itertools import product
from math import inf
from time import monotonic

from ev_routing.route_hybrid import quality, sequences
from ev_routing.route_portfolio import energy_groups


def rebuild_waves(search, best, policy, deadline):
    instance, network = search.instance, search.network
    if best is not None and len(best.served_visit_ids) == len(instance.customer_ids):
        return best
    ops, fleet = instance.operations, len(instance.vehicle_ids)
    if not ops.use_customer_time_windows or not ops.max_route_seconds:
        return best
    windows = ops.customer_time_windows
    groups = energy_groups(network, policy.rebuild_clusters)
    def close(c):
        return windows[c].close_seconds if c in windows else inf

    tight = {c for c in instance.customer_ids if c in windows
             and windows[c].close_seconds - windows[c].open_seconds < .6 * ops.max_route_seconds}
    if not tight:
        return best
    candidates = []
    # A bounded optional neighborhood; exact pricing remains unrestricted.
    for number, assignment in enumerate(product(range(fleet), repeat=len(groups))):
        if number >= 512 or monotonic() >= deadline:
            break
        orders = [[] for _ in range(fleet)]
        flexible = []
        for group, vehicle in zip(groups, assignment):
            orders[vehicle].extend(c for c in group if c in tight)
            flexible.extend((c, vehicle) for c in group if c not in tight)
        for order in orders:
            order.sort(key=lambda c: (close(c), c))
        if not all(network.sequence_time_possible(order) for order in orders):
            continue
        energy = sum(
            network.distances(b).get(a, inf)
            for order in orders
            for a, b in zip([instance.depot_id, *order], [*order, instance.depot_id])
            if a != b
        )
        candidates.append((energy, orders, flexible))
    old_seconds, old_policy = search.evaluation_seconds, search.policy
    search.evaluation_seconds = max(old_seconds, .08)
    search.policy = policy.model_copy(update={"resource_path_order": "time"})
    try:
        for _, orders, flexible in sorted(candidates, key=lambda item: item[0]):
            if monotonic() >= deadline:
                break
            search.stats["wave_backbone_attempts"] += 1
            backbone = search.solution(orders, deadline)
            if backbone is None:
                continue
            search.stats["wave_backbone_feasible"] += 1
            orders = sequences(backbone)
            # Insertion checks physical charging and windows for the actual
            # candidate, rather than accepting the optimistic path metric.
            for customer, preferred_vehicle in sorted(flexible, key=lambda item: close(item[0])):
                if monotonic() >= deadline:
                    break
                positions = []
                for vehicle, order in enumerate(orders):
                    for position in range(len(order) + 1):
                        a = order[position - 1] if position else instance.depot_id
                        b = order[position] if position < len(order) else instance.depot_id
                        cost = (network.distances(customer).get(a, inf)
                                + network.distances(b).get(customer, inf)
                                - (network.distances(b).get(a, inf) if a != b else 0))
                        positions.append((cost, vehicle != preferred_vehicle, vehicle, position))
                for _, _, vehicle, position in sorted(positions)[:16]:
                    if monotonic() >= deadline:
                        break
                    trial = [*orders[vehicle][:position], customer, *orders[vehicle][position:]]
                    if search.evaluate(instance.vehicle_ids[vehicle], trial, deadline) is not None:
                        orders[vehicle] = trial
                        break
            candidate = search.solution(orders, deadline)
            search.stats["wave_candidates"] += 1
            if quality(candidate) > quality(best):
                best = candidate
                search._survive(best, policy.population_size)
                search.stats["wave_improvements"] += 1
                search._record("wave_schedule_incumbent", best)
            if best is not None and len(best.served_visit_ids) == len(instance.customer_ids):
                break
    finally:
        search.evaluation_seconds, search.policy = old_seconds, old_policy
    return best
