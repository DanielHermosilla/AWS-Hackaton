"""Caminos dirigidos y auditoría física de la variante entre servicios."""

import json
import random

import networkx as nx
import pytest

from ev_routing import cli, pipeline
from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    ProblemInstance,
    RouteStep,
    Solution,
    SolveResult,
    VehicleRoute,
)
from ev_routing.inputs import load_instance, save_instance
from ev_routing.service_graph import (
    PathArchive,
    build_service_graph,
    check_service_context,
    expand_and_validate,
    fingerprint,
)
from ev_routing.validation import validate_solution


@pytest.fixture
def road():
    # El circuito 0-j-A-B-C-0 consume 8 kWh. Al salir con 6 y reservar 1,
    # hace falta incorporar al menos 3 kWh en C para completarlo.
    return ProblemInstance(
        name="circuito sintético",
        nodes=[
            Node(node_id=node, node_type=kind, connector_types=["J1772"])
            for node, kind in [
                ("0", "base"), ("j", "junction"), ("z", "junction"),
                ("A", "visit"), ("B", "visit"), ("C", "charger"), ("U", "charger"),
            ]
        ],
        arcs=[
            Arc(from_node_id=a, to_node_id=b, energy_kwh=e, distance_m=100 * e)
            for a, b, e in [
                ("0", "j", 1), ("j", "A", 1), ("A", "B", 1), ("B", "C", 1),
                ("C", "0", 4), ("0", "C", 9), ("j", "z", 0), ("z", "j", 0),
            ]
        ],
        parameters=ModelParameters(
            vehicle_count=2, movement_limit=2, battery_capacity_kwh=10, reserve_kwh=1,
        ),
    )


@pytest.fixture
def candidate():
    """Atender solo B aunque se atraviese A; segundo vehículo inactivo."""
    active = VehicleRoute(
        vehicle_id="vehicle_1",
        steps=[
            RouteStep(
                position=0, node_id="0", next_node_id="B",
                battery_arrival_kwh=6, battery_departure_kwh=6,
                predicted_arc_energy_kwh=3, effective_arc_energy_kwh=3,
            ),
            RouteStep(
                position=1, node_id="B", next_node_id="C",
                battery_arrival_kwh=3, battery_departure_kwh=3,
                delivered_visit_ids=["B"],
                predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1,
            ),
            RouteStep(
                position=2, node_id="C", next_node_id="0",
                battery_arrival_kwh=2, charged_to_battery_kwh=3, battery_departure_kwh=5,
                predicted_arc_energy_kwh=4, effective_arc_energy_kwh=4,
            ),
            RouteStep(
                position=3, node_id="0", battery_arrival_kwh=1, battery_departure_kwh=1,
            ),
        ],
        net_energy_kwh=8,
    )
    idle = VehicleRoute(
        vehicle_id="vehicle_2",
        steps=[
            RouteStep(
                position=i, node_id="0", battery_arrival_kwh=6, battery_departure_kwh=6,
                next_node_id="0" if i < 3 else None,
                predicted_arc_energy_kwh=0 if i < 3 else None,
                effective_arc_energy_kwh=0 if i < 3 else None,
            )
            for i in range(4)
        ],
        net_energy_kwh=0,
    )
    return Solution(
        routes=[active, idle], served_visit_ids=["B"], unserved_visit_ids=["A"],
        net_energy_kwh=8,
    )


