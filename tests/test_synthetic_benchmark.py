"""Testigos independientes, comparación sin fuga y control local sin llamadas AWS."""

import copy
import json
from time import monotonic

import networkx as nx
import pytest

from ev_routing import synthetic_benchmark as benchmark
from ev_routing.llm_head import LLMHead
from ev_routing.resource_graph import prepare_service_graph
from ev_routing.search_policy import SearchConfig
from ev_routing.service_graph import check_service_context
from ev_routing.synthetic_instances import make_case
from ev_routing.validation import validate_solution


@pytest.mark.parametrize("family", ["loose", "clustered", "crossed"])
@pytest.mark.parametrize("seed", [0, 101])
def test_generated_witness_is_feasible_requires_charge_and_is_reproducible(family, seed):
    case = make_case(16, seed, family)
    assert case.road == make_case(16, seed, family).road
    assert len(case.witness.served_visit_ids) == 16
    assert validate_solution(case.road, case.witness, enforce_movement_limit=False).feasible
    assert case.description["witness_charging_stops"] > 0
    assert not case.description["witness_given_to_solver_or_llm"]
    assert "witness" not in json.dumps(case.road.provenance)
    assert len({round(a.energy_kwh / a.distance_m, 6) for a in case.road.arcs}) > 2
    graph = nx.DiGraph()
    graph.add_weighted_edges_from(
        (a.from_node_id, a.to_node_id, a.energy_kwh) for a in case.road.arcs
    )
    outgoing = nx.single_source_dijkstra_path_length(graph, "depot")
    returning = nx.single_source_dijkstra_path_length(graph.reverse(), "depot")
    usable = case.road.parameters.initial_energy_kwh - case.road.parameters.reserve_kwh
    assert all(outgoing[c] + returning[c] > usable for c in case.road.customer_ids)
    # La prueba no confía en el mismo constructor que produjo la carga.
    damaged = case.witness.model_copy(deep=True)
    for route in damaged.routes:
        for step in route.steps:
            step.charged_to_battery_kwh = 0
    assert not validate_solution(case.road, damaged, enforce_movement_limit=False).feasible


def test_preprocessing_preserves_services_and_energy_time_alternatives():
    case = make_case(4, 0)
    compact, archive = prepare_service_graph(case.road)
    check_service_context(compact, case.road, archive)
    assert set(compact.customer_ids) == set(case.road.customer_ids)
    assert set(compact.charger_ids) == set(case.road.charger_ids)
    paths = [a for a in compact.arcs
             if a.from_node_id == "depot" and a.to_node_id == "station_0_0"]
    assert len(paths) == 2
    cheap, costly = sorted(paths, key=lambda a: a.energy_kwh)
    assert cheap.travel_time_seconds > costly.travel_time_seconds


def test_physical_hash_ignores_labels_metadata_and_order_but_not_physics():
    case = make_case(4, 0).road
    other = case.model_copy(deep=True)
    other.name = "another-name"
    other.provenance = {"other": "metadata"}
    other.nodes.reverse()
    other.arcs.reverse()
    assert benchmark.physical_hash(case) == benchmark.physical_hash(other)
    other.arcs[0].energy_kwh += .1
    assert benchmark.physical_hash(case) != benchmark.physical_hash(other)


