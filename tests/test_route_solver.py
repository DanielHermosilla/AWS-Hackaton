"""Óptimos manuales y casos que una cota oculta de visitas eliminaría."""

from time import monotonic

import pytest

pytest.importorskip("pyscipopt")

from test_model import _instance
from test_operations import charging_case, tiny

from ev_routing.contracts import Operations, SolverConfig
from ev_routing.route_policy import RoutePolicy
from ev_routing.route_solver import solve_routes
from ev_routing.search_policy import SearchConfig
from ev_routing.validation import validate_solution


def check(instance, count, energy, *, optimal=True, seconds=10, **kwargs):
    result = solve_routes(instance, SolverConfig(time_limit_seconds=seconds), **kwargs)
    assert result.solution is not None, result.model_dump()
    report = validate_solution(instance, result.solution, enforce_movement_limit=False)
    assert report.feasible, report.violations
    assert len(result.solution.served_visit_ids) == count, result.model_dump()
    assert result.solution.net_energy_kwh == pytest.approx(energy), result.model_dump()
    assert result.lexicographic_optimal == optimal, {
        "runtime_seconds": result.runtime_seconds,
        "phases": [
            phase.model_dump(include={
                "name", "termination_condition", "incumbent", "best_bound",
                "relative_gap", "proven_optimal", "runtime_seconds",
            })
            for phase in result.phases
        ],
    }
    assert result.search["movement_limit_used"] is None
    assert all(s["native_optimize_seconds"] >= 0 for s in result.search["phases"])
    return result


@pytest.mark.parametrize("h", [1, 3, 10000])
def test_no_h_in_single_tour_or_general_pricing(h):
    simple = tiny()
    simple.parameters.movement_limit = h
    check(simple, 2, 3)
    general = tiny(service_seconds=100, max_route_seconds=250)
    general.parameters.movement_limit = h
    result = check(general, 2, 4)
    assert all(len(r.steps) == 3 for r in result.solution.routes)


@pytest.mark.parametrize("options,count,energy", [
    ({}, 1, 8),
    ({"max_route_seconds": 3419}, 0, 0),
    ({"disabled_charger_ids": ["F"]}, 0, 0),
    ({"final_reserve_soc": .4, "max_route_seconds": 6500}, 1, 8),
])
def test_continuous_partial_charge_time_efficiency_and_final_reserve(options, count, energy):
    instance = charging_case(**options)
    instance.parameters.movement_limit = 1
    check(instance, count, energy)


def test_windows_with_waiting_and_service_completion():
    check(tiny(
        service_seconds=50, max_route_seconds=500, use_customer_time_windows=True,
        customer_time_windows={
            "A": {"open_seconds": 200, "close_seconds": 250},
            "B": {"open_seconds": 0, "close_seconds": 100},
        },
    ), 1, 2)


def test_transit_is_not_service():
    instance = _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit")],
        arcs=[("0", "A", 1), ("A", "B", 1), ("B", "A", 1), ("A", "0", 1)], movements=1,
    )
    instance.arcs = [a.model_copy(update={"travel_time_seconds": 10}) for a in instance.arcs]
    instance.operations = Operations(
        service_seconds_by_customer={"A": 100, "B": 5}, max_route_seconds=50,
        use_customer_time_windows=True,
        customer_time_windows={"A": {"open_seconds": 0, "close_seconds": 0}},
    )
    result = check(instance, 1, 4)
    assert result.solution.served_visit_ids == ["B"]


@pytest.mark.parametrize("arcs,count,energy", [
    ([("0", "j", -8), ("j", "C", 7), ("C", "0", 1)], 1, 4),
    ([("0", "j", 8), ("j", "C", -8), ("C", "0", 1)], 0, 0),
    ([("0", "j", -2), ("j", "0", 0), ("0", "C", 1), ("C", "0", 1)], 1, -4),
    ([("0", "j", 0), ("j", "0", 0), ("0", "C", 1), ("C", "0", 1)], 1, 2),
])
def test_regeneration_saturation_deficit_and_cycles(arcs, count, energy):
    instance = _instance(
        nodes=[("0", "base"), ("j", "junction"), ("C", "visit")],
        arcs=arcs, movements=1,
    )
    check(instance, count, energy)


def test_intermediate_depot_returns():
    check(_instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit")],
        arcs=[("0", "A", 1), ("A", "0", 1), ("0", "B", 1), ("B", "0", 1)],
        movements=1,
    ), 2, 4)


def test_repeated_charger():
    check(_instance(
        nodes=[("0", "base"), ("F", "charger"), ("C", "visit")],
        arcs=[("0", "F", 1), ("F", "C", 4), ("C", "F", 5), ("F", "0", 2)],
        movements=1,
    ), 1, 12)


