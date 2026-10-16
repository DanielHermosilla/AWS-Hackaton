import copy
import json
from pathlib import Path
from time import monotonic

import pytest
from test_route_orchestration import pairs
from test_synthetic_benchmark import summary

from ev_routing.presentation_benchmark import parser, plan
from ev_routing.presentation_impact import ImpactFactors, estimate_run, llm_cost, paired_impact
from ev_routing.route_hints import routing_digest, validate_orders
from ev_routing.route_hybrid import HybridRoutes
from ev_routing.route_policy import RoutePolicy
from ev_routing.synthetic_instances import make_case
from ev_routing.validation import validate_solution

ROOT = Path(__file__).resolve().parents[1]


def factors():
    return ImpactFactors.model_validate_json((ROOT / "config/presentation-impact.json").read_text())


def test_money_and_carbon_replenish_initial_battery_and_preserve_losses():
    f = factors().model_copy(update={
        "charging_efficiency": .8, "electricity_price_per_kwh": .2,
        "grid_generation_kg_co2_per_kwh": .4, "grid_loss_fraction": 0,
    })
    a, b = summary(), summary(policy="adaptive")
    for r, energy, cost in ((a, 10, 0), (b, 12, .1)):
        r.update(energy_kwh=energy, served_visit_ids=["a", "b", "c", "d"],
                 llm_cost_estimate=cost)
    p = paired_impact(a, b, f)
    assert p["battery_energy_saved_kwh"] == -2
    assert p["electricity_saved_kwh"] == -2.5
    assert p["vehicle_electricity_co2_saved_kg"] == -1
    assert p["money_saved_after_llm"] == pytest.approx(-.6)
    r = estimate_run({**a, "distance_km": 100}, f, {})
    assert r["electricity_replenishment_kwh"] == 12.5
    assert r["diesel_same_route_litres"] == 8


def test_equal_count_but_different_customers_cannot_claim_energy_savings():
    a, b = summary(), summary(policy="adaptive")
    a.update(served_visit_ids=["a", "b", "c", "d"], llm_cost_estimate=0)
    b.update(served_visit_ids=["a", "b", "c", "e"], llm_cost_estimate=.1)
    p = paired_impact(a, b, factors())
    assert p["delivery_delta"] == 0
    assert p["battery_energy_saved_kwh"] is None


def test_cost_uses_real_usage_and_unknown_failed_calls_are_not_free():
    f = factors()
    response = {"tuning": {"calls": 1, "decisions": [{
        "model_id": "us.openai.gpt-5.6-luna",
        "usage": {"inputTokens": 1000, "outputTokens": 100},
    }]}}
    assert llm_cost(response, f) == pytest.approx(.000352)
    bad = copy.deepcopy(response)
    bad["tuning"]["decisions"][0]["usage"] = None
    assert llm_cost(bad, f) is None
    response["tuning"]["inference_inflight"] = True
    assert llm_cost(response, f) is None
    assert llm_cost({}, f) == 0


def test_native_cached_usage_is_priced_without_dropping_cached_input():
    f = factors()
    f.bedrock_prices_per_million_tokens_usd["us.openai.gpt-5.6-luna"].cache_write = .275
    f.bedrock_prices_per_million_tokens_usd["us.openai.gpt-5.6-luna"].cache_read = .022
    result = {"tuning": {"calls": 1, "decisions": [{
        "model_id": "us.openai.gpt-5.6-luna",
        "usage": {"inputTokens": 2, "outputTokens": 419, "cacheWriteInputTokens": 35462,
                  "cacheReadInputTokens": 0, "totalTokens": 35883},
    }]}}
    assert llm_cost(result, f) == pytest.approx(.01030557)
    result["tuning"]["decisions"][0]["usage"]["totalTokens"] = 421
    assert llm_cost(result, f) is None


def test_plan_counts_calls_without_contacting_aws_and_rejects_seed_leakage():
    args = parser().parse_args(["plan", "--customers", "16", "--families", "dispatch",
                               "--test-seeds", "100", "--ablation"])
    p = plan(args)
    assert p["pilot_runs_without_aws"] == 8
    assert p["comparison_runs"] == 5
    assert p["max_real_aws_calls"] == 4
    args.test_seeds = args.development_seeds
    with pytest.raises(ValueError, match="semillas"):
        plan(args)


def test_hint_is_physical_primal_only_and_cannot_reduce_coverage():
    instance = pairs()
    search = HybridRoutes(instance)
    vehicle = instance.vehicle_ids[0]
    policy = RoutePolicy(route_orders={vehicle: ["A", "B"], instance.vehicle_ids[1]: ["C"]})
    best = search.apply_order_hint(None, policy, monotonic() + 2)
    assert validate_solution(instance, best, enforce_movement_limit=False).feasible
    assert len(best.served_visit_ids) == 3
    assert search.stats["order_hints_improved"] == 1
    assert search.apply_order_hint(best, policy, monotonic() + 2) is best
    assert search.stats["order_hints_attempted"] == 1
    policy.route_orders = {vehicle: ["A"]}
    assert search.apply_order_hint(best, policy, monotonic() + 2) is best
    assert search.stats["order_hints_feasible"] == 2
    assert search.stats["order_hints_improved"] == 1


