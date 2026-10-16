"""Regresiones independientes de ventanas, pricing y etapas consumidas del LLM."""

from itertools import permutations
from random import Random
from threading import Event
from time import monotonic

import pytest
from test_resource_graph import instance
from test_route_orchestration import pairs

from ev_routing.contracts import SolverConfig, TimeWindow
from ev_routing.llm_head import LLMHead
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.route_hybrid import HybridRoutes
from ev_routing.route_policy import RoutePolicy
from ev_routing.route_pricing import PricingNetwork, ReducedCostOracle, SequenceOracle
from ev_routing.route_resources import RouteOracle
from ev_routing.route_schedule import FixedPathRepair
from ev_routing.route_solver import _phase, solve_routes
from ev_routing.search_policy import SearchConfig
from ev_routing.synthetic_benchmark import comparisons, select_fixed
from ev_routing.validation import validate_solution


def timed_case(seed):
    rng = Random(seed)
    road = instance(
        [("0", "A", 2, 2), ("A", "0", 1, 2), ("0", "B", 1, 3),
         ("B", "0", 2, 2), ("A", "B", -.5 if seed % 2 else .5, 1),
         ("B", "A", 1, 1)],
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit")],
        max_route_seconds=12, service_seconds=1,
    )
    road.operations.use_customer_time_windows = True
    road.operations.customer_time_windows = {
        "A": TimeWindow(open_seconds=0, close_seconds=rng.uniform(3, 9)),
        "B": TimeWindow(open_seconds=2, close_seconds=rng.uniform(4, 11)),
    }
    return road


