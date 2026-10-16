"""Cotas frente a enumeración, física independiente y callbacks SCIP reales."""

import json
from random import Random
from threading import Event, get_ident
from time import monotonic
from types import SimpleNamespace

import pytest
from pyscipopt import Model
from test_resource_graph import exhaust, instance, window_case
from test_route_orchestration import pairs

from ev_routing.contracts import Arc, SolverConfig
from ev_routing.llm_head import LLMHead
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.route_hybrid import HybridRoutes, sequences
from ev_routing.route_policy import RoutePolicy
from ev_routing.route_pricing import PricingNetwork, ReducedCostOracle
from ev_routing.route_relaxation import energy_relaxation
from ev_routing.route_resources import assemble_solution
from ev_routing.route_solver import solve_routes
from ev_routing.search_policy import SearchConfig
from ev_routing.service_graph import expand_and_validate
from ev_routing.validation import validate_solution


def test_long_repair_collects_policy_updates_between_insertions(monkeypatch):
    import ev_routing.route_hybrid as hybrid

    search = HybridRoutes(pairs())
    search.policy = RoutePolicy()
    clock, events, evaluations = [0.0], [], []
    monkeypatch.setattr(hybrid, "monotonic", lambda: clock[0])

    def evaluate(vehicle, order, deadline):
        evaluations.append((clock[0], search.evaluation_seconds))
        clock[0] += .2
        return SimpleNamespace(net_energy_kwh=float(len(order)))

    def observer(event, state):
        events.append(clock[0])
        search.policy.resource_repair_seconds = .08

    search.evaluate, search.observer = evaluate, observer
    a, b, c = sorted(search.instance.customer_ids)
    choices = search._options([[a, b], []], c, 10)
    assert choices
    assert events and events[0] < evaluations[-1][0]
    assert any(seconds == .08 for _, seconds in evaluations[1:])
    assert all(later - earlier >= .25 for earlier, later in zip(events, events[1:]))


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("weight", [0, 1])
def test_pruned_pricing_matches_negative_columns_of_exhaustive_oracle(seed, weight):
    rng = Random(seed)
    road = instance([
        ("0", "j", -2 if seed % 2 else .5, 1), ("j", "A", 2, 1),
        ("A", "0", 1, 1), ("0", "B", 2, 1), ("B", "A", 1, 1),
        ("A", "B", 1, 1), ("B", "0", 2, 1),
    ], nodes=[("0", "base"), ("j", "junction"), ("A", "visit"), ("B", "visit")],
        max_route_seconds=20, service_seconds=1)
    graph, _ = prepare_service_graph(road)
    reference = exhaust(graph)
    rewards = [rng.uniform(-3, 12), rng.uniform(-3, 12)]
    convex = rng.uniform(-2, 3)
    cuts = [(3, rng.uniform(-2, 2))]
    def reduced(mask, route):
        return (weight * route.net_energy_kwh - convex
                - sum(value for i, value in enumerate(rewards) if mask & (1 << i))
                - sum(value * ((mask & subset).bit_count() // 2) for subset, value in cuts))
    expected = {mask: reduced(mask, route) for mask, route in reference.routes.items()
                if reduced(mask, route) < -1e-7}
    query = ReducedCostOracle(graph, graph.vehicle_ids[0], rewards, cuts, convex, weight,
                              1e-7, PricingNetwork(graph))
    query.exhaust(monotonic() + 3)
    assert query.complete
    actual = {mask: reduced(mask, route) for mask, route in query.routes.items()
              if reduced(mask, route) < -1e-7}
    assert actual == pytest.approx(expected)


def test_new_dual_does_not_reuse_a_previous_prune():
    graph, _ = prepare_service_graph(window_case())
    network = PricingNetwork(graph)
    first = ReducedCostOracle(graph, graph.vehicle_ids[0], [-100], [], -1, 1, 1e-7, network)
    first.exhaust(monotonic()+1)
    assert first.complete and first.pruned_bound > 0
    second = ReducedCostOracle(graph, graph.vehicle_ids[0], [100], [], 0, 1, 1e-7, network)
    second.exhaust(monotonic()+1)
    assert second.complete and second.routes[1].net_energy_kwh == pytest.approx(3)


def test_sequence_repair_chooses_fast_profile_and_validates_expanded_streets():
    road = window_case()
    graph, archive = prepare_service_graph(road)
    search = HybridRoutes(graph)
    search.evaluation_seconds = 1
    route = search.evaluate(graph.vehicle_ids[0], ["C"], monotonic()+2)
    assert route is not None
    assert route.net_energy_kwh == pytest.approx(3)
    solution = assemble_solution(graph, [route])
    _, report, _ = expand_and_validate(graph, road, archive, solution, without_h=True)
    assert report.feasible, report.violations
    assert all(step.arc_id for step in route.steps[:-1])


def test_sequence_repair_revisits_station_and_preserves_partial_charge():
    road = instance([
        ("0", "j", -2, 1), ("j", "F", 3, 1), ("F", "C", 4, 1),
        ("C", "F", 5, 1), ("F", "0", 2, 1),
    ], nodes=[("0", "base"), ("j", "junction"), ("F", "charger"), ("C", "visit")],
        max_route_seconds=80, include_charging_time=True, charging_power_kw=360,
        service_seconds=5)
    graph, archive = prepare_service_graph(road)
    search = HybridRoutes(graph)
    search.evaluation_seconds = 2
    route = search.evaluate(graph.vehicle_ids[0], ["C"], monotonic()+3)
    assert route is not None
    assert sum(step.node_id == "F" for step in route.steps) == 2
    assert route.net_energy_kwh == pytest.approx(12)
    _, report, _ = expand_and_validate(graph, road, archive, assemble_solution(graph, [route]),
                                       without_h=True)
    assert report.feasible


def test_relaxed_tour_repairs_on_parallel_profiles_without_fixing_fast_path():
    road = window_case()
    road.operations.customer_time_windows["C"].close_seconds = 2000
    graph, archive = prepare_service_graph(road)
    search = HybridRoutes(graph)
    solution = search.split_tour(["0", "C", "0"], monotonic()+2)
    assert solution is not None
    assert solution.net_energy_kwh == pytest.approx(2)
    _, report, _ = expand_and_validate(graph, road, archive, solution, without_h=True)
    assert report.feasible
    # The same sequence can deliberately prioritize the faster, more expensive path.
    search.policy = RoutePolicy(resource_path_order="time")
    fast = search.evaluate(graph.vehicle_ids[0], ["C"], monotonic()+2)
    assert fast is not None
    assert fast.net_energy_kwh == pytest.approx(3)


def test_parallel_arcs_are_not_summed_in_valid_lower_bound():
    graph = instance([
        ("0", "A", 1, 1), ("A", "B", 1, 1), ("B", "0", 1, 1),
    ], nodes=[("0", "base"), ("A", "visit"), ("B", "visit")])
    graph.schema_version = "1.1"
    graph.arcs = [arc.model_copy(update={"arc_id": f"a{i}"}) for i, arc in enumerate(graph.arcs)]
    graph.arcs.append(Arc(from_node_id="0", to_node_id="A", energy_kwh=9,
                          distance_m=100, arc_id="slow", travel_time_seconds=1))
    report = energy_relaxation(graph, SolverConfig(), RoutePolicy(), monotonic()+1,
                               complete_service=True)
    assert report["applicable"]
    assert report["bound_kwh"] == pytest.approx(3)


def test_memetic_crossover_and_alns_preserve_uniqueness_and_physics():
    graph = pairs()
    search = HybridRoutes(graph)
    first = search.solution([["A", "B"], ["C"]], monotonic()+1)
    second = search.solution([["A", "C"], ["B"]], monotonic()+1)
    search._survive(first, 6)
    search._survive(second, 6)
    result = search.improve(first, RoutePolicy(
        alns_iterations=12, population_size=6, local_search_passes=0, ruin_rounds=0,
    ), monotonic()+2, 4)
    assert search.stats["crossovers"] > 0
    assert sum(search.operator_counts.values()) > 0
    assert len(result.served_visit_ids) == 3
    assert result.net_energy_kwh <= first.net_energy_kwh + 1e-9
    for candidate in search.population:
        visited = [i for order in sequences(candidate) for i in order]
        assert len(visited) == len(set(visited))
        assert validate_solution(graph, candidate, enforce_movement_limit=False).feasible


def test_worker_gets_real_instance_and_mps_without_blocking_or_scip_objects(tmp_path):
    entered, release = Event(), Event()
    calls = []
    main_thread = get_ident()
    def provider(request):
        calls.append((request, get_ident()))
        entered.set()
        release.wait(2)
        return {"policy": {"node_selection": "depth_first"}, "usage": {"totalTokens": 17}}
    config = SearchConfig(policy="adaptive", log_directory=str(tmp_path),
                          bedrock={"model_id": "double", "timeout_seconds": 1})
    head = LLMHead(config, {}, monotonic()+5, 5, provider, instance=pairs())
    model = Model()
    model.hideOutput()
    var = model.addVar(vtype="B", name="customer")
    model.addCons(var <= 1)
    head.attach_master(model, "master")
    started = monotonic()
    head.decide("before_search", {})
    assert monotonic()-started < 1
    assert entered.wait(1)
    request, worker = calls[0]
    assert worker != main_thread
    assert request["instance_context"]["scope"] == "complete_physical_graph"
    assert "\nNAME " in request["restricted_master"]["text"]
    assert "RESTRICTED_MASTER_ONLY" in request["restricted_master"]["scope"]
    json.dumps(request, allow_nan=False)
    release.set()
    head.pending.result(timeout=2)
    assert head.collect()
    assert head.policy.node_selection == "depth_first"
    assert head.report()["decisions"][0]["usage"]["totalTokens"] == 17
    head.close()
    model.freeProb()


def test_invalid_head_action_keeps_last_valid_policy():
    replies = iter([{"focus_customers": ["A"], "node_selection": "depth_first"},
                    {"focus_customers": ["not-a-customer"]},
                    {"scip_parameters": {"numerics/feastol": .1}}])
    config = SearchConfig(policy="adaptive", max_llm_calls=3, decision_interval_seconds=0,
                          bedrock={"model_id": "double", "timeout_seconds": .01})
    head = LLMHead(config, {}, monotonic()+5, 5,
                   lambda _: {"policy": next(replies)}, instance=pairs())
    for _ in range(3):
        head.decide("search_stagnation", {"phase": "energy"})
        if head.pending:
            head.pending.result(timeout=1)
            head.collect()
    assert head.policy.node_selection == "depth_first"
    assert head.policy.focus_customers == ["A"]
    assert [r["status"] for r in head.records] == ["applied", "rejected", "rejected"]
    head.close()


def test_full_service_event_survives_an_inflight_first_request():
    entered, release = Event(), Event()
    requests = []

    def provider(request):
        requests.append(request)
        if len(requests) == 1:
            entered.set()
            release.wait(2)
        return {"policy": {}, "usage": {"totalTokens": 10}}

    head = LLMHead(SearchConfig(
        policy="adaptive", max_llm_calls=2, decision_interval_seconds=99,
        bedrock={"model_id": "double", "timeout_seconds": 1},
    ), {"customers": 3}, monotonic() + 10, 10, provider, instance=pairs())
    head.decide("before_search", {"phase": "planning"})
    assert entered.wait(1)
    head.decide("first_full_service", {
        "phase": "energy", "deliveries": 3, "energy_kwh": 9,
        "orders": {"vehicle_1": ["A", "B"], "vehicle_2": ["C"]},
        "first_full_delivery_seconds": .1,
    })
    assert head.calls == 1
    assert head.report()["queued_full_service_feedback"]
    release.set()
    head.pending.result(timeout=1)
    head.decide("pricing_progress", {"phase": "energy"})
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    assert [r["event"] for r in requests] == ["before_search", "first_full_service"]
    assert requests[-1]["state"]["feedback_was_deferred"]
    assert requests[-1]["state"]["first_full_delivery_seconds"] == .1
    assert head.report()["events"]["first_full_service"] == 1
    assert not head.report()["queued_full_service_feedback"]
    head.close()


def test_interrupted_electric_neighborhood_can_resume(monkeypatch):
    from test_model import _instance
    from ev_routing.route_portfolio import rebuild
    import ev_routing.route_electric_local as local

    nodes = ["0", "A", "B", "C"]
    cheap = {("0", "A"), ("A", "C"), ("C", "B"), ("B", "0"), ("C", "0")}
    instance = _instance(
        nodes=[(n, "base" if n == "0" else "visit") for n in nodes],
        arcs=[(a, b, .5 if (a, b) in cheap else 2.5)
              for a in nodes for b in nodes if a != b],
        movements=1, initial_soc=1,
    )
    search = HybridRoutes(instance)
    policy = RoutePolicy(rebuild_strategy="electric_local", rebuild_seconds=1)
    search.policy = policy
    best = search.solution([["A", "B", "C"]], monotonic() + 1)
    assert best.net_energy_kwh == pytest.approx(6)
    # The caller admitted the work, but its slice expires inside the heuristic.
    with monkeypatch.context() as patch:
        patch.setattr(local, "monotonic", lambda: monotonic() + 100)
        interrupted = rebuild(search, best, policy, monotonic() + 1, 0)
    assert interrupted is best
    resumed = rebuild(search, best, policy, monotonic() + 1, 0)
    assert resumed.net_energy_kwh == pytest.approx(2)
    assert resumed.served_visit_ids == best.served_visit_ids
    assert validate_solution(instance, resumed, enforce_movement_limit=False).feasible


def test_live_head_prints_actual_changes_and_inactive_settings(capsys):
    head = LLMHead(SearchConfig(
        policy="adaptive", show_llm_trace=True, bedrock={"model_id": "double"},
    ), {}, monotonic()+5, 5, lambda _: {"policy": {
        "node_selection": "depth_first", "seed_starts": 24,
    }}, instance=pairs())
    head.decide("pricing_progress", {"phase": "energy"})
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    output = capsys.readouterr().out
    assert "Consulta enviada; SCIP continúa" in output
    assert "Decisión validada" in output
    assert '"status": "applied"' in output
    assert '"before": "hybrid"' in output and '"after": "depth_first"' in output
    assert '"inactive_settings": {' in output and '"seed_starts": 24' in output
    head.close()


def test_malformed_provider_response_falls_back_without_stopping_search():
    config = SearchConfig(policy="adaptive", bedrock={"model_id": "double"})
    head = LLMHead(config, {}, monotonic()+5, 5, lambda _: [], instance=pairs())
    head.decide("before_search", {})
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    assert head.report()["status"] == "fallback"
    assert head.records[0]["reason"] == "invalid_response"
    head.close()


def test_expired_request_does_not_block_fast_model_or_apply_stale_policy():
    entered, release = Event(), Event()
    calls = []
    def provider(request):
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            release.wait(2)
            return {"policy": {"columns_per_round": 99}, "usage": {"totalTokens": 11}}
        return {"policy": {"columns_per_round": 7}}
    head = LLMHead(SearchConfig(
        policy="adaptive", decision_interval_seconds=0, max_llm_calls=2,
        bedrock={"model_id": "strong", "fast_model_id": "fast"},
    ), {}, monotonic()+10, 10, provider, instance=pairs())
    head.decide("before_search", {})
    assert entered.wait(1)
    head.pending_deadline = monotonic()-1
    head.decide("pricing_progress", {"phase": "energy"})
    if head.pending:
        head.pending.result(timeout=1)
        head.collect()
    assert head.policy.columns_per_round == 7
    assert head.records[0]["reason"] == "decision_deadline"
    assert head.records[1]["model_id"] == "fast"
    stale = head.abandoned[0][0]
    release.set()
    stale.result(timeout=1)
    head.collect()
    assert head.policy.columns_per_round == 7
    assert head.records[0]["usage"]["totalTokens"] == 11
    head.close()


def test_live_callbacks_apply_llm_policy_and_preserve_manual_optimum(tmp_path):
    result = solve_routes(pairs(), SolverConfig(time_limit_seconds=5), SearchConfig(
        policy="adaptive", decision_interval_seconds=0, max_llm_calls=3,
        log_directory=str(tmp_path), bedrock={"model_id": "double", "timeout_seconds": .01},
    ), policy_provider=lambda _: {"policy": {
        "route_cuts": "subset_row_triples", "tree_branching": "llm_priority",
        "focus_customers": ["A"], "callback_frequency": 1, "node_selection": "depth_first",
        "scip_parameters": {"heuristics/rounding/freq": 1},
    }, "usage": {"totalTokens": 5}})
    assert result.lexicographic_optimal, result.model_dump()
    assert result.solution.net_energy_kwh == pytest.approx(9)
    assert result.search["controller"]["applied_decisions"] > 0
    controls = [phase["callback_control"] for phase in result.search["phases"]
                if phase.get("callback_control")]
    assert controls
    assert not any(control["errors"] for control in controls)
    assert any(any(int(rev) > 0 for rev in c["callbacks_by_policy_revision"]) for c in controls)
    assert any(c["callbacks"].get("separation", 0) for c in controls)
    assert any(c["callbacks"].get("recombination_submips", 0) for c in controls)
    assert list(tmp_path.glob("*.mps"))