@pytest.mark.parametrize("orders", [
    {"vehicle_1": ["A", "A"]}, {"unknown": []}, {"vehicle_1": ["unknown"]},
])
def test_hint_rejects_duplicates_unknown_vehicle_and_unknown_customer(orders):
    with pytest.raises(ValueError):
        validate_orders(orders, {"A", "B"}, {"vehicle_1"})


def test_metric_has_no_invented_travel_times_or_hidden_witness():
    digest = routing_digest(pairs(), 10000)
    assert digest["travel_seconds"] is None
    assert digest["energy_kwh"][0][1] == 2
    assert "witness" not in json.dumps(digest)
    assert routing_digest(pairs(), 10)["scope"] == "omitted"


def test_portfolio_preserves_physics_and_does_not_claim_a_bound():
    from ev_routing.route_portfolio import rebuild
    instance = pairs()
    search = HybridRoutes(instance)
    policy = RoutePolicy(rebuild_strategy="energy_blocks", rebuild_clusters=2, rebuild_seconds=2)
    candidate = rebuild(search, None, policy, monotonic() + 3, 0)
    assert candidate is not None
    assert len(candidate.served_visit_ids) == 3
    assert validate_solution(instance, candidate, enforce_movement_limit=False).feasible
    assert search.stats["portfolio_improvements"] > 0
    assert "bound" not in search.stats


@pytest.mark.parametrize("size,seed", [(16, 1), (80, 2), (160, 3)])
def test_targeted_dispatch_witness_is_independently_feasible(size, seed):
    case = make_case(size, seed, "dispatch")
    assert validate_solution(case.road, case.witness, enforce_movement_limit=False).feasible
    assert len(case.witness.served_visit_ids) == size


def test_electric_local_moves_preserve_deliveries_and_improve_crossed_routes():
    from test_model import _instance
    from ev_routing.route_electric_local import improve_electric

    locations = {"0": (0, 0), "A": (2, 1), "B": (-2, 1),
                 "C": (2, -1), "D": (-2, -1)}
    instance = _instance(
        nodes=[(i, "base" if i == "0" else "visit") for i in locations],
        arcs=[(a, b, .1 * ((locations[a][0] - locations[b][0]) ** 2
                           + (locations[a][1] - locations[b][1]) ** 2) ** .5)
              for a in locations for b in locations if a != b],
        movements=1, vehicles=2,
    )
    search = HybridRoutes(instance)
    original = search.solution([["A", "B"], ["C", "D"]], monotonic() + 2)
    improved = improve_electric(search, original, monotonic() + 2)
    assert improved.served_visit_ids == original.served_visit_ids
    assert improved.net_energy_kwh < original.net_energy_kwh
    assert search.stats["electric_local_improvements"] > 0
    assert validate_solution(instance, improved, enforce_movement_limit=False).feasible


def test_head_keeps_best_observed_route_context_after_weaker_seed():
    from ev_routing.llm_head import LLMHead
    from ev_routing.search_policy import SearchConfig

    head = LLMHead(SearchConfig(policy="standard"), {}, monotonic() + 3, 3,
                   instance=pairs())
    best = {"deliveries": 3, "energy_kwh": 9, "orders": {"vehicle_1": ["A", "B"]}}
    head.decide("heuristic_incumbent", best)
    head.decide("heuristic_incumbent",
                {"deliveries": 1, "energy_kwh": 4, "orders": {"vehicle_1": ["C"]}})
    assert head.incumbent_orders == best["orders"]
    head.decide("heuristic_incumbent",
                {"deliveries": 3, "energy_kwh": 10, "orders": {"vehicle_1": ["C", "A"]}})
    assert head.incumbent_orders == best["orders"]
    head.close()


def test_unattended_pilot_retains_failures_and_excludes_failed_presets():
    from ev_routing.synthetic_benchmark import select_fixed

    rows = [summary(policy="standard"), summary(policy="electric")]
    rows[0]["returncode"] = 124
    selected = select_fixed(rows, [], "code", allow_failures=True)
    assert selected["selected_preset"] == "electric"
    assert selected["excluded_presets_with_execution_failures"] == {"standard": 1}
    assert selected["pilot_runs_including_failures"] == 2
    rows[1]["returncode"] = 124
    with pytest.raises(ValueError, match="Todos los presets"):
        select_fixed(rows, [], "code", allow_failures=True)


@pytest.mark.parametrize("family,seed", [("crossed", 1), ("dispatch", 2)])
def test_window_waves_builds_independently_validated_complete_routes(family, seed):
    from ev_routing.resource_graph import prepare_service_graph
    from ev_routing.service_graph import expand_and_validate

    generated = make_case(24, seed, family)
    instance, archive = prepare_service_graph(generated.road)
    search = HybridRoutes(instance)
    policy = RoutePolicy(rebuild_strategy="window_waves", rebuild_seconds=3,
                         seed_strategy="none", alns_iterations=0)
    solution = search.improve(None, policy, monotonic() + 3, 0)
    assert solution is not None and len(solution.served_visit_ids) == 24
    _, validation, _ = expand_and_validate(instance, generated.road, archive, solution, without_h=True)
    assert validation.feasible