@pytest.mark.parametrize("seed", range(6))
def test_time_reachability_reduced_cost_bound_matches_full_enumeration(seed):
    graph, _ = prepare_service_graph(timed_case(seed))
    full = RouteOracle(graph, graph.vehicle_ids[0])
    full.exhaust(monotonic() + 3)
    assert full.complete
    rng = Random(seed)
    rewards, convex = [rng.uniform(-2, 10), rng.uniform(-2, 10)], rng.uniform(-2, 3)
    cuts = [(3, rng.uniform(-3, 3))]
    for energy_weight in [0, 1]:
        def reduced(mask, route):
            return energy_weight * route.net_energy_kwh - convex - sum(
                p for i, p in enumerate(rewards) if mask & (1 << i)
            ) - sum(value * ((mask & subset).bit_count() // 2) for subset, value in cuts)
        expected = {m: reduced(m, r) for m, r in full.routes.items() if reduced(m, r) < -1e-7}
        query = ReducedCostOracle(graph, graph.vehicle_ids[0], rewards, cuts, convex,
                                  energy_weight, 1e-7, PricingNetwork(graph))
        query.exhaust(monotonic() + 3)
        assert query.complete
        actual = {m: reduced(m, r) for m, r in query.routes.items() if reduced(m, r) < -1e-7}
        assert actual == pytest.approx(expected)


@pytest.mark.parametrize("seed", range(4))
def test_sequence_time_bounds_preserve_exact_routes_and_energy(seed):
    road = timed_case(seed)
    for order in permutations(road.customer_ids):
        # Referencia sin los descartes de tiempo/escape ni la cola de SequenceOracle.
        class FixedOrderReference(RouteOracle):
            def _service(self, label):
                target = order[label.mask.bit_count()] if label.mask.bit_count() < len(order) else None
                for mask, services, resources in super()._service(label):
                    if mask == label.mask or label.walk[-1] == target:
                        yield mask, services, resources
        reference = FixedOrderReference(road, road.vehicle_ids[0])
        reference.exhaust(monotonic() + 3)
        assert reference.complete
        query = SequenceOracle(road, road.vehicle_ids[0], order, PricingNetwork(road))
        query.exhaust(monotonic() + 3)
        assert query.complete
        target = query.target_mask
        assert (target in query.routes) == (target in reference.routes)
        if target in reference.routes:
            assert query.routes[target].net_energy_kwh == pytest.approx(
                reference.routes[target].net_energy_kwh
            )


def test_window_seed_serves_urgent_customer_before_near_flexible_customers():
    # Todos caben en batería. Los clientes cercanos distraían al vecino más
    # próximo: atender primero A deja fuera C, cuyo cierre es 5.
    road = instance([
        ("0", "A", 1, 1), ("A", "0", 1, 1),
        ("0", "C", 2, 2), ("C", "0", 2, 2),
        ("A", "C", 1, 4), ("C", "A", 1, 1),
    ], nodes=[("0", "base"), ("A", "visit"), ("C", "visit")],
        max_route_seconds=20, service_seconds=2)
    road.operations.use_customer_time_windows = True
    road.operations.customer_time_windows = {
        "A": TimeWindow(open_seconds=0, close_seconds=20),
        "C": TimeWindow(open_seconds=0, close_seconds=5),
    }
    search = HybridRoutes(road)
    search.policy = RoutePolicy()
    result = search.seed("regret_insertion", 1, monotonic() + 2, 0)
    assert set(result.served_visit_ids) == {"A", "C"}
    assert validate_solution(road, result, enforce_movement_limit=False).feasible
    assert search.trace[-1]["event"] == "window_insertion_seed"


def test_fixed_path_lp_uses_partial_charges_at_repeated_station_with_deadline():
    from ev_routing.route_resources import assemble_solution
    road = instance([
        ("0", "F", 3, 1), ("F", "C", 4, 1), ("C", "F", 1, 1), ("F", "0", 3, 1),
    ], nodes=[("0", "base"), ("F", "charger"), ("C", "visit")],
        max_route_seconds=20, service_seconds=1, include_charging_time=True,
        charging_power_kw=3600, use_customer_time_windows=True,
        customer_time_windows={"C": {"open_seconds": 0, "close_seconds": 6}})
    repair = FixedPathRepair(road, PricingNetwork(road))
    route = repair.route(road.vehicle_ids[0], ["C"], monotonic() + 2)
    assert route is not None
    charges = [s.charged_to_battery_kwh for s in route.steps if s.node_id == "F"]
    assert len(charges) == 2
    assert charges[0] > 0 and charges[1] > 0
    assert sum(charges) == pytest.approx(6)
    assert next(s for s in route.steps if s.delivered_visit_ids).departure_seconds <= 6 + 1e-8
    assert validate_solution(road, assemble_solution(road, [route]),
                             enforce_movement_limit=False).feasible


def test_fixed_path_failure_does_not_remove_alternative_resource_routes():
    # La recarga necesaria exige un desvío que no pertenece al camino mínimo.
    road = instance([
        ("0", "C", 4, 1), ("C", "0", 4, 1),
        ("0", "F", 3, 2), ("F", "C", 3, 2), ("C", "F", 3, 2), ("F", "0", 3, 2),
    ], nodes=[("0", "base"), ("C", "visit"), ("F", "charger")],
        max_route_seconds=40, include_charging_time=True, charging_power_kw=3600)
    graph, _ = prepare_service_graph(road)
    search = HybridRoutes(graph)
    assert search.fixed_paths.route(graph.vehicle_ids[0], ["C"], monotonic() + 1) is None
    search.evaluation_seconds = 1
    route = search.evaluate(graph.vehicle_ids[0], ["C"], monotonic() + 2)
    assert route is not None
    assert any(s.node_id == "F" and s.charged_to_battery_kwh > 0 for s in route.steps)


def test_global_completion_pass_keeps_existing_deliveries_before_destroying_routes():
    road = pairs()
    search = HybridRoutes(road)
    search.fast.supported = False  # Ejercitar la reparación general, no el camino heredado.
    partial = search.solution([["A"], ["B"]], monotonic() + 1)
    completed = search.improve(
        partial, RoutePolicy(alns_iterations=0), monotonic() + 2, 0,
    )
    assert set(completed.served_visit_ids) == set(road.customer_ids)
    assert search.trace[-1]["event"] == "completion_insertion"
    assert validate_solution(road, completed, enforce_movement_limit=False).feasible


def test_seed_completion_invalidates_pending_seed_changes_before_collection():
    release = Event()
    def provider(request):
        release.wait(2)
        return {"policy": {"seed_starts": 64, "resource_repair_seconds": .12}}
    head = LLMHead(
        SearchConfig(policy="adaptive", max_llm_calls=1,
                     bedrock={"model_id": "double", "timeout_seconds": 2}),
        {}, monotonic() + 4, 4, provider, instance=pairs(),
    )
    head.decide("before_search", {})
    release.set()
    head.pending.result(timeout=2)
    head.decide("after_seed", {"phase": "planning"})
    assert head.policy.seed_starts == RoutePolicy().seed_starts
    assert head.policy.resource_repair_seconds == .12
    assert head.records[0]["inactive_settings"]["seed_starts"] == 64
    assert "seed_starts" not in head.records[0]["algorithm_changes"]


def test_consumed_settings_and_last_call_are_reserved_for_actual_search_feedback():
    calls = []
    def provider(request):
        calls.append(request)
        return {"policy": {"seed_time_fraction": .2, "resource_repair_seconds": .1}}
    head = LLMHead(
        SearchConfig(policy="adaptive", max_llm_calls=2, decision_interval_seconds=0,
                     bedrock={"model_id": "double", "timeout_seconds": 1}),
        {}, monotonic() + 5, 5, provider, instance=pairs(),
    )
    head.locked_settings.add("seed_time_fraction")
    head.decide("before_search", {})
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    assert head.policy.seed_time_fraction == RoutePolicy().seed_time_fraction
    head.decide("after_seed", {"phase": "planning", "deliveries": 1})
    head.decide("tree_node", {"phase": "deliveries"})
    assert len(calls) == 1
    head.decide("search_stagnation", {
        "phase": "deliveries", "pricing_interrupted": True, "exact_pricing_seconds": 8,
    })
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    assert len(calls) == 2
    assert calls[1]["state"]["exact_pricing_seconds"] == 8
    assert calls[1]["finished_stages"] == ["seeding"]
    assert calls[1]["locked_policy_fields"] == ["seed_time_fraction"]


def test_controls_of_unavailable_legacy_adapter_are_not_effective_changes():
    head = LLMHead(
        SearchConfig(policy="adaptive", max_llm_calls=1,
                     bedrock={"model_id": "double", "timeout_seconds": 1}),
        {}, monotonic() + 3, 3,
        lambda _: {"policy": {"local_search_passes": 99, "alns_iterations": 120}},
        instance=two_vehicle_shift(),
    )
    head.unsupported_settings.add("local_search_passes")
    head.decide("before_search", {})
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    assert head.records[0]["inactive_settings"]["local_search_passes"] == 99
    assert "local_search_passes" not in head.records[0]["algorithm_changes"]
    assert head.policy.alns_iterations == 120
    assert head.report()["unsupported_policy_fields"] == ["local_search_passes"]


@pytest.mark.solver
def test_native_complete_service_records_time_before_optimal_early_exit():
    result = solve_routes(
        pairs(), SolverConfig(time_limit_seconds=3), SearchConfig(route_policy_overrides={
            "seed_strategy": "none", "seed_charging": False, "alns_iterations": 0,
            "restricted_master_seconds": 0.0,
        }),
    )
    assert len(result.solution.served_visit_ids) == len(pairs().customer_ids)
    assert result.phases[0].proven_optimal
    assert result.search["first_full_delivery_seconds"] is not None
    assert 0 <= result.search["first_full_delivery_seconds"] <= result.runtime_seconds


def test_benchmark_does_not_turn_missing_success_timestamp_into_par2_failure():
    from test_synthetic_benchmark import summary
    row = summary()
    row["first_full_delivery_solver_seconds"] = None
    row["first_full_within_solver_budget"] = False
    stats = comparisons([row])["modes"]["standard"]
    assert stats["full_service_runs_missing_time"] == 1
    assert stats["full_service_par2_mean_solver_seconds"] is None
    with pytest.raises(ValueError, match="telemetría incompleta"):
        select_fixed([row], [], "code")


def two_vehicle_shift():
    road = instance(
        [(i, j, .5, 3) for i in ("0", "A", "B")
         for j in ("0", "A", "B") if i != j],
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit")],
        max_route_seconds=7,
    )
    road.parameters.vehicle_count = 2
    return road


def test_resource_tour_repair_splits_between_vehicles_and_keeps_every_customer():
    road = two_vehicle_shift()
    search = HybridRoutes(road)
    assert search.evaluate(road.vehicle_ids[0], ["A", "B"], monotonic() + 1) is None
    result = search.split_tour(["0", "A", "B", "0"], monotonic() + 2)
    assert result is not None
    assert set(result.served_visit_ids) == {"A", "B"}
    assert all(sum(len(step.delivered_visit_ids) for step in route.steps) == 1
               for route in result.routes)
    assert validate_solution(road, result, enforce_movement_limit=False).feasible


def test_supplied_charging_tour_cannot_be_replaced_by_an_unrelated_partial_seed(monkeypatch):
    search = HybridRoutes(two_vehicle_shift())
    monkeypatch.setattr(search, "split_tour", lambda *_: None)
    monkeypatch.setattr(search, "seed", lambda *_: pytest.fail("No se pidió un arranque genérico"))
    assert search.charging_seed(1, monotonic() + 1, tours=[["0", "A", "B", "0"]]) is None


def test_energy_phase_rejects_a_cheaper_repair_with_fewer_deliveries(monkeypatch):
    road = two_vehicle_shift()
    search = HybridRoutes(road)
    full = search.solution([["A"], ["B"]], monotonic() + 2)
    partial = search.solution([["A"], []], monotonic() + 2)
    assert partial.net_energy_kwh < full.net_energy_kwh
    monkeypatch.setattr(HybridRoutes, "seed", lambda *_: None)
    monkeypatch.setattr(HybridRoutes, "improve", lambda self, best, *_: best)
    monkeypatch.setattr(HybridRoutes, "split_tour", lambda *_: partial)
    monkeypatch.setattr("ev_routing.route_solver.energy_relaxation", lambda *_, **kw: {
        "applicable": True, "bound_kwh": full.net_energy_kwh, "tour": ["0", "A", "B", "0"],
    })
    result = solve_routes(
        road, SolverConfig(time_limit_seconds=1),
        SearchConfig(route_policy_overrides={"seed_charging": False}),
        initial_solution=full,
    )
    assert set(result.solution.served_visit_ids) == {"A", "B"}
    assert result.phases[0].incumbent == 2
    assert result.phases[1].incumbent == full.net_energy_kwh
    assert result.lexicographic_optimal


@pytest.mark.parametrize("name,bound", [("energy", 100), ("deliveries", 0)])
def test_inconsistent_bound_does_not_create_an_optimality_certificate(name, bound):
    road = two_vehicle_shift()
    solution = HybridRoutes(road).solution([["A"], ["B"]], monotonic() + 1)
    phase = _phase(name, solution, bound, "optimal", .1)
    assert phase.has_solution and not phase.proven_optimal
    assert phase.best_bound is None and phase.relative_gap is None
    assert phase.termination_condition == "inconsistent_bound"


def test_extra_deliveries_found_during_energy_update_coverage_and_reset_its_bound(monkeypatch):
    from time import sleep
    road = two_vehicle_shift()
    search = HybridRoutes(road)
    full = search.solution([["A"], ["B"]], monotonic() + 1)
    partial = search.solution([["A"], []], monotonic() + 1)
    energy_started = []
    monkeypatch.setattr(HybridRoutes, "seed", lambda *_: None)
    monkeypatch.setattr(HybridRoutes, "improve",
                        lambda self, best, *_: full if energy_started else best)

    def master(instance, config, policy, oracles, name, deadline, best, *args, **kwargs):
        if name == "deliveries":
            sleep(max(0, deadline - monotonic()))
        else:
            energy_started.append(True)
        stats = dict.fromkeys([
            "columns", "heuristic_pricing_columns", "exact_pricing_seconds",
            "heuristic_pricing_seconds", "labels_expanded", "dual_pricing_labels",
            "exact_dual_queries", "completed_dual_queries", "completion_bound_prunes",
            "return_time_prunes", "pricing_interrupted",
        ], 0)
        bound = 2 if name == "deliveries" else (
            full.net_energy_kwh if best is full else .25
        )
        return best, _phase(name, best, bound, "pricing_incomplete", .01), stats

    monkeypatch.setattr("ev_routing.route_solver._master_phase", master)
    result = solve_routes(
        road, SolverConfig(time_limit_seconds=1),
        SearchConfig(route_policy_overrides={
            "seed_charging": False, "restricted_master_seconds": 0.,
            "deliveries_time_fraction": .1,
        }), initial_solution=partial,
    )
    assert result.solution is full
    assert result.phases[0].incumbent == result.phases[0].best_bound == 2
    assert result.phases[0].termination_condition == "coverage_improved_during_energy"
    assert result.phases[1].incumbent == result.phases[1].best_bound == full.net_energy_kwh
    assert result.search["energy_relaxation"]["invalidated_by"] == "increased_deliveries"
    assert result.search["first_full_delivery_seconds"] is not None