def test_slow_station_must_be_revisited_and_charge_partially():
    instance = _instance(
        nodes=[("0", "base"), ("S", "charger"), ("F", "charger"), ("C", "visit")],
        arcs=[("0", "S", 4), ("S", "F", 2), ("F", "S", 1), ("S", "C", 7), ("C", "0", 2)],
        movements=1,
    )
    instance.arcs = [a.model_copy(update={"travel_time_seconds": 1}) for a in instance.arcs]
    instance.operations = Operations(
        max_route_seconds=300, include_charging_time=True, charging_efficiency=1,
        charging_power_kw_by_station={"S": 36, "F": 3600},
    )
    result = check(instance, 1, 16)
    stations = [s for s in result.solution.routes[0].steps if s.node_id == "S"]
    assert len(stations) == 2
    assert all(s.charged_to_battery_kwh > 0 for s in stations)
    assert stations[0].battery_departure_kwh < 10


def test_master_integrality_with_fractional_pair_cover_and_subset_rows():
    # Tres rutas de dos clientes a peso 1/2 cuestan 7.5; solución entera 5+4=9.
    instance = _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit"), ("C", "visit")],
        arcs=[(i, j, 2 if "0" in (i, j) else 1)
              for i in ["0", "A", "B", "C"] for j in ["0", "A", "B", "C"] if i != j],
        movements=1, vehicles=2,
    )
    check(instance, 3, 9)
    result = check(instance, 3, 9, search_config=SearchConfig(
        policy="adaptive", bedrock={"model_id": "test", "timeout_seconds": .01},
    ), policy_provider=lambda _: {"policy": {"route_cuts": "none", "columns_per_round": 1}})
    assert all(s["max_columns_added_per_call"] == 1
               for s in result.search["phases"] if s["pricing_calls"])


def test_final_reserve_can_make_even_inactive_vehicle_infeasible():
    instance = tiny(final_reserve_soc=.8)
    result = solve_routes(instance, SolverConfig(time_limit_seconds=2))
    assert result.status == "infeasible"
    assert result.solution is None


def test_one_strategic_call_for_both_phases():
    calls = []

    def provider(request):
        calls.append(request)
        return {"policy": RoutePolicy().model_dump(), "usage": {"totalTokens": 20}}

    result = check(tiny(), 2, 3, search_config=SearchConfig(
        policy="adaptive", bedrock={"model_id": "test", "timeout_seconds": .01}, max_llm_calls=10,
    ), policy_provider=provider)
    assert len(calls) == result.search["controller"]["calls"] == 1
    # Esta reducción puede resolverse en presolve; registrar el plugin no exige
    # crear artificialmente nodos para provocar callbacks.
    assert any(s.get("callback_control") is not None for s in result.search["phases"])


def test_pricing_interruption_cannot_certify_restricted_master(monkeypatch):
    from ev_routing.route_resources import RouteOracle
    original = RouteOracle.advance

    def slow(self):
        deadline = monotonic() + .02
        while monotonic() < deadline:
            pass
        return original(self)

    monkeypatch.setattr(RouteOracle, "advance", slow)
    result = solve_routes(tiny(service_seconds=100, max_route_seconds=250),
                          SolverConfig(time_limit_seconds=.01))
    assert not result.lexicographic_optimal
    assert result.status != "infeasible"
    # El presupuesto también puede vencer reparando el arranque, antes del LP.
    assert not result.search["phases"] or any(
        s["pricing_interrupted"] for s in result.search["phases"]
    )


def test_margin_applied_once():
    check(tiny(energy_margin_fraction=1), 2, 8)


def test_default_service_preparation_does_not_need_h_certificate(tmp_path, capsys):
    import json

    from ev_routing import cli
    from ev_routing.inputs import load_instance, save_instance
    from ev_routing.service_graph import PathArchive, check_service_context

    road = tiny(service_seconds=100, max_route_seconds=250)
    source, target, paths = [tmp_path / f"{name}.json" for name in ("road", "service", "paths")]
    save_instance(road, source)
    assert cli.main([
        "service-graph", "--road-instance", str(source), "--output", str(target),
        "--path-archive", str(paths),
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["service_movements"] is None
    assert not target.with_suffix(".horizon.json").exists()
    compact = load_instance(target)
    check_service_context(compact, road, PathArchive.model_validate_json(paths.read_text()))
    check(compact, 2, 4)


def test_variable_length_road_expansion_and_pipeline():
    from ev_routing.pipeline import run_instance
    from ev_routing.service_graph import build_service_graph

    road = tiny()
    compact, archive = build_service_graph(road, 1)
    result = run_instance(compact, road_instance=road, path_archive=archive)
    assert result["status"] == "optimal"
    assert result["formulation"]["movement_limit_used"] is None
    assert result["validation"]["feasible"]
    assert result["road_validation"]["feasible"]
    assert [len(r["steps"]) for r in result["road_validation"]["routes"]] == [4, 1]
