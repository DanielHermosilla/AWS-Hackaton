"""Pruebas de equivalencia física y de óptimos contra la red sin comprimir."""

import hashlib
import json
import random
from itertools import product
from time import monotonic

import pytest

from ev_routing.contracts import (
    Arc,
    BatteryProfile,
    ModelParameters,
    Node,
    Operations,
    ProblemInstance,
    SolverConfig,
)
from ev_routing.inputs import load_instance, save_instance
from ev_routing.pipeline import run_instance
from ev_routing.resource_graph import compose_profiles, prepare_service_graph, profile_dominates
from ev_routing.route_resources import RouteOracle, assemble_solution, route_from_walk
from ev_routing.service_graph import (
    PathArchive,
    build_service_graph,
    check_service_context,
    expand_and_validate,
    fingerprint,
)
from ev_routing.validation import validate_solution


def instance(arcs, *, nodes=None, **options):
    if nodes is None:
        nodes = [("0", "base"), ("j", "junction"), ("C", "visit")]
    return ProblemInstance(
        name="synthetic-resource-paths",
        nodes=[Node(node_id=n, node_type=k, connector_types=["J1772"]) for n, k in nodes],
        arcs=[
            Arc(from_node_id=a, to_node_id=b, energy_kwh=e, distance_m=100,
                travel_time_seconds=t)
            for a, b, e, t in arcs
        ],
        parameters=ModelParameters(
            battery_capacity_kwh=10, reserve_kwh=1, vehicle_count=1, movement_limit=1,
        ),
        operations=Operations(**options),
    )


def window_case():
    return instance([
        ("0", "j", .5, 600), ("j", "C", .5, 600),
        ("0", "C", 2, 600), ("C", "0", 1, 300),
    ], service_seconds=60, max_route_seconds=3600, use_customer_time_windows=True,
        customer_time_windows={"C": {"open_seconds": 0, "close_seconds": 900}})


def exhaust(road):
    oracle = RouteOracle(road, road.vehicle_ids[0])
    oracle.exhaust(monotonic() + 5)
    assert oracle.complete, f"Oráculo incompleto tras {oracle.expanded} etiquetas"
    for route in oracle.routes.values():
        solution = assemble_solution(road, [route])
        report = validate_solution(road, solution, enforce_movement_limit=False)
        assert report.feasible, report.violations
    return oracle


def compare(road, **kwargs):
    compact, archive = prepare_service_graph(road, **kwargs)
    check_service_context(compact, road, archive)
    original, reduced = exhaust(road), exhaust(compact)
    assert set(reduced.routes) == set(original.routes)
    for mask, route in reduced.routes.items():
        assert route.net_energy_kwh == pytest.approx(original.routes[mask].net_energy_kwh)
        _, report, _ = expand_and_validate(
            compact, road, archive, assemble_solution(compact, [route]), without_h=True,
        )
        assert report.feasible, report.violations
    return compact, archive, reduced


def test_profiles_against_independent_segment_replay():
    # Enumerar signos, saturación, déficits y distintos SoC. No comparar contra
    # otra llamada a las funciones que construyen/propagan el perfil.
    checked = 0
    for length in range(1, 5):
        for energies in product((-6, -2, 0, 2, 6), repeat=length):
            profile = BatteryProfile(
                consumption_kwh=0, minimum_departure_kwh=1, maximum_arrival_kwh=10,
            )
            for energy in energies:
                if profile is not None:
                    profile = compose_profiles(profile, BatteryProfile(
                        consumption_kwh=energy, minimum_departure_kwh=max(1, 1 + energy),
                        maximum_arrival_kwh=min(10, 10 - energy),
                    ), 10)
            for start in (1 + .5 * i for i in range(19)):
                battery, feasible = start, True
                for energy in energies:
                    battery = min(10, battery - energy)
                    feasible &= battery >= 1
                accepted = profile is not None and start >= profile.minimum_departure_kwh
                assert accepted == feasible, (energies, start)
                if accepted:
                    assert battery == min(
                        start - profile.consumption_kwh, profile.maximum_arrival_kwh,
                    )
                checked += 1
    assert checked == 14820