def test_shortest_directed_paths_preserve_isolated_services_and_handle_zero_cycles(road):
    before = road.model_dump()
    compact, archive = build_service_graph(road, 3)
    assert len(compact.nodes) == 5
    assert compact.customer_ids == ["A", "B"]
    assert compact.charger_ids == ["C", "U"]
    assert len(compact.arcs) == 12
    arcs = {(a.from_node_id, a.to_node_id): a for a in compact.arcs}
    paths = {(p.from_node_id, p.to_node_id): p.node_ids for p in archive.paths}
    assert arcs["0", "C"].energy_kwh == 4  # El arco directo cuesta 9.
    assert arcs["C", "0"].energy_kwh == 4
    assert arcs["0", "B"].energy_kwh == 3
    assert arcs["B", "0"].energy_kwh == 5  # No inventar reversibilidad.
    assert paths["0", "B"] == ["0", "j", "A", "B"]
    assert not any("U" in pair for pair in arcs)
    assert all(len(p.node_ids) == len(set(p.node_ids)) for p in archive.paths)
    assert compact.parameters.movement_limit == 3
    assert road.model_dump() == before
    check_service_context(compact, road, archive)


def test_minimum_energy_path_can_be_longer_than_the_shortest_distance(road):
    # El arco directo mide 1 m pero cuesta 9 kWh. El camino de cuatro
    # calles mide 400 m y cuesta 4 kWh: el peso debe ser energía, no distancia.
    next(a for a in road.arcs if (a.from_node_id, a.to_node_id) == ("0", "C")).distance_m = 1
    compact, archive = build_service_graph(road, 3)
    arc = next(a for a in compact.arcs if (a.from_node_id, a.to_node_id) == ("0", "C"))
    path = next(p for p in archive.paths if (p.from_node_id, p.to_node_id) == ("0", "C"))
    assert arc.energy_kwh == 4
    assert arc.distance_m == 400
    assert path.node_ids == ["0", "j", "A", "B", "C"]


def test_zero_energy_streets_are_edges_including_a_complete_zero_energy_path(road):
    for arc in road.arcs:
        if (arc.from_node_id, arc.to_node_id) in {("0", "j"), ("j", "A")}:
            arc.energy_kwh = 0
    compact, archive = build_service_graph(road, 3)
    arcs = {(a.from_node_id, a.to_node_id): a for a in compact.arcs}
    paths = {(p.from_node_id, p.to_node_id): p.node_ids for p in archive.paths}
    assert arcs["0", "A"].energy_kwh == 0
    assert paths["0", "A"] == ["0", "j", "A"]
    assert arcs["A", "0"].energy_kwh == 6  # Conservar el sentido de circulación.


@pytest.mark.parametrize("only_depot", [False, True])
def test_empty_road_preserves_services_without_inventing_connections(only_depot):
    nodes = [Node(node_id="depósito", node_type="base")]
    if not only_depot:
        nodes.extend([
            Node(node_id="cliente sin calles", node_type="visit"),
            Node(node_id="cargador/aislado", node_type="charger"),
        ])
    road = ProblemInstance(nodes=nodes, arcs=[])
    compact, archive = build_service_graph(road, 1)
    assert compact.nodes == road.nodes
    assert compact.arcs == archive.paths == []
    check_service_context(compact, road, archive)


@pytest.mark.parametrize("seed", range(5))
def test_contraction_matches_exhaustive_simple_path_energy(seed):
    # Enumerar todas las rutas simples en redes pequeñas es un oráculo
    # independiente de Dijkstra. Con energías no negativas existe un mínimo
    # simple, incluso cuando hay ciclos de costo cero.
    rng = random.Random(seed)
    nodes = [
        Node(node_id=name, node_type=kind)
        for name, kind in [
            ("base/α", "base"), ("cliente-17", "visit"), ("carga:X", "charger"),
            ("cruce a", "junction"), ("cruce b", "junction"), ("sumidero", "visit"),
            ("aislado", "charger"),
        ]
    ]
    arcs = [
        Arc(
            from_node_id=a.node_id, to_node_id=b.node_id,
            energy_kwh=rng.choice([0, 0.125, 1.5, 3]),
            distance_m=rng.randint(1, 100),
        )
        for a in nodes[:5] for b in nodes[:6]
        if a != b and rng.random() < 0.4
    ]
    road = ProblemInstance(nodes=nodes, arcs=arcs)
    graph = nx.DiGraph()
    graph.add_nodes_from(n.node_id for n in nodes)
    graph.add_edges_from((a.from_node_id, a.to_node_id) for a in arcs)
    energy = {(a.from_node_id, a.to_node_id): a.energy_kwh for a in arcs}
    compact, archive = build_service_graph(road, 4)
    actual = {(a.from_node_id, a.to_node_id): a.energy_kwh for a in compact.arcs}
    expected = {}
    for source in compact.nodes:
        for target in compact.nodes:
            if source == target:
                continue
            totals = [
                sum(energy[pair] for pair in zip(path, path[1:]))
                for path in nx.all_simple_paths(graph, source.node_id, target.node_id)
            ]
            if totals:
                expected[source.node_id, target.node_id] = min(totals)
    assert actual == expected
    for path in archive.paths:
        assert len(path.node_ids) == len(set(path.node_ids))
        assert sum(energy[pair] for pair in zip(path.node_ids, path.node_ids[1:])) == (
            expected[path.from_node_id, path.to_node_id]
        )


