"""Parámetros nativos reales, recursos protegidos y estrategias físicas verificadas."""

from time import monotonic

import numpy as np
import pytest
from pyscipopt import Model
from test_model import _instance
from test_operations import tiny
from test_verbose_run import BedrockDouble

from ev_routing.contracts import SolverConfig
from ev_routing.llm.bedrock import BedrockPolicyClient
from ev_routing.route_heuristics import InsertionRoutes
from ev_routing.route_policy import RoutePolicy, choose_route_policy
from ev_routing.route_resources import Polytope
from ev_routing.route_solver import _configure, solve_routes
from ev_routing.scip_tuning import parameter_catalog, prompt_catalog, validate_parameters
from ev_routing.search_policy import BedrockConfig, SearchConfig
from ev_routing.validation import validate_solution


def test_catalog_comes_from_installed_scip_and_respects_pricing_capabilities():
    general, tour = parameter_catalog(), parameter_catalog(True)
    assert general["available_parameter_count"] > 1200
    assert tour["available_parameter_count"] > general["available_parameter_count"]
    assert general["scip_version"] == "10.0.0"
    assert "heuristics/rounding/freq" in general["parameters_and_defaults"]
    assert "presolving/maxrounds" not in general["parameters_and_defaults"]
    assert "presolving/maxrounds" in tour["parameters_and_defaults"]
    assert all("feastol" not in key for key in tour["parameters_and_defaults"])


def test_prompt_grouping_preserves_every_native_parameter_without_mutating_registry():
    grouped = prompt_catalog()["parameters_and_defaults"]

    def flatten(tree, prefix=""):
        result = {}
        for key, value in tree.items():
            name = prefix + key
            if isinstance(value, dict):
                result.update(flatten(value, name + "/"))
            else:
                result[name] = value
        return result

    assert flatten(grouped) == parameter_catalog()["parameters_and_defaults"]


def test_extended_strategy_rationale_does_not_reject_valid_parameters():
    policy = RoutePolicy.model_validate({
        "rationale": "Observación; hipótesis. " * 100,
        "scip_parameters": {"heuristics/rounding/freq": 3},
    })
    assert validate_parameters(policy.scip_parameters) == {"heuristics/rounding/freq": 3}


@pytest.mark.parametrize("parameters", [
    {"limits/time": 999}, {"limits/gap": 1}, {"parallel/maxnthreads": 8},
    {"numerics/feastol": 0.1}, {"presolving/maxrounds": 10},
    {"propagating/rootredcost/freq": 1}, {"missing/parameter": 1},
    {"heuristics/rounding/freq": True}, {"heuristics/rounding/freq": -999},
    {"lp/initalgorithm": "invalid"},
])
def test_disallowed_types_ranges_and_certification_changes_are_rejected(parameters):
    with pytest.raises(ValueError):
        validate_parameters(parameters)


def test_native_presets_and_parameters_are_applied_and_protections_survive(tmp_path):
    policy = RoutePolicy(
        heuristics="fast", scip_parameters=validate_parameters({
            "heuristics/rounding/freq": 7, "nodeselection/dfs/stdpriority": 123456,
            "lp/initalgorithm": "d",
        }),
    )
    model = Model()
    changes = _configure(model, SolverConfig(threads=1), policy, str(tmp_path), "test")
    assert model.getParam("heuristics/rounding/freq") == 7
    assert model.getParam("nodeselection/dfs/stdpriority") == 123456
    assert model.getParam("lp/initalgorithm") == "d"
    assert model.getParam("presolving/maxrounds") == 0
    assert model.getParam("separating/maxrounds") == 0
    assert model.getParam("propagating/rootredcost/freq") == -1
    assert len(changes) > 10  # El preset cambia parámetros nativos, no solo el informe.
    assert (tmp_path / "test.parameters.json").is_file()
    model.freeProb()


def test_invalid_llm_native_parameter_falls_back_without_partial_application():
    config = SearchConfig(policy="adaptive", bedrock={"model_id": "test"})
    policy, report = choose_route_policy(config, {}, monotonic() + 60, provider=lambda _: {
        "policy": {"heuristics": "aggressive", "scip_parameters": {"limits/gap": 0.9}},
    })
    assert report["status"] == "fallback"
    assert report["applied_decisions"] == 0
    assert policy == RoutePolicy()


def test_null_annotations_are_audited_without_discarding_valid_actions():
    config = SearchConfig(policy="adaptive", bedrock={"model_id": "test"})
    policy, report = choose_route_policy(config, {}, monotonic() + 60, provider=lambda _: {
        "policy": {"heuristics": "fast", "unused_note": None,
                   "scip_parameters": {"heuristics/rounding/freq": 3}},
    })
    assert report["status"] == "adaptive"
    assert policy.heuristics == "fast"
    assert policy.scip_parameters == {"heuristics/rounding/freq": 3}
    assert report["decisions"][0]["ignored_null_fields"] == {"unused_note": None}


@pytest.mark.parametrize("extra", [{"unknown_action": True}, {"unknown_action": ""},
                                  {"scip_parameters": {"limits/time": None}}])
