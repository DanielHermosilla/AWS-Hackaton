"""Delivery orders are primal hints, never constraints or certificates."""

from __future__ import annotations

import json
import networkx as nx

from ev_routing.operations import arc_energy, travel_seconds


def validate_orders(orders, customer_ids, vehicle_ids):
    if set(orders) - set(vehicle_ids):
        raise ValueError("unknown_vehicle")
    visits = [node for order in orders.values() for node in order]
    if len(visits) != len(set(visits)) or set(visits) - set(customer_ids):
        raise ValueError("duplicate_or_unknown_delivery")


def routing_digest(instance, max_bytes):
    """Small directed metric for planning; resources remain in the full instance.

    Independent energy/time minima need not describe the same physical path.
    No witness, solution, seed identifier or generator metadata is read here.
    """
    services = [instance.depot_id, *sorted(instance.customer_ids)]
    if len(services) > 501:
        return {"scope": "omitted", "reason": "more_than_500_customers"}
    if any(arc_energy(a, instance.operations) < 0 for a in instance.arcs):
        return {"scope": "omitted", "reason": "negative_energy_not_supported_by_digest"}
    has_time = all(a.travel_time_seconds is not None or instance.operations.assumed_speed_kph
                   for a in instance.arcs)
    graphs = [nx.DiGraph() for _ in range(2 if has_time else 1)]
    for graph in graphs:
        graph.add_nodes_from(n.node_id for n in instance.nodes)
    for arc in instance.arcs:
        costs = [arc_energy(arc, instance.operations)]
        if has_time:
            costs.append(travel_seconds(arc, instance.operations))
        for graph, cost in zip(graphs, costs):
            a, b = arc.from_node_id, arc.to_node_id
            if not graph.has_edge(a, b) or cost < graph[a][b]["weight"]:
                graph.add_edge(a, b, weight=cost)
    matrices = []
    for graph in graphs:
        matrix = []
        for source in services:
            distances = nx.single_source_dijkstra_path_length(graph, source)
            matrix.append([round(distances[target], 2) if target in distances else None
                           for target in services])
        matrices.append(matrix)
    result = {
        "scope": "complete_customer_metric",
        "warning": "Separate unconstrained shortest ENERGY and TIME paths; not feasible routes or bounds with rounding. Native repair schedules charging, windows and streets.",
        "row_and_column_ids": services,
        "energy_kwh": matrices[0], "travel_seconds": matrices[1] if has_time else None,
        "vehicle_ids": instance.vehicle_ids,
        "customer_windows": {
            node: window.model_dump()
            for node, window in instance.operations.customer_time_windows.items()
        } if instance.operations.use_customer_time_windows else {},
    }
    size = len(json.dumps(result, separators=(",", ":"), allow_nan=False).encode())
    if size <= max_bytes:
        return result
    # Give large instances actionable structure instead of dropping all metrics.
    graph = nx.Graph()
    graph.add_nodes_from(range(1, len(services)))
    for i in graph.nodes:
        for j in range(i + 1, len(services)):
            a, b = matrices[0][i][j], matrices[0][j][i]
            if a is not None and b is not None:
                graph.add_edge(i, j, weight=(a + b)/2)
    tree = nx.minimum_spanning_tree(graph)
    for i, j, _ in sorted(tree.edges(data=True), key=lambda e: -e[2]["weight"])[:3]:
        tree.remove_edge(i, j)
    groups = sorted((sorted(g) for g in nx.connected_components(tree)), key=lambda g: g[0])
    summary = {k: v for k, v in result.items() if k not in {"energy_kwh", "travel_seconds"}}
    summary.update(
        scope="energy_clusters_and_nearest_neighbors_not_complete_matrix",
        dense_metric_bytes=size,
        energy_groups=[[services[i] for i in g] for g in groups],
        group_min_energy_kwh=[
            [min((matrices[0][i][j] for i in a for j in b if matrices[0][i][j] is not None),
                 default=None) for b in groups] for a in groups
        ],
        nearest_neighbors={
            services[i]: [[services[j], matrices[0][i][j],
                           matrices[1][i][j] if has_time else None]
                          for j in sorted((j for j in range(1, len(services)) if j != i
                                           and matrices[0][i][j] is not None),
                                          key=lambda j: matrices[0][i][j])[:3]]
            for i in range(1, len(services))
        },
    )
    if len(json.dumps(summary, separators=(",", ":")).encode()) <= max_bytes:
        return summary
    return {"scope": "omitted", "reason": "metric_exceeds_context_budget", "bytes": size}