@pytest.mark.parametrize("h", [0, -1, 2.5, True])
def test_service_horizon_must_be_positive_integer(road, h):
    with pytest.raises(ValueError, match="service_movements"):
        build_service_graph(road, h)


def test_rejects_regeneration_instead_of_hiding_intermediate_deficits(road):
    road.arcs[0].energy_kwh = -1
    with pytest.raises(ValueError, match="regeneración"):
        build_service_graph(road, 3)


def test_rejects_reducing_a_reduced_instance(road):
    compact, _ = build_service_graph(road, 3)
    with pytest.raises(ValueError, match="red vial original"):
        build_service_graph(compact, 3)


@pytest.mark.parametrize("corruption", ["road", "compact", "missing", "duplicate", "physics"])
def test_context_rejects_stale_or_inconsistent_snapshots(road, corruption):
    compact, archive = build_service_graph(road, 3)
    if corruption == "road":
        road.arcs[0].energy_kwh += 1
    elif corruption == "compact":
        compact.parameters.movement_limit += 1
    elif corruption == "missing":
        archive.paths.pop()
    elif corruption == "duplicate":
        archive.paths.append(archive.paths[0])
    else:
        compact.parameters.battery_capacity_kwh = 11
        archive.service_instance_sha256 = fingerprint(compact)
    with pytest.raises(ValueError):
        check_service_context(compact, road, archive)


def test_expansion_checks_every_street_and_preserves_transit_charge_and_idle_vehicle(road, candidate):
    before = road.model_dump()
    compact, archive = build_service_graph(road, 3)
    assert validate_solution(compact, candidate).feasible
    expanded, report, counts = expand_and_validate(compact, road, archive, candidate)
    assert report.feasible, report.violations
    assert all(report.checks.values())
    assert counts == {"vehicle_1": 5, "vehicle_2": 0}
    assert [s.node_id for s in expanded.routes[0].steps] == ["0", "j", "A", "B", "C", "0"]
    assert expanded.routes[0].steps[2].delivered_visit_ids == []
    assert expanded.routes[0].steps[3].delivered_visit_ids == ["B"]
    assert expanded.routes[0].steps[4].charged_to_battery_kwh == 3
    assert all(s.node_id == "0" for s in expanded.routes[1].steps)
    assert expanded.net_energy_kwh == 8
    assert road.model_dump() == before
    assert not validate_solution(road, expanded).feasible  # Supera H vial original.
    assert len(candidate.routes[0].steps) == 4  # No alterar el incumbente.