def test_null_annotation_handling_never_allows_unknown_actions_or_native_parameters(extra):
    config = SearchConfig(policy="adaptive", bedrock={"model_id": "test"})
    policy, report = choose_route_policy(config, {}, monotonic() + 60, provider=lambda _: {
        "policy": {"heuristics": "fast", **extra},
    })
    assert report["status"] == "fallback"
    assert policy == RoutePolicy()


def test_claude_sampling_and_effort_are_forwarded_without_unsupported_temperature(tmp_path):
    native = BedrockDouble('{"heuristics":"fast"}')
    client = BedrockPolicyClient(
        BedrockConfig(model_id="us.anthropic.claude-sonnet-5-5", reasoning_effort="medium"),
        client=native, temperature=0, trace_directory=str(tmp_path),
    )
    client({})
    assert "temperature" not in native.calls[0]["inferenceConfig"]
    assert native.calls[0]["additionalModelRequestFields"] == {
        "output_config": {"effort": "medium"},
    }


def test_two_vertex_dominance_does_not_launch_an_lp(monkeypatch):
    import ev_routing.route_resources as resources
    monkeypatch.setattr(resources, "linprog", lambda *a, **kw: pytest.fail("LP unnecessary"))
    left = Polytope(np.array([[4., 0., 0.], [8., 0., 4.]]), np.zeros((2, 1)))
    right = Polytope(np.array([[6., 0., 2.]]), np.zeros((1, 1)))
    assert left.dominates(right)
    assert not left.dominates(right, vertices_only=True)
    assert not left.dominates(Polytope(np.array([[9., 0., 2.]]), np.zeros((1, 1))))


@pytest.mark.parametrize("strategy", ["cheapest_insertion", "regret_insertion"])
def test_insertion_seed_is_h_free_and_does_not_claim_energy_optimality(strategy):
    instance = _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit"), ("C", "visit")],
        arcs=[(i, j, 2 if "0" in (i, j) else 1)
              for i in ["0", "A", "B", "C"] for j in ["0", "A", "B", "C"] if i != j],
        movements=1, vehicles=2,
    )
    seed = InsertionRoutes(instance).seed(strategy, 4, monotonic() + 1)
    assert len(seed.served_visit_ids) == 3
    assert seed.net_energy_kwh == 9
    assert validate_solution(instance, seed, enforce_movement_limit=False).feasible
    assert any(len(route.steps) > 2 for route in seed.routes)
    assert InsertionRoutes(tiny(max_route_seconds=300)).seed(strategy, 1, monotonic() + 1) is None


@pytest.mark.parametrize("search", ["breadth_first", "depth_first"])
@pytest.mark.parametrize("dominance", ["convex", "vertices_only"])
def test_policy_preserves_exact_small_optimum_with_heuristic_pricing(search, dominance):
    instance = _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit"), ("C", "visit")],
        arcs=[(i, j, 2 if "0" in (i, j) else 1)
              for i in ["0", "A", "B", "C"] for j in ["0", "A", "B", "C"] if i != j],
        movements=1, vehicles=2,
    )
    result = solve_routes(
        instance, SolverConfig(time_limit_seconds=5),
        SearchConfig(policy="adaptive", bedrock={"model_id": "test", "timeout_seconds": .01}),
        policy_provider=lambda _: {"policy": {
            "pricing_search": search, "dominance": dominance,
            "pricing_strategy": "heuristic_then_exact", "route_cuts": "none",
            "scip_parameters": {"lp/initalgorithm": "d", "heuristics/rounding/freq": 3},
        }},
    )
    assert result.lexicographic_optimal
    assert len(result.solution.served_visit_ids) == 3
    assert result.solution.net_energy_kwh == pytest.approx(9)
    assert validate_solution(instance, result.solution, enforce_movement_limit=False).feasible


def test_llm_receives_budget_and_cannot_discard_a_better_standard_seed():
    nodes = ["0", "A", "B", "C", "D"]
    costs = [[0, 3, 3, 2, 2], [2, 0, 2, 2, 2], [1, 5, 0, 2, 3],
             [1, 4, 2, 0, 5], [1, 3, 2, 1, 0]]
    instance = _instance(
        nodes=[(n, "base" if n == "0" else "visit") for n in nodes],
        arcs=[(a, b, costs[i][j]) for i, a in enumerate(nodes)
              for j, b in enumerate(nodes) if i != j],
        movements=1, vehicles=2,
    )
    requests = []

    def provider(request):
        requests.append(request)
        return {"policy": {"seed_strategy": "regret_insertion", "seed_starts": 4}}

    result = solve_routes(
        instance, SolverConfig(time_limit_seconds=1),
        SearchConfig(policy="adaptive", bedrock={"model_id": "test", "timeout_seconds": .01}),
        policy_provider=provider,
    )
    profile = requests[0]["structure"]
    assert profile["search_budget"]["total_seconds"] == 1
    assert profile["search_budget"]["inference_consumes_search_budget"]
    assert profile["validated_incumbent"] == {
        "deliveries": 3, "energy_kwh": 8, "all_customers_served": False,
    }
    seeds = result.search["initial_routes"]
    assert seeds["baseline_energy_kwh"] == seeds["energy_kwh"] == 8
    assert seeds["additional_candidate_energy_kwh"] == 9
    assert (len(result.solution.served_visit_ids), -result.solution.net_energy_kwh) >= (3, -8)