def test_dominance_must_hold_at_all_departure_batteries():
    # [-4,+4] es accesible con batería baja pero satura; [+4,-4]
    # exige al menos 5 y conserva más batería. No se pueden unificar.
    low = BatteryProfile(
        consumption_kwh=0, minimum_departure_kwh=1, maximum_arrival_kwh=6,
    )
    high = BatteryProfile(
        consumption_kwh=0, minimum_departure_kwh=5, maximum_arrival_kwh=10,
    )
    assert not profile_dominates(low, high, 10)
    assert not profile_dominates(high, low, 10)


def test_window_keeps_fast_alternative_and_fixes_dijkstra_counterexample():
    road = window_case()
    old, _ = build_service_graph(road, 1)
    assert set(exhaust(old).routes) == {0}
    compact, _, oracle = compare(road)
    assert oracle.routes[1].net_energy_kwh == 3
    alternatives = [a for a in compact.arcs if a.from_node_id == "0" and a.to_node_id == "C"]
    assert len(alternatives) == 2
    assert len({a.arc_id for a in alternatives}) == 2
    assert {a.travel_time_seconds for a in alternatives} == {600, 1200}


@pytest.mark.parametrize("arcs,energy", [
    ([("0", "j", -6, 1), ("j", "C", 4, 1), ("C", "0", 1, 1)], 1),
    ([("0", "j", 6, 1), ("j", "C", -5, 1), ("C", "0", 1, 1)], None),
    ([("0", "j", -2, 1), ("j", "0", 0, 1), ("0", "C", 1, 1), ("C", "0", 1, 1)], -4),
    ([("0", "j", 0, 1), ("j", "0", 0, 1), ("0", "C", 1, 1), ("C", "0", 1, 1)], 2),
])
def test_saturation_deficit_and_useful_or_useless_cycles(arcs, energy):
    road = instance(arcs, max_route_seconds=60)
    compact, _, oracle = compare(road)
    if energy is None:
        assert set(oracle.routes) == {0}
    else:
        assert oracle.routes[1].net_energy_kwh == energy
    if energy == -4:
        assert any(a.from_node_id == a.to_node_id == "0" for a in compact.arcs)


def test_margin_is_applied_per_segment_once_even_with_negative_total():
    road = instance([
        ("0", "j", -6, 1), ("j", "C", 4, 1), ("C", "0", 1, 1),
    ], energy_margin_fraction=.2, max_route_seconds=60)
    compact, _, oracle = compare(road)
    path = next(a for a in compact.arcs if a.to_node_id == "C")
    assert path.energy_kwh == -2
    assert path.battery_profile.consumption_kwh == pytest.approx(-1.2)
    assert oracle.routes[1].net_energy_kwh == pytest.approx(2)


@pytest.mark.parametrize("junction", [False, True])
def test_decimal_reserve_boundary_does_not_reject_a_valid_snapshot(junction):
    road = instance(
        [("0", "j", 21.6, 1), ("j", "C", -21.6, 1), ("C", "0", 0, 1)]
        if junction else [("0", "C", 21.6, 1), ("C", "0", -21.6, 1)],
        nodes=[("0", "base"), ("C", "visit"), *([("j", "junction")] if junction else [])],
    )
    road.parameters = ModelParameters(
        vehicle_count=1, battery_capacity_kwh=24, reserve_kwh=2.4, initial_soc=1,
    )
    compact, _, oracle = compare(road)
    assert oracle.routes[1].net_energy_kwh == pytest.approx(0)
    assert compact.parameters.reserve_kwh == 2.4
    assert compact.arcs[0].battery_profile.maximum_arrival_kwh == 24 - 21.6
    if junction:
        assert compact.provenance["representation"]["roundoff_retained_junctions"] == 1


