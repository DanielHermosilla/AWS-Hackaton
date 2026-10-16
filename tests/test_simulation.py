"""La demanda simulada conserva calles, fuentes y conectividad dirigida."""

import pytest

from ev_routing.contracts import Arc, Node, ProblemInstance
from ev_routing.service_graph import build_service_graph, check_service_context, fingerprint
from ev_routing.simulation import simulate_customers


@pytest.fixture
def road():
    nodes = [
        Node(node_id="base", node_type="base", latitude=0, longitude=0),
        Node(node_id="a", node_type="visit", latitude=0, longitude=1),
        Node(node_id="b", node_type="visit", latitude=1, longitude=0),
        Node(node_id="charger", node_type="charger", latitude=0.9, longitude=0.9),
        *[Node(node_id=f"j{i}", node_type="junction", latitude=i / 20, longitude=0.2)
          for i in range(1, 10)],
        Node(node_id="outside", node_type="junction", latitude=2, longitude=2),
        Node(node_id="coincident", node_type="junction", latitude=0, longitude=1),
        Node(node_id="oneway", node_type="junction", latitude=0.5, longitude=0.5),
        Node(node_id="isolated", node_type="junction", latitude=0.6, longitude=0.6),
    ]
    arcs = [Arc(from_node_id=source, to_node_id=target, energy_kwh=0.5, distance_m=10)
            for node in nodes[1:-2]
            for source, target in (("base", node.node_id), (node.node_id, "base"))]
    arcs.append(Arc(from_node_id="base", to_node_id="oneway", energy_kwh=0.5))
    return ProblemInstance(nodes=nodes, arcs=arcs)


def test_simulation_preserves_source_roads_resources_and_chargers(road):
    before = fingerprint(road)
    simulated = simulate_customers(road, 5, seed=0)
    assert fingerprint(road) == before
    assert len(simulated.customer_ids) == 5
    assert set(road.customer_ids) < set(simulated.customer_ids)
    assert simulated.charger_ids == road.charger_ids
    assert simulated.arcs == road.arcs
    assert simulated.parameters == road.parameters
    assert simulated.operations == road.operations
    added = simulated.provenance["simulation"]["added_customer_ids"]
    assert len(set(added)) == 3
    assert set(added) <= {f"j{i}" for i in range(1, 10)}
    assert simulated.provenance["simulation"]["source_instance_sha256"] == before
    assert simulated.provenance["simulation"]["candidate_count"] == 9


def test_seed_is_reproducible_independent_of_input_order(road):
    first = simulate_customers(road, 5, seed=0)
    assert fingerprint(first) == fingerprint(simulate_customers(road, 5, seed=0))
    reordered = road.model_copy(update={"nodes": list(reversed(road.nodes))})
    def select(instance):
        return instance.provenance["simulation"]["added_customer_ids"]
    assert select(first) == select(simulate_customers(reordered, 5, seed=0))
    assert select(first) != select(simulate_customers(road, 5, seed=1))


@pytest.mark.parametrize("total", [0, 2, 20, True, 3.5])
def test_invalid_or_unavailable_customer_counts_are_rejected(road, total):
    with pytest.raises(ValueError):
        simulate_customers(road, total)


def test_simulation_requires_coordinates_nonnegative_seed_and_road_graph(road):
    with pytest.raises(ValueError, match="semilla"):
        simulate_customers(road, 5, seed=-1)
    without_coordinates = road.model_copy(update={"nodes": [
        node.model_copy(update={"latitude": None, "longitude": None})
        if node.node_id == "a" else node for node in road.nodes
    ]})
    with pytest.raises(ValueError, match="coordenadas"):
        simulate_customers(without_coordinates, 5)
    compact, _ = build_service_graph(road, road.parameters.movement_limit)
    with pytest.raises(ValueError, match="red vial original"):
        simulate_customers(compact, 5)


def test_rebuilt_paths_match_simulated_snapshot_and_preserve_energy(road):
    simulated = simulate_customers(road, 5)
    compact, archive = build_service_graph(simulated, simulated.parameters.movement_limit)
    check_service_context(compact, simulated, archive)
    assert len(compact.customer_ids) == 5
    assert compact.charger_ids == road.charger_ids
    for arc in compact.arcs:
        # La fixture es una estrella bidireccional: 0.5 desde/hacia base, 1 entre hojas.
        assert arc.energy_kwh == (0.5 if "base" in (arc.from_node_id, arc.to_node_id) else 1)
    with pytest.raises(ValueError, match="red vial no coincide"):
        check_service_context(compact, road, archive)
