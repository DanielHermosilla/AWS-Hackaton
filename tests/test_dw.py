"""Branch-price-and-cut nativo contra cuentas y enumeradores independientes."""

import json

import pytest
from oracle import integer_walk_oracle, no_charge_walk_oracle
from test_model import _instance, _saturation_instance, _scarce_energy_instance, _seeded_instance
from test_operations import charging_case, tiny

from ev_routing.contracts import SolverConfig
from ev_routing.heuristics import build_greedy_start
from ev_routing.search_policy import SearchConfig
from ev_routing.solve import solve_instance
from ev_routing.validation import validate_solution

pytest.importorskip("pygcgopt")
pytestmark = pytest.mark.solver


def solve(instance, policy="standard", *, decomposition="vehicle", **options):
    from ev_routing.dw import solve_dantzig_wolfe

    requests = []

    def provider(request):
        requests.append(request)
        return {"policy": {
            "decomposition": decomposition, "cut_selection": "sparse",
            "pricing": "exact" if request["event"] == "before_decomposition"
            else "heuristic_then_exact", "columns_per_round": 10,
        }}

    result = solve_dantzig_wolfe(
        instance, SolverConfig(solver="gcg", time_limit_seconds=30),
        SearchConfig(
            policy=policy, bedrock={"model_id": "test-double"},
            decision_interval_seconds=0, min_pricing_calls_between_decisions=1,
            max_llm_calls=4,
        ),
        policy_provider=provider if policy == "adaptive" else None, **options,
    )
    assert result.status == "optimal", result.model_dump()
    assert result.lexicographic_optimal
    assert validate_solution(instance, result.solution).feasible
    assert all(not p["callback_errors"] for p in result.search["phases"])
    assert all(p["dw_approach"] == "convexification" for p in result.search["phases"])
    assert all(
        application["exact_pricing_enabled"]
        for phase in result.search["phases"] for application in phase["policy_applications"]
    )
    return result, requests


@pytest.mark.parametrize("policy", ["standard", "deterministic", "adaptive"])
def test_two_phase_operations_and_real_callbacks(policy):
    instance = tiny(service_seconds=100, max_route_seconds=250)
    result, requests = solve(instance, policy, decomposition="vehicle_routing")
    assert len(result.solution.served_visit_ids) == 2
    assert result.solution.net_energy_kwh == pytest.approx(4)
    assert [(p.incumbent, p.best_bound) for p in result.phases] == [(2, 2), (4, 4)]
    assert result.search["controller"]["pricing_callbacks"] > 0
    if policy == "adaptive":
        assert requests[0]["event"] == "before_decomposition"
        assert result.search["controller"]["cut_callbacks"] > 0
        assert result.search["controller"]["policy_selected_cuts"] > 0
        assert any(r["event"] != "before_decomposition" for r in requests)
        assert any(
            a["policy"]["pricing"] == "heuristic_then_exact"
            for p in result.search["phases"] for a in p["policy_applications"]
        )
        assert "node_id" not in json.dumps(requests)
        assert all(p["decomposition"]["name"] == "vehicle_routing"
                   for p in result.search["phases"])


@pytest.mark.parametrize("factory,expected", [
    (_saturation_instance, (1, 4)),
    (_scarce_energy_instance, (2, 8)),
    (lambda: charging_case(), (1, 8)),
    (lambda: charging_case(max_route_seconds=3419), (0, 0)),
    (lambda: charging_case(disabled_charger_ids=["F"]), (0, 0)),
    (lambda: tiny(energy_margin_fraction=1), (2, 8)),
    (lambda: tiny(final_reserve_soc=0.5), (0, 0)),
    (lambda: tiny(service_seconds=50, max_route_seconds=500, use_customer_time_windows=True,
                  customer_time_windows={"A": {"open_seconds": 200, "close_seconds": 250},
                                         "B": {"open_seconds": 0, "close_seconds": 100}}),
     (1, 2)),
])
@pytest.mark.parametrize("decomposition", ["vehicle", "vehicle_routing"])
def test_resources_match_independent_manual_optima(factory, expected, decomposition):
    instance = factory()
    result, _ = solve(instance, "adaptive", decomposition=decomposition)
    assert len(result.solution.served_visit_ids) == expected[0]
    assert result.solution.net_energy_kwh == pytest.approx(expected[1])


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 20, 21])
def test_original_walk_space_matches_independent_enumeration(seed):
    instance = _seeded_instance(seed, fractional_without_charge=seed >= 20)
    oracle = no_charge_walk_oracle if seed >= 20 else integer_walk_oracle
    count, energy = oracle(instance)
    result, _ = solve(instance, "deterministic")
    assert len(result.solution.served_visit_ids) == count
    assert result.solution.net_energy_kwh == pytest.approx(float(energy))


