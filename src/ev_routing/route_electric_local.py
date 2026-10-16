"""Resource-validated 2-opt, relocation and inter-route tail exchanges."""

from __future__ import annotations

from math import inf
from time import monotonic


def improve_electric(search, best, deadline):
    from ev_routing.route_hybrid import quality, sequences

    if best is None:
        return None
    network, depot = search.network, search.instance.depot_id
    def distance(a, b):
        return network.distances(b).get(a, inf) if a != b else 0

    sweep = 0
    exhausted = False
    while monotonic() < deadline:
        orders = sequences(best)
        moves = []
        ranking_complete = True
        for k, order in enumerate(orders):
            # Directed reversal needs the internal arc difference, not just
            # the symmetric TSP four-edge formula.
            prefix = [0.0]
            for a, b in zip(order, order[1:]):
                prefix.append(prefix[-1] + distance(b, a) - distance(a, b))
            for i in range(len(order)):
                a, b = order[i-1] if i else depot, order[i]
                for j in range(i+1, len(order)):
                    c, d = order[j], order[j+1] if j+1 < len(order) else depot
                    gain = (distance(a, c) + distance(b, d) - distance(a, b) - distance(c, d)
                            + prefix[j] - prefix[i])
                    if gain < -1e-8:
                        moves.append((gain, "reverse", k, i, j))
                for j in range(len(order)+1):
                    if j in (i, i+1):
                        continue
                    c = order[i+1] if i+1 < len(order) else depot
                    x, y = order[j-1] if j else depot, order[j] if j < len(order) else depot
                    gain = (distance(a, c) - distance(a, b) - distance(b, c)
                            + distance(x, b) + distance(b, y) - distance(x, y))
                    if gain < -1e-8:
                        moves.append((gain, "relocate", k, i, j))
            for other in range(k+1, len(orders)):
                route = orders[other]
                for i in range(len(order)+1):
                    a, b = order[i-1] if i else depot, order[i] if i < len(order) else depot
                    for j in range(len(route)+1):
                        c, d = route[j-1] if j else depot, route[j] if j < len(route) else depot
                        gain = distance(a, d) + distance(c, b) - distance(a, b) - distance(c, d)
                        if gain < -1e-8:
                            moves.append((gain, "tails", k, other, i, j))
            if monotonic() >= deadline:
                ranking_complete = False
                break
        search.stats["electric_local_ranked_moves"] += len(moves)
        changed = False
        evaluated_all = True
        for move in sorted(moves):
            if monotonic() >= deadline:
                evaluated_all = False
                break
            trial = [list(order) for order in orders]
            kind, k = move[1:3]
            if kind == "tails":
                other, i, j = move[3:]
                trial[k] = orders[k][:i] + orders[other][j:]
                trial[other] = orders[other][:j] + orders[k][i:]
                affected = [k, other]
            else:
                i, j = move[3:]
                affected = [k]
                if kind == "reverse":
                    trial[k][i:j+1] = reversed(trial[k][i:j+1])
                else:
                    customer = trial[k].pop(i)
                    trial[k].insert(j - (j > i), customer)
            if not all(network.sequence_time_possible(trial[j]) for j in affected):
                search.stats["electric_local_time_rejections"] += 1
                continue
            search.stats["electric_local_repairs"] += 1
            candidate = search.solution(trial, deadline)
            if quality(candidate) > quality(best):
                previous = best.net_energy_kwh
                best = candidate
                search._survive(best, search.policy.population_size if search.policy else 12)
                search.stats["electric_local_improvements"] += 1
                search._record("electric_local_incumbent", best, operator=kind,
                               previous_energy_kwh=previous, sweep=sweep)
                changed = True
                break
        if not changed:
            exhausted = ranking_complete and evaluated_all and monotonic() < deadline
            break
        sweep += 1
    search.stats["electric_local_completed_passes" if exhausted else "electric_local_interrupted"] += 1
    return best