@pytest.mark.parametrize("corruption", ["endpoint", "street", "energy", "distance"])
def test_expansion_rejects_broken_or_mismatched_road_paths(road, candidate, corruption):
    compact, archive = build_service_graph(road, 3)
    path = next(p for p in archive.paths if (p.from_node_id, p.to_node_id) == ("0", "B"))
    if corruption == "endpoint":
        path.node_ids[0] = "C"
    elif corruption == "street":
        path.node_ids = ["0", "B"]
    else:
        arc = next(a for a in compact.arcs if (a.from_node_id, a.to_node_id) == ("0", "B"))
        if corruption == "energy":
            arc.energy_kwh += 1
        else:
            arc.distance_m += 1
        archive.service_instance_sha256 = fingerprint(compact)
    with pytest.raises(ValueError):
        expand_and_validate(compact, road, archive, candidate)


def test_pipeline_requires_audit_context_before_calling_solver(road, monkeypatch):
    compact, _ = build_service_graph(road, 3)

    def forbidden(*args):
        pytest.fail("No resolver sin poder comprobar las calles")

    monkeypatch.setattr(pipeline, "solve_instance", forbidden)
    with pytest.raises(ValueError, match="--road-instance"):
        pipeline.run_instance(compact)


@pytest.mark.parametrize("broken", [False, True])
def test_pipeline_separates_physical_validation_from_original_h(road, candidate, monkeypatch, broken):
    compact, archive = build_service_graph(road, 3)
    if broken:
        path = next(p for p in archive.paths if (p.from_node_id, p.to_node_id) == ("0", "B"))
        path.node_ids = ["0", "B"]
    monkeypatch.setattr(
        pipeline, "solve_instance",
        lambda *args: SolveResult(
            requested_solver="auto", used_solver="gurobi",
            status="feasible", solution=candidate,
        ),
    )
    result = pipeline.run_instance(compact, road_instance=road, path_archive=archive)
    if broken:
        assert result["status"] == "invalid_solution"
        assert not result["validation"]["feasible"]
        assert result["kpis"]["served_deliveries"] is None
        assert not result["road_validation"]["feasible"]
    else:
        assert result["status"] == "feasible"
        assert result["validation"]["feasible"]
        assert result["road_validation"]["feasible"]
        assert not result["road_validation"]["within_original_movement_limit"]
        assert result["road_validation"]["road_movement_counts"]["vehicle_1"] == 5
        assert result["kpis"]["served_deliveries"] == 1
        assert result["kpis"]["net_battery_energy_kwh"] == 8


@pytest.mark.solver
def test_public_cli_preserves_all_services_and_solves_known_recharge_optimum(
    road, tmp_path, capsys
):
    source, compact, archive, result = [
        tmp_path / name for name in ["road.json", "service.json", "paths.json", "result.json"]
    ]
    save_instance(road, source)
    assert cli.main([
        "service-graph", "--road-instance", str(source), "--service-movements", "4",
        "--output", str(compact), "--path-archive", str(archive),
    ]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert (prepared["nodes"], prepared["deliveries"], prepared["chargers"]) == (5, 2, 2)
    assert (prepared["road_nodes"], prepared["road_arcs"]) == (len(road.nodes), len(road.arcs))
    assert prepared["preprocessing_seconds"] >= 0
    assert prepared["shortest_path_algorithm"] == "scipy.sparse.csgraph.dijkstra"
    assert prepared["unreachable_ordered_service_pairs"] == 8
    check_service_context(
        load_instance(compact), load_instance(source),
        PathArchive.model_validate_json(archive.read_text()),
    )
    code = cli.main([
        "run", "--instance", str(compact), "--road-instance", str(source),
        "--path-archive", str(archive), "--time-limit-seconds", "15", "--output", str(result),
    ])
    answer = json.loads(result.read_text())
    if answer["status"] == "unavailable":
        pytest.skip(answer["solve"]["message"])
    assert code == 0, capsys.readouterr()
    assert answer["solve"]["lexicographic_optimal"]
    assert answer["kpis"]["served_deliveries"] == 2
    assert answer["kpis"]["net_battery_energy_kwh"] == pytest.approx(8)
    assert answer["road_validation"]["feasible"]
    assert answer["parameters"]["movement_limit"] == 4
    assert load_instance(source).parameters.movement_limit == 2