@pytest.mark.parametrize("arcs,horizon,expected", [
    ([("0", "A", 1), ("A", "B", 1), ("B", "A", 1), ("A", "0", 1)], 4, (2, 4)),
    ([("0", "A", 1), ("A", "0", 1), ("0", "B", 1), ("B", "0", 1)], 4, (2, 4)),
    ([("0", "j", 8), ("j", "A", -8), ("A", "0", 1)], 3, (0, 0)),
    ([("0", "j", -2), ("j", "0", 0), ("0", "A", 1), ("A", "0", 1)], 4, (1, 0)),
    ([("0", "j", -2), ("j", "0", 0), ("0", "A", 1), ("A", "0", 1)], 8, (1, -4)),
    ([("0", "j", 1), ("j", "A", 1), ("A", "B", 1), ("B", "0", 1)], 3, (0, 0)),
])
def test_repetition_transit_depot_deficit_and_horizon(arcs, horizon, expected):
    instance = _instance(
        nodes=[("0", "base"), ("A", "visit"), ("B", "visit"), ("j", "junction")],
        arcs=arcs, movements=horizon,
    )
    result, _ = solve(instance)
    assert len(result.solution.served_visit_ids) == expected[0]
    assert result.solution.net_energy_kwh == pytest.approx(expected[1])


def test_zero_customers_and_gcg_dispatch():
    instance = _instance(nodes=[("0", "base")], arcs=[], movements=1)
    result = solve_instance(instance, SolverConfig(solver="gcg", time_limit_seconds=10))
    assert result.lexicographic_optimal
    assert result.solution.served_visit_ids == []
    assert result.solution.net_energy_kwh == 0


def test_timeout_keeps_independently_validated_start_without_false_certificate():
    instance = tiny()
    start = build_greedy_start(instance)
    result = solve_instance(
        instance, SolverConfig(solver="gcg", time_limit_seconds=0.000001),
        initial_solution=start,
    )
    assert result.solution == start
    assert result.solution_source == "initial_solution"
    assert result.status == "feasible" and not result.lexicographic_optimal
    assert all(p.best_bound is None for p in result.phases)


def test_invalid_native_extraction_cannot_escape_as_feasible(monkeypatch):
    from ev_routing import dw
    start = build_greedy_start(tiny())
    invalid = start.model_copy(deep=True)
    invalid.routes[0].steps[0].battery_arrival_kwh = -1
    monkeypatch.setattr(dw, "extract_solution", lambda *args: invalid)
    result = dw.solve_dantzig_wolfe(
        tiny(), SolverConfig(solver="gcg", time_limit_seconds=10),
    )
    assert result.solution is None and result.status == "error"
    assert result.phases[0].best_bound is None
    assert not result.lexicographic_optimal


def test_infeasible_final_reserve_uses_native_proof_without_an_incumbent():
    result = solve_instance(
        tiny(final_reserve_soc=0.8), SolverConfig(solver="gcg", time_limit_seconds=10),
    )
    assert result.solution is None
    assert result.status == "infeasible", result.model_dump()
    assert result.phases[0].termination_condition == "infeasible"


def test_initial_aws_failure_uses_native_search_and_reports_fallback():
    from ev_routing.dw import solve_dantzig_wolfe

    def unavailable(request):
        raise TimeoutError("provider unavailable")

    result = solve_dantzig_wolfe(
        tiny(), SolverConfig(solver="gcg", time_limit_seconds=10),
        SearchConfig(policy="adaptive", bedrock={"model_id": "test"}),
        policy_provider=unavailable,
    )
    assert result.lexicographic_optimal
    assert result.search["controller"]["status"] == "fallback"
    assert result.search["controller"]["effective_policy"] == "standard"
    assert all(
        not application["effective_parameters"]
        for phase in result.search["phases"] for application in phase["policy_applications"]
    )


def test_native_branch_price_and_cut_beyond_root_and_presolved_phase(capfd):
    from ev_routing.dw import solve_dantzig_wolfe

    nodes = ["0", "A", "B", "C"]
    instance = _instance(
        nodes=[(n, "base" if n == "0" else "visit") for n in nodes],
        arcs=[(a, b, 2 if "0" in (a, b) else 1) for a in nodes for b in nodes if a != b],
        movements=3, vehicles=2,
    )
    # Cada vehículo puede atender como máximo dos clientes (energía disponible 5).
    # Atender tres exige un recorrido de dos (5) y uno de un cliente (4): total 9.
    # La combinación de tres medias rutas de dos clientes cuesta 7.5: gap fraccional.
    result = solve_dantzig_wolfe(
        instance, SolverConfig(solver="gcg", time_limit_seconds=10),
        SearchConfig(policy="adaptive", bedrock={"model_id": "test"}, max_llm_calls=1),
        policy_provider=lambda request: {"policy": {
            "decomposition": "vehicle_routing", "cut_family": "original",
            "cut_selection": "sparse", "max_selected_cuts": 1, "pricing": "exact",
        }},
    )
    assert result.lexicographic_optimal
    assert len(result.solution.served_visit_ids) == 3
    assert result.solution.net_energy_kwh == pytest.approx(9)
    assert result.phases[1].best_bound == pytest.approx(9)
    assert result.search["phases"][1]["branch_nodes"] > 1
    assert "ERROR:" not in capfd.readouterr().err
