"""Decisiones ejecutadas, presupuesto, certificados y testigos independientes."""

from time import monotonic

import pytest
from test_model import _instance

from ev_routing.contracts import SolverConfig
from ev_routing.route_heuristics import InsertionRoutes
from ev_routing.route_orchestrator import RouteOrchestrator
from ev_routing.route_policy import RoutePolicy
from ev_routing.route_relaxation import energy_relaxation
from ev_routing.route_solver import solve_routes
from ev_routing.search_policy import SearchConfig
from ev_routing.validation import validate_solution


def pairs():
    return _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit"), ("C", "visit")],
        arcs=[(i, j, 2 if "0" in (i, j) else 1)
              for i in ["0", "A", "B", "C"] for j in ["0", "A", "B", "C"] if i != j],
        movements=1, vehicles=2,
    )


def test_two_real_decision_stages_change_executed_native_parameters():
    calls = []

    def provider(request):
        calls.append(request)
        return {"policy": (
            {"seed_starts": 3, "seed_charging": False, "epoch_seconds": .1}
            if request["event"] == "before_search" else
            {"scip_parameters": {"lp/initalgorithm": "d"}, "pricing_heuristic_starts": 6}
        ), "usage": {"totalTokens": 10}}

    instance = pairs()
    original = instance.model_dump_json()
    result = solve_routes(instance, SolverConfig(time_limit_seconds=5), SearchConfig(
        policy="adaptive", max_llm_calls=2,
        bedrock={"model_id": "double", "timeout_seconds": .01},
    ), policy_provider=provider)
    assert [r["event"] for r in calls] == ["before_search", "after_seed"]
    assert calls[1]["state"]["deliveries"] == 3
    assert result.search["controller"]["calls"] == 2
    assert result.search["controller"]["callback_calls"] > 0
    assert instance.model_dump_json() == original
    assert result.lexicographic_optimal
    assert result.solution.net_energy_kwh == pytest.approx(9)
    assert validate_solution(instance, result.solution, enforce_movement_limit=False).feasible
    assert any(s["physical_oracles"] == 1 for s in result.search["phases"])
    assert all(s["native_parameter_changes"]["lp/initalgorithm"]["after"] == "d"
               for s in result.search["phases"])


def test_invalid_later_proposal_preserves_previous_policy_and_call_budget():
    config = SearchConfig(
        policy="adaptive", max_llm_calls=2, decision_interval_seconds=0,
        bedrock={"model_id": "double", "timeout_seconds": .01},
    )
    replies = iter([
        {"policy": {"seed_starts": 11}},
        {"policy": {"seed_starts": 1, "scip_parameters": {"limits/time": 100000}}},
    ])
    controller = RouteOrchestrator(config, {}, monotonic()+30, 30, lambda _: next(replies))
    controller.decide("before_search", {})
    controller.decide("after_seed", {})
    controller.decide("search_stagnation", {})
    assert controller.policy.seed_starts == 11
    assert controller.report()["calls"] == 2
    assert controller.report()["status"] == "partial_fallback"
    assert [r["status"] for r in controller.records] == ["applied", "rejected"]


def test_expired_response_is_recorded_but_not_applied(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("ev_routing.route_orchestrator.monotonic", lambda: clock[0])

    def provider(_):
        clock[0] = 100
        return {"policy": {"seed_starts": 64}, "usage": {"totalTokens": 1}}

    config = SearchConfig(policy="adaptive", bedrock={"model_id": "double", "timeout_seconds": .01})
    controller = RouteOrchestrator(config, {}, 10, 10, provider)
    controller.decide("before_search", {})
    assert controller.policy.seed_starts == RoutePolicy().seed_starts
    assert controller.records[0]["status"] == "not_applied"
    assert controller.records[0]["usage"]["totalTokens"] == 1


def test_inference_time_allocation_blocks_unbudgeted_calls():
    config = SearchConfig(policy="adaptive", bedrock={"model_id": "double", "timeout_seconds": 8})
    controller = RouteOrchestrator(config, {}, monotonic()+10, 10, lambda _: pytest.fail("unbudgeted"))
    controller.decide("before_search", {})
    assert controller.report()["calls"] == 0
    assert controller.report()["skipped_events"][0]["reason"] == "insufficient_inference_budget"


def test_seed_and_local_search_preserve_directed_costs_and_manual_optimum():
    instance = pairs()
    constructor = InsertionRoutes(instance)
    seed = constructor.seed("regret_insertion", 4, monotonic()+1)
    result = constructor.improve(seed, RoutePolicy(), monotonic()+1)
    assert len(result.served_visit_ids) == 3
    assert result.net_energy_kwh == pytest.approx(9)
    assert validate_solution(instance, result, enforce_movement_limit=False).feasible


def test_relaxation_bound_does_not_require_original_triangle_inequality():
    instance = _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit"), ("F", "charger")],
        arcs=[("0", "A", 2), ("A", "0", 2), ("0", "B", 2), ("B", "0", 2),
              ("A", "B", 100), ("B", "A", 100), ("A", "F", 1), ("F", "A", 1),
              ("B", "F", 1), ("F", "B", 1)],
        movements=1, initial_soc=1,
    )
    report = energy_relaxation(instance, SolverConfig(), RoutePolicy(), monotonic()+2,
                               complete_service=True)
    # El recorrido 0-A-F-B-0 cuesta 6; el arco directo de 100 no justifica una cota mayor.
    assert report["applicable"]
    assert report["bound_kwh"] <= 6
    assert report["bound_kwh"] == pytest.approx(6, abs=1e-7)


def test_all_customer_relaxation_is_not_used_when_only_some_are_served():
    report = energy_relaxation(pairs(), SolverConfig(), RoutePolicy(), monotonic()+2,
                               complete_service=False)
    assert not report["applicable"]


def test_partial_charging_seed_is_valid_but_not_an_optimality_certificate():
    nodes = [("0", "base"), ("A", "visit"), ("B", "visit"), ("F", "charger")]
    instance = _instance(
        nodes=nodes, arcs=[(a, b, 2) for a, _ in nodes for b, _ in nodes if a != b],
        movements=1,
    )
    result = InsertionRoutes(instance).charging_seed(3, monotonic()+1)
    assert result is not None
    assert len(result.served_visit_ids) == 2
    assert result.net_energy_kwh == pytest.approx(8)
    assert sum(s.charged_to_battery_kwh for r in result.routes for s in r.steps) == pytest.approx(3)
    assert validate_solution(instance, result, enforce_movement_limit=False).feasible