def test_known_times_survive_when_another_street_has_no_time_and_timing_is_disabled():
    road = instance(
        [("0", "C", -2, 50), ("C", "0", 1, None)],
        nodes=[("0", "base"), ("C", "visit")],
    )
    compact, archive = prepare_service_graph(road)
    check_service_context(compact, road, archive)
    times = {(a.from_node_id, a.to_node_id): a.travel_time_seconds for a in compact.arcs}
    assert times == {("0", "C"): 50, ("C", "0"): None}


@pytest.mark.parametrize("kwargs", [
    {"preprocessing_seconds": 0}, {"max_pair_expansions": 0},
    {"max_pair_expansions": 1}, {"max_pair_expansions": 64},
])
def test_partial_contraction_preserves_all_routes_instead_of_truncating_labels(kwargs):
    compact, _, oracle = compare(window_case(), **kwargs)
    assert compact.provenance["representation"]["road_optimum_preserved"]
    assert oracle.routes[1].net_energy_kwh == 3
    if kwargs.get("preprocessing_seconds") == 0 or kwargs.get("max_pair_expansions") == 0:
        assert "j" in {n.node_id for n in compact.nodes}


def test_regenerative_cycle_at_retained_junction_is_not_deleted():
    road = instance([
        ("0", "a", 1, 1), ("a", "j", -2, 1), ("j", "a", 0, 1),
        ("a", "C", 1, 1), ("C", "0", 1, 1),
    ], nodes=[("0", "base"), ("a", "junction"), ("j", "junction"), ("C", "visit")],
        max_route_seconds=60)
    compact, _, _ = compare(road)
    assert any(n.node_type == "junction" for n in compact.nodes)
    assert any(a.from_node_id == a.to_node_id for a in compact.arcs)


def test_partial_charging_service_transit_and_repeated_station():
    road = instance([
        ("0", "j", -2, 1), ("j", "F", 3, 1), ("F", "C", 4, 1),
        ("C", "F", 5, 1), ("F", "0", 2, 1),
    ], nodes=[("0", "base"), ("j", "junction"), ("F", "charger"), ("C", "visit")],
        max_route_seconds=80, include_charging_time=True, charging_power_kw=360,
        service_seconds=5, use_customer_time_windows=True,
        customer_time_windows={"C": {"open_seconds": 10, "close_seconds": 200}})
    _, _, oracle = compare(road)
    route = oracle.routes[1]
    charges = [s.charged_to_battery_kwh for s in route.steps]
    assert sum(charges) == pytest.approx(7)
    assert route.net_energy_kwh == pytest.approx(12)
    assert sum(s.node_id == "F" for s in route.steps) == 2


@pytest.mark.parametrize("seed", range(12))
def test_random_small_graphs_match_full_road_oracle(seed):
    rng = random.Random(seed)
    names = ["0", "A", "B", "j", "k"]
    potentials = {name: rng.randrange(-2, 3) for name in names}
    edges = []
    for a, b in product(names, repeat=2):
        if a != b and rng.random() < .5:
            # Coste reducido positivo -> sin ciclos negativos; sí calles negativas.
            edges.append((a, b, rng.randrange(1, 4) + potentials[b] - potentials[a],
                          rng.randrange(1, 6)))
    road = instance(
        edges, nodes=[("0", "base"), ("A", "visit"), ("B", "visit"),
                      ("j", "junction"), ("k", "junction")],
        max_route_seconds=25, service_seconds=1, use_customer_time_windows=True,
        customer_time_windows={"A": {"open_seconds": 3, "close_seconds": 15}},
    )
    compare(road)