def test_local_rules_change_live_policy_and_record_no_llm(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Las reglas locales no pueden inicializar ni llamar Bedrock.")
    monkeypatch.setattr("ev_routing.llm.bedrock.create_bedrock_client", forbidden)
    instance = make_case(8, 0, "crossed").road
    head = LLMHead(
        SearchConfig(local_rule_control=True), {"customers": 8}, monotonic() + 20, 20,
        provider=forbidden, instance=instance,
    )
    policy_reference = head.policy
    head.decide("before_search", {})
    head.decide("after_seed", {"deliveries": 3})
    assert head.policy is policy_reference
    assert policy_reference.resource_path_order == "time"
    assert policy_reference.focus_customers
    head.decide("search_stagnation", {"deliveries": 8})
    assert policy_reference.resource_path_order == "energy"
    assert policy_reference.focus_customers == []
    report = head.report()
    assert report["local_policy_mode"] == "rules"
    assert len(report["local_decisions"]) >= 2
    assert report["calls"] == report["applied_decisions"] == 0
    assert report["decisions"] == []


@pytest.mark.parametrize("override", [
    {"battery_capacity_kwh": 10}, {"columns_per_round": 0},
    {"scip_parameters": {"limits/time": 100}},
    {"focus_customers": ["nonexistent"]},
])
def test_initial_policy_cannot_change_physics_global_budget_or_unknown_customers(override):
    with pytest.raises(ValueError):
        LLMHead(SearchConfig(route_policy_overrides=override), {}, monotonic() + 5, 5)


def test_fixed_rules_and_adaptive_share_frozen_starting_policy():
    args = benchmark.parser().parse_args(["compare"])
    fixed = benchmark.PRESETS["primal"]
    for mode in ["fixed", "rules", "adaptive"]:
        config = benchmark._search(args, mode, fixed)
        assert config.route_policy_overrides == fixed
        assert config.local_rule_control == (mode == "rules")
        assert config.policy == ("adaptive" if mode == "adaptive" else "standard")
    assert benchmark._search(args, "standard", fixed).route_policy_overrides == {}
    with pytest.raises(ValueError, match="reglas locales"):
        SearchConfig(policy="adaptive", local_rule_control=True,
                     bedrock={"model_id": "test-model"})


def result_fixture():
    return {
        "status": "feasible",
        "validation": {"feasible": True}, "road_validation": {"feasible": True},
        "kpis": {"feasible": True, "served_deliveries": 4, "net_battery_energy_kwh": 10.0},
        "solve": {"phases": [
            {"name": "deliveries", "proven_optimal": True},
            {"name": "energy", "relative_gap": .004, "best_bound": 9.96},
        ], "search": {"first_full_delivery_seconds": 1.2}},
        "tuning": {"status": "fallback", "calls": 1, "applied_decisions": 0,
                   "decisions": [{"status": "not_applied", "usage": None}]},
    }


def summary(result=None, code=0, policy="standard"):
    return benchmark.summarize(
        {"policy": policy, "case_id": "test-case", "solver_seed": 0, "budget_seconds": 10},
        {"customers": 4, "family": "loose", "instance_seed": 100,
         "preprocessing_and_audit_seconds": .2, "physical_sha256": "abc"},
        {"returncode": code, "wall_seconds": 2.0},
        result if result is not None else result_fixture(), 10, .005,
    )


def test_gap_requires_full_valid_service_and_finite_global_bound():
    assert summary()["energy_gap_reached"]
    for modification in ["bound_missing", "bound_invalid", "partial", "invalid", "no_solution"]:
        result = result_fixture()
        if modification == "bound_missing":
            result["solve"]["phases"][1]["best_bound"] = None
        elif modification == "bound_invalid":
            result["solve"]["phases"][1]["best_bound"] = 11
        elif modification == "partial":
            result["kpis"]["served_deliveries"] = 3
        elif modification == "invalid":
            result["road_validation"]["feasible"] = False
        else:
            result.update(validation=None, road_validation=None, kpis={})
        assert not summary(result)["energy_gap_reached"]
    assert not summary(code=124)["energy_gap_reached"]
    assert not summary({})["feasible"]


def test_fallback_failures_and_unequal_deliveries_are_not_hidden():
    base = summary(policy="fixed")
    adaptive = summary(policy="adaptive")
    assert adaptive["llm_status"] == "fallback"
    assert adaptive["llm_total_tokens"] is None
    failed = summary(code=124, policy="adaptive")
    failed["case_id"] = "failed-case"
    partial = result_fixture()
    partial["kpis"]["served_deliveries"] = 3
    partial = summary(partial, policy="adaptive")
    partial["case_id"] = "partial-case"
    base_partial = copy.deepcopy(base)
    base_partial["case_id"] = "partial-case"
    stats = benchmark.comparisons([base, base_partial, adaptive, failed, partial])["modes"]["adaptive"]
    assert stats["runs"] == 3
    assert stats["execution_failures"] == 1
    assert stats["same_delivery_energy_pairs"] == 1
    assert stats["full_service_par2_mean_solver_seconds"] == pytest.approx((1.2 + 20 + 20) / 3)
    assert stats["gap_speedup_bootstrap_95_by_instance"] is None


def test_pilot_selection_and_test_split_are_frozen_before_execution(tmp_path, monkeypatch):
    rows = [summary(policy=p) for p in benchmark.PRESETS]
    rows[1]["first_full_delivery_solver_seconds"] = .8
    selected = benchmark.select_fixed(
        rows, [{"physical_sha256": "abc", "instance_seed": 0, "customers": 4, "family": "loose"}],
        benchmark.code_hash(),
    )
    assert selected["selected_preset"] == "primal"
    policy_path = tmp_path / "selected.json"
    policy_path.write_text(json.dumps(selected))
    assert benchmark.load_fixed(policy_path, benchmark.code_hash()) == json.loads(json.dumps(selected))
    with pytest.raises(ValueError, match="otro código"):
        benchmark.load_fixed(policy_path, "different-code")
    def forbidden(*args, **kwargs):
        pytest.fail("No preparar ni resolver instancias del piloto como evaluación.")
    monkeypatch.setattr(benchmark, "_prepare_case", forbidden)
    args = benchmark.parser().parse_args([
        "compare", "--fixed-policy", str(policy_path), "--instance-seeds", "0",
        "--output-dir", str(tmp_path / "out"),
    ])
    with pytest.raises(ValueError, match="semillas de prueba"):
        benchmark.run(args)
    assert not (tmp_path / "out").exists()
    rows[0]["returncode"] = 124
    with pytest.raises(ValueError, match="errores de ejecución"):
        benchmark.select_fixed(rows, [], benchmark.code_hash())


def test_adaptive_dry_run_prepares_without_starting_solver_or_aws(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("dry-run no debe ejecutar procesos ni inicializar Bedrock.")
    monkeypatch.setattr(benchmark, "_execute", forbidden)
    monkeypatch.setattr("ev_routing.llm.bedrock.create_bedrock_client", forbidden)
    policy_path = tmp_path / "selected.json"
    policy_path.write_text(json.dumps(benchmark.select_fixed(
        [summary()], [{"physical_sha256": "development", "instance_seed": 0,
                      "customers": 4, "family": "loose"}], benchmark.code_hash(),
    )))
    args = benchmark.parser().parse_args([
        "compare", "--fixed-policy", str(policy_path), "--output-dir", str(tmp_path / "out"),
        "--customers", "4", "--families", "loose", "--instance-seeds", "100", "--dry-run",
    ])
    assert benchmark.run(args) == 0
    assert not (tmp_path / "out" / "runs").exists()
    plan = json.loads((tmp_path / "out" / "plan.json").read_text())
    assert {r["policy"] for r in plan} == {"standard", "fixed", "rules", "adaptive"}
    args.resume = True
    assert benchmark.run(args) == 0
    args.threads = 2
    with pytest.raises(ValueError, match="idénticos código, datos y opciones"):
        benchmark.run(args)


@pytest.mark.solver
def test_process_smoke_keeps_witness_private_and_checks_resume_integrity(tmp_path):
    args = benchmark.parser().parse_args([
        "pilot", "--output-dir", str(tmp_path / "out"), "--customers", "4",
        "--families", "loose", "--policies", "standard", "--time-limit-seconds", ".5",
    ])
    assert benchmark.run(args) == 0
    directory = next((tmp_path / "out" / "runs").iterdir())
    execution = (directory / "execution.json").read_bytes()
    job = json.loads((directory / "job.json").read_text())
    assert set(job["inputs"]) == {"road", "instance", "paths"}
    assert "initial_solution" not in job
    result = json.loads((directory / "result.json").read_text())
    assert result["tuning"]["calls"] == 0
    args.resume = True
    assert benchmark.run(args) == 0
    assert execution == (directory / "execution.json").read_bytes()
    (directory / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="Resultado modificado"):
        benchmark.run(args)