def test_cache_scenario_invalidation_and_archive_tampering(tmp_path):
    road = window_case()
    first, archive = prepare_service_graph(road, cache_directory=tmp_path)
    second, second_archive = prepare_service_graph(road, cache_directory=tmp_path)
    assert second.provenance["preprocessing_cache"]["hit"]
    check_service_context(second, road, second_archive)
    assert first.arcs == second.arcs
    changed = road.operations.model_copy(update={"energy_margin_fraction": .1})
    third, _ = prepare_service_graph(road, operations=changed, cache_directory=tmp_path)
    assert not third.provenance["preprocessing_cache"]["hit"]
    assert len(list(tmp_path.glob("*.json"))) == 2
    first.arcs[0].battery_profile.maximum_arrival_kwh -= .5
    archive.service_instance_sha256 = fingerprint(first)
    with pytest.raises(ValueError, match="perfil de batería"):
        check_service_context(first, road, archive)


def test_legacy_fingerprints_are_unchanged_by_optional_arc_fields():
    road = window_case()
    old = road.model_dump_json(exclude={"arcs": {"__all__": {"arc_id", "battery_profile"}}})
    assert fingerprint(road) == hashlib.sha256(old.encode()).hexdigest()


def test_validator_detects_intermediate_deficit_and_ambiguous_path_id():
    road = instance([("0", "j", 6, 1), ("j", "C", -5, 1), ("C", "0", 1, 1)])
    compact, _ = prepare_service_graph(road)
    keys = [next(a.arc_id for a in compact.arcs if a.to_node_id == target) for target in ["C", "0"]]
    route = route_from_walk(compact, "vehicle_1", ["0", "C", "0"], [1], [0, 0, 0], arc_ids=keys)
    solution = assemble_solution(compact, [route])
    report = validate_solution(compact, solution, enforce_movement_limit=False)
    assert not report.feasible
    assert any("intermedia" in message for message in report.violations)
    route.steps[0].arc_id = None
    report = validate_solution(compact, solution, enforce_movement_limit=False)
    assert not report.feasible


def test_cli_applies_windows_before_selecting_paths_and_cache(tmp_path, capsys):
    from ev_routing.cli import main

    road = window_case().model_copy(update={"operations": Operations()})
    source, target, paths, config = (tmp_path / f"{name}.json" for name in ["road", "compact", "paths", "config"])
    save_instance(road, source)
    config.write_text(json.dumps({"operations": window_case().operations.model_dump()}))
    args = [
        "service-graph", "--road-instance", str(source), "--output", str(target),
        "--path-archive", str(paths), "--config", str(config),
        "--cache-directory", str(tmp_path / "cache"),
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["preprocessing"]["kind"] == "resource_paths"
    compact = load_instance(target)
    archive = PathArchive.model_validate_json(paths.read_text())
    check_service_context(compact, road, archive)
    assert exhaust(compact).routes[1].net_energy_kwh == 3
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["cache"]["hit"]


@pytest.mark.solver
@pytest.mark.parametrize("case,expected", [("window", 3), ("regeneration", 1)])
def test_scip_pipeline_certifies_and_expands_selected_paths(case, expected):
    pytest.importorskip("pyscipopt")
    road = window_case() if case == "window" else instance([
        ("0", "j", -6, 1), ("j", "C", 4, 1), ("C", "0", 1, 1),
    ])
    compact, archive = prepare_service_graph(road)
    result = run_instance(
        compact, SolverConfig(time_limit_seconds=5),
        road_instance=road, path_archive=archive,
    )
    assert result["status"] == "optimal", result["solve"]
    assert result["solve"]["lexicographic_optimal"]
    assert result["kpis"]["served_deliveries"] == 1
    assert result["kpis"]["net_battery_energy_kwh"] == expected
    assert result["validation"]["feasible"]
    assert result["road_validation"]["feasible"]
    assert result["formulation"]["movement_limit_used"] is None


def test_legacy_backends_reject_profiles_instead_of_ignoring_them():
    from ev_routing.model import build_model
    from ev_routing.solve import solve_instance

    compact, _ = prepare_service_graph(window_case())
    with pytest.raises(ValueError, match="scip-routes"):
        build_model(compact)
    with pytest.raises(ValueError, match="scip-routes"):
        solve_instance(compact, SolverConfig(solver="gurobi"))
