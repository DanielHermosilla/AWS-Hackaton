"""Flujo offline completo y resultados verificables desde la misma CLI pública."""

import csv
import hashlib
import json
import socket
from types import SimpleNamespace

import networkx as nx
import pytest

from ev_routing import cli, pipeline
from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    PhaseResult,
    ProblemInstance,
    RouteStep,
    Solution,
    SolveResult,
    SolverConfig,
    VehicleRoute,
)
from ev_routing.inputs import ROUTING_COLUMNS, load_instance, save_instance


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Esta suite debe usar archivos y dobles locales, sin red")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def example():
    """Una entrega accesible y otra aislada; 2 kWh medidos desde los dos arcos."""
    instance = ProblemInstance(
        name="Entrega sintética, no instancia oficial",
        nodes=[
            Node(node_id="centro α", node_type="base"),
            Node(node_id="visit/A", node_type="visit"),
            Node(node_id="pendiente B", node_type="visit"),
        ],
        arcs=[
            Arc(from_node_id="centro α", to_node_id="visit/A", energy_kwh=1, distance_m=500),
            Arc(from_node_id="visit/A", to_node_id="centro α", energy_kwh=1, distance_m=700),
        ],
        parameters=ModelParameters(
            vehicle_count=1, movement_limit=2, battery_capacity_kwh=10, reserve_kwh=1
        ),
        provenance={"kind": "synthetic_test", "assumptions": ["Arcos y energía de prueba."]},
    )
    solution = Solution(
        routes=[
            VehicleRoute(
                vehicle_id="vehicle_1",
                steps=[
                    RouteStep(
                        position=0, node_id="centro α", battery_arrival_kwh=6,
                        battery_departure_kwh=6, next_node_id="visit/A",
                        predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1,
                    ),
                    RouteStep(
                        position=1, node_id="visit/A", battery_arrival_kwh=5,
                        battery_departure_kwh=5, next_node_id="centro α",
                        delivered_visit_ids=["visit/A"],
                        predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1,
                    ),
                    RouteStep(
                        position=2, node_id="centro α",
                        battery_arrival_kwh=4, battery_departure_kwh=4,
                    ),
                ],
                net_energy_kwh=2,
            )
        ],
        served_visit_ids=["visit/A"],
        unserved_visit_ids=["pendiente B"],
        net_energy_kwh=2,
    )
    solved = SolveResult(
        requested_solver="auto",
        used_solver="scip",
        solver_version="test-double",
        fallback_reason="gurobi: no disponible en el doble de prueba",
        status="optimal",
        lexicographic_optimal=True,
        solution=solution,
        runtime_seconds=0.0,
        phases=[
            PhaseResult(
                name="deliveries", sense="maximize", status="optimal",
                termination_condition="optimal", has_solution=True, proven_optimal=True,
                incumbent=1, best_bound=1, absolute_gap=0, relative_gap=0,
            ),
            PhaseResult(
                name="energy", sense="minimize", status="optimal",
                termination_condition="optimal", has_solution=True, proven_optimal=True,
                incumbent=2, best_bound=2, absolute_gap=0, relative_gap=0,
            ),
        ],
    )
    return SimpleNamespace(instance=instance, solved=solved)


@pytest.fixture
def fake_solver(monkeypatch, example):
    calls = []

    def execute(instance, config):
        calls.append((instance.model_copy(deep=True), config.model_copy(deep=True)))
        return example.solved.model_copy(deep=True)

    monkeypatch.setattr(pipeline, "solve_instance", execute)
    return calls


def test_pipeline_writes_auditable_json_and_marks_unknown_impacts_unavailable(
    example, fake_solver, tmp_path
):
    output = tmp_path / "nested" / "result.json"
    before = example.instance.model_dump()
    result = pipeline.run_instance(example.instance, output_path=output)
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert result["status"] == "optimal"
    assert result["validation"]["feasible"]
    assert all(result["validation"]["checks"].values())
    assert result["kpis"]["served_deliveries"] == 1
    assert result["kpis"]["total_deliveries"] == 2
    assert result["kpis"]["distance_km"] == pytest.approx(1.2)
    assert result["kpis"]["net_battery_energy_kwh"] == 2
    assert result["kpis"]["minimum_battery_kwh"] == 4
    for name in (
        "grid_energy_kwh", "operational_duration_seconds", "time_saved_seconds", "co2e_saved_kg"
    ):
        assert result["kpis"][name] is None
        assert result["kpis"]["unavailable_reasons"][name]
    assert result["solve"]["solution"]["unserved_visit_ids"] == ["pendiente B"]
    assert result["parameters"] == before["parameters"]
    assert example.instance.model_dump() == before
    assert len(fake_solver) == 1
    assert output.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.parametrize("corruption", ["battery", "duplicate_delivery", "energy", "return"])
def test_checker_overrules_optimal_status_and_suppresses_invalid_kpis(
    example, fake_solver, corruption
):
    solution = example.solved.solution
    assert solution is not None
    if corruption == "battery":
        solution.routes[0].steps[1].battery_arrival_kwh = 50
    elif corruption == "duplicate_delivery":
        solution.routes[0].steps[1].delivered_visit_ids.append("visit/A")
    elif corruption == "energy":
        solution.net_energy_kwh = -100
    else:
        solution.routes[0].steps[-1].node_id = "visit/A"
    result = pipeline.run_instance(example.instance)
    assert result["status"] == "invalid_solution"
    assert result["solve"]["status"] == "optimal"
    assert not result["validation"]["feasible"]
    assert result["validation"]["violations"]
    assert not result["kpis"]["feasible"]
    assert result["kpis"]["served_deliveries"] is None
    assert result["kpis"]["net_battery_energy_kwh"] is None


@pytest.mark.parametrize("status", ["time_limit", "infeasible", "unavailable", "error"])
def test_no_incumbent_still_produces_json_without_fictitious_zero_metrics(
    example, fake_solver, tmp_path, status
):
    example.solved.solution = None
    example.solved.status = status
    example.solved.lexicographic_optimal = False
    example.solved.phases = [
        PhaseResult(
            name="deliveries", sense="maximize", status=status,
            termination_condition=status, has_solution=False, proven_optimal=False,
            best_bound=2 if status == "time_limit" else None,
        )
    ]
    result = pipeline.run_instance(example.instance, output_path=tmp_path / "result.json")
    assert result["status"] == status
    assert result["validation"] is None
    assert result["solve"]["solution"] is None
    assert result["kpis"]["served_deliveries"] is None
    assert result["kpis"]["net_battery_energy_kwh"] is None
    assert result["solve"]["phases"][0]["incumbent"] is None
    assert result["solve"]["phases"][0]["relative_gap"] is None
    assert json.loads((tmp_path / "result.json").read_text()) == result


def test_conditional_energy_phase_keeps_its_own_bound_and_gap(example, fake_solver):
    example.solved.status = "feasible"
    example.solved.lexicographic_optimal = False
    first, second = example.solved.phases
    first.status = "time_limit"
    first.termination_condition = "maxTimeLimit"
    first.proven_optimal = False
    first.best_bound, first.absolute_gap, first.relative_gap = 2, 1, 0.5
    second.best_bound, second.absolute_gap, second.relative_gap = 2, 0, 0
    result = pipeline.run_instance(example.instance)
    one, two = result["solve"]["phases"]
    assert (one["sense"], one["incumbent"], one["best_bound"]) == ("maximize", 1, 2)
    assert (two["sense"], two["incumbent"], two["best_bound"]) == ("minimize", 2, 2)
    assert one["relative_gap"] == 0.5 and two["relative_gap"] == 0
    assert two["proven_optimal"] and not one["proven_optimal"]
    assert not result["solve"]["lexicographic_optimal"]
    assert result["status"] == "feasible" and result["kpis"]["feasible"]
    assert "gap" not in result and "relative_gap" not in result["solve"]


def test_instance_hash_is_stable_across_runs_and_independent_of_solver_options(
    example, fake_solver
):
    first = pipeline.run_instance(example.instance, SolverConfig(solver="scip", seed=0))
    second = pipeline.run_instance(example.instance, SolverConfig(solver="gurobi", seed=13))
    assert first["instance_sha256"] == second["instance_sha256"]
    assert first["run_id"] != second["run_id"]
    assert first["solver_config"] != second["solver_config"]
    changed = example.instance.model_copy(deep=True)
    changed.parameters.reserve_kwh = 0.5
    third = pipeline.run_instance(changed)
    assert third["instance_sha256"] != first["instance_sha256"]


def test_pipeline_never_calls_the_future_tuning_entry_point(example, fake_solver, monkeypatch):
    from ev_routing.llm import tuning

    def forbidden(*args, **kwargs):
        pytest.fail("El pipeline actual no debe entrar al tuning")

    monkeypatch.setattr(tuning, "propose_tuning", forbidden)
    monkeypatch.setattr(tuning, "build_tuning_request", forbidden)
    result = pipeline.run_instance(example.instance)
    assert result["tuning"]["status"] == "disabled"
    assert result["tuning"]["reason"]
    assert result["runtime_seconds"]["llm"] == 0
    assert all(value >= 0 for value in result["runtime_seconds"].values())
    assert result["runtime_seconds"]["total"] >= result["runtime_seconds"]["validation"]


def test_run_cli_preserves_instance_parameters_and_only_overrides_solver(
    example, fake_solver, tmp_path, capsys
):
    source, output, config = (tmp_path / name for name in ("instance.json", "run.json", "config.json"))
    save_instance(example.instance, source)
    original_bytes = source.read_bytes()
    config.write_text(
        json.dumps(
            {
                "model": {
                    "vehicle_count": 3, "movement_limit": 99,
                    "battery_capacity_kwh": 100, "reserve_kwh": 20, "initial_soc": 0.7,
                },
                "solver": {
                    "solver": "auto", "time_limit_seconds": 90, "threads": 1,
                    "seed": 23, "relative_gap": 0.05,
                },
            }
        ),
        encoding="utf-8",
    )
    code = cli.main(
        [
            "run", "--instance", str(source), "--config", str(config), "--output", str(output),
            "--solver", "scip", "--time-limit-seconds", "8", "--threads", "2", "--seed", "71",
            "--tee",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0 and captured.err == ""
    stdout = json.loads(captured.out)
    assert stdout["status"] == "optimal"
    assert stdout["solver"] == "scip"
    assert stdout["deliveries"] == 1
    assert stdout["net_battery_energy_kwh"] == 2
    assert stdout["result_path"] == str(output)
    assert source.read_bytes() == original_bytes
    seen_instance, seen_config = fake_solver[0]
    assert seen_instance == example.instance
    assert seen_config == SolverConfig(
        solver="scip", time_limit_seconds=8, threads=2, seed=71, relative_gap=0.05, tee=True
    )
    result = json.loads(output.read_text())
    assert result["parameters"] == example.instance.parameters.model_dump()
    assert result["tuning"]["status"] == "disabled"


@pytest.mark.parametrize("no_solution", [False, True])
def test_run_cli_returns_one_for_unvalidated_or_missing_solution(
    example, fake_solver, tmp_path, capsys, no_solution
):
    source, output = tmp_path / "instance.json", tmp_path / "result.json"
    save_instance(example.instance, source)
    if no_solution:
        example.solved.solution = None
        example.solved.status = "time_limit"
        example.solved.lexicographic_optimal = False
    else:
        example.solved.solution.net_energy_kwh = 999
    code = cli.main(["run", "--instance", str(source), "--output", str(output)])
    assert code == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out)["deliveries"] is None
    result = json.loads(output.read_text())
    assert not result["kpis"]["feasible"]
    assert result["status"] == ("time_limit" if no_solution else "invalid_solution")


@pytest.mark.parametrize(
    "problem",
    ["missing_instance", "malformed_instance", "invalid_config", "zero_budget", "solver_failure"],
)
def test_run_errors_are_json_on_stderr_and_do_not_publish_a_result(
    example, fake_solver, tmp_path, capsys, monkeypatch, problem
):
    source, output = tmp_path / "instance.json", tmp_path / "result.json"
    save_instance(example.instance, source)
    args = ["run", "--instance", str(source), "--output", str(output)]
    if problem == "missing_instance":
        source.unlink()
    elif problem == "malformed_instance":
        source.write_text('{"nodes":', encoding="utf-8")
    elif problem == "invalid_config":
        config = tmp_path / "config.json"
        config.write_text('{"solver":{"movement_limit":1}}', encoding="utf-8")
        args += ["--config", str(config)]
    elif problem == "zero_budget":
        args += ["--time-limit-seconds", "0"]
    else:
        def fail(*args, **kwargs):
            raise RuntimeError("fallo de prueba")

        monkeypatch.setattr(pipeline, "solve_instance", fail)
    assert cli.main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["error"] and error["type"]
    assert not output.exists()


@pytest.fixture
def local_inputs(tmp_path, monkeypatch):
    import osmnx as ox

    def download_forbidden(*args, **kwargs):
        pytest.fail("prepare offline no debe descargar ni consultar mapas")

    monkeypatch.setattr(ox, "graph_from_bbox", download_forbidden)
    graph = nx.MultiDiGraph(crs="EPSG:4326", simplified=False)
    for key, longitude in ((11, -70.65), (22, -70.6499), (33, -70.6498)):
        graph.add_node(key, x=longitude, y=-33.45)
    for origin, destination, length in (
        (11, 22, 120), (22, 11, 140), (22, 33, 80), (33, 22, 90)
    ):
        graph.add_edge(origin, destination, length=length, osmid=100 + origin)
    graphml = tmp_path / "roads.graphml"
    ox.save_graphml(graph, filepath=graphml)
    nodes = tmp_path / "nodes.csv"
    rows = []
    for node_id, kind, longitude in (
        ("centro α", "base", -70.65),
        ("visit/A", "visit", -70.6499),
        ("visit/B", "visit", -70.6498),
        ("charge:1", "charger", -70.6499),
        ("charge:2", "charger", -70.6498),
    ):
        row = dict.fromkeys(ROUTING_COLUMNS, "")
        row.update(node_id=node_id, node_type=kind, latitude=-33.45, longitude=longitude)
        if kind == "charger":
            row.update(
                total_ports=2, dc_fast_ports=1, level2_ports=1,
                connector_types=" CHAdeMO ; J1772 ", max_power_kw=50,
            )
        rows.append(row)
    with nodes.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROUTING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return SimpleNamespace(nodes=nodes, graphml=graphml, output=tmp_path / "out" / "instance.json")


def prepare_args(inputs, *extra):
    return [
        "prepare", "--nodes", str(inputs.nodes), "--graphml", str(inputs.graphml),
        "--output", str(inputs.output), *extra,
    ]


def test_prepare_reads_local_csv_graphml_and_records_all_assumptions(local_inputs, capsys):
    before = (local_inputs.nodes.read_bytes(), local_inputs.graphml.read_bytes())
    assert cli.main(prepare_args(local_inputs, "--energy-rate", "0.2", "--name", "escenario local")) == 0
    captured = capsys.readouterr()
    assert not captured.err
    summary = json.loads(captured.out)
    instance = load_instance(local_inputs.output)
    assert instance.name == "escenario local"
    assert summary["deliveries"] == 2
    assert summary["energy_kwh_per_km"] == 0.2
    assert len(instance.nodes) == summary["nodes"] == 8
    assert len(instance.arcs) == summary["arcs"] == 14
    assert instance.depot_id == "centro α"
    assert set(instance.customer_ids) == {"visit/A", "visit/B"}
    assert set(instance.charger_ids) == {"charge:1", "charge:2"}
    road = next(a for a in instance.arcs if a.from_node_id == "osm:11" and a.to_node_id == "osm:22")
    assert road.distance_m == 120 and road.energy_kwh == pytest.approx(0.024)
    assert instance.provenance["graphml_downloaded_this_run"] is False
    assert instance.provenance["routing_csv_sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert instance.provenance["graphml_sha256"] == hashlib.sha256(before[1]).hexdigest()
    assert instance.provenance["network"]["original_road_arc_count"] == 4
    assert instance.provenance["energy_model"]["kind"] == "user_supplied_distance_rate"
    assert instance.provenance["capacity_note"]
    assert instance.provenance["assumptions"]
    assert before == (local_inputs.nodes.read_bytes(), local_inputs.graphml.read_bytes())


@pytest.mark.parametrize(
    "selection,visits,chargers",
    [
        (["--visit-id", "visit/B", "--no-chargers"], ["visit/B"], []),
        (["--charger-id", "charge:2"], ["visit/A", "visit/B"], ["charge:2"]),
        (
            ["--visit-id", "visit/B", "--visit-id", "visit/A", "--charger-id", "charge:1"],
            ["visit/A", "visit/B"], ["charge:1"],
        ),
        (["--visit-id", "visit/A", "--visit-id", "visit/A"], ["visit/A"], ["charge:1", "charge:2"]),
    ],
)
def test_prepare_selection_is_explicit_and_does_not_prune_road_intersections(
    local_inputs, capsys, selection, visits, chargers
):
    assert cli.main(prepare_args(local_inputs, "--energy-rate", "0.2", *selection)) == 0
    capsys.readouterr()
    instance = load_instance(local_inputs.output)
    assert instance.customer_ids == visits
    assert instance.charger_ids == chargers
    assert instance.provenance["selected_visit_ids"] == visits
    assert instance.provenance["selected_charger_ids"] == chargers
    assert {n.node_id for n in instance.nodes if n.node_type == "junction"} == {
        "osm:11", "osm:22", "osm:33"
    }


def test_prepare_applies_physical_config_when_creating_the_snapshot(local_inputs, tmp_path, capsys):
    config = tmp_path / "prepare-config.json"
    model = ModelParameters(
        vehicle_count=3, movement_limit=15, battery_capacity_kwh=30, reserve_kwh=3,
        initial_soc=0.7, vehicle_connector_types=["CHAdeMO"],
    )
    config.write_text(json.dumps({"model": model.model_dump()}), encoding="utf-8")
    assert cli.main(
        prepare_args(local_inputs, "--energy-rate", "0.2", "--config", str(config))
    ) == 0
    capsys.readouterr()
    instance = load_instance(local_inputs.output)
    assert instance.parameters == model
    assert instance.vehicle_ids == ["vehicle_1", "vehicle_2", "vehicle_3"]


def test_prepare_integrates_eved_with_real_intervals_and_reuses_content_cache(
    local_inputs, tmp_path, capsys, monkeypatch
):
    import ev_routing.energy as energy

    eved = tmp_path / "ev.csv"
    eved.write_text(
        "VehId,Trip,Timestamp,Vehicle Speed[km/h],HV Battery Current[A],HV Battery Voltage[V]\n"
        "EV1,trip2,2026-01-01 12:00:05,36,-36,100\n"
        "EV1,trip1,2026-01-01 10:00:00,36,-36,100\n"
        "EV1,trip2,2026-01-01 12:00:00,36,-36,100\n"
        "EV1,trip1,2026-01-01 10:00:03,36,-36,100\n",
        encoding="utf-8",
    )
    cache = tmp_path / "cache" / "energy.json"
    args = prepare_args(local_inputs, "--eved", str(eved), "--energy-cache", str(cache))
    assert cli.main(args) == 0
    summary = json.loads(capsys.readouterr().out)
    # 3.6 kW * (3 + 5) s = 0.008 kWh; 36 km/h * 8 s = 0.08 km.
    assert summary["energy_kwh_per_km"] == pytest.approx(0.1)
    instance = load_instance(local_inputs.output)
    training = instance.provenance["energy_model"]["training_summary"]
    assert training["trip_count"] == 2
    assert training["valid_interval_count"] == 2
    assert training["integrated_seconds"] == 8
    assert training["energy_kwh"] == pytest.approx(0.008)
    assert training["distance_km"] == pytest.approx(0.08)
    assert training["source_sha256"] == hashlib.sha256(eved.read_bytes()).hexdigest()
    assert instance.provenance["energy_model"]["limitations"]
    saved_cache = cache.read_bytes()

    def do_not_integrate_again(*args, **kwargs):
        pytest.fail("La segunda preparación debe reutilizar la integración cacheada")

    monkeypatch.setattr(energy, "integrate_eved", do_not_integrate_again)
    assert cli.main(args) == 0
    capsys.readouterr()
    assert cache.read_bytes() == saved_cache


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["--visit-id", "unknown"], "cliente desconocidos"),
        (["--visit-id", "charge:1"], "cliente desconocidos"),
        (["--charger-id", "visit/A"], "cargador desconocidos"),
        (["--energy-rate", "0"], "finito y positivo"),
        (["--energy-rate", "-0.1"], "finito y positivo"),
        (["--energy-rate", "nan"], "finito y positivo"),
        (["--max-snap-distance-m", "-1"], "finito y no negativo"),
    ],
)
def test_prepare_invalid_requests_fail_without_writing_snapshot(
    local_inputs, capsys, arguments, expected
):
    energy_args = [] if "--energy-rate" in arguments else ["--energy-rate", "0.2"]
    assert cli.main(prepare_args(local_inputs, *energy_args, *arguments)) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert expected in json.loads(captured.err)["error"]
    assert not local_inputs.output.exists()


def test_prepare_never_downloads_when_local_graph_is_missing(local_inputs, capsys):
    local_inputs.graphml.unlink()
    assert cli.main(prepare_args(local_inputs, "--energy-rate", "0.2")) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "FileNotFoundError"
    assert "allow_download" in error["error"]
    assert not local_inputs.output.exists()


@pytest.mark.parametrize("conflict", ["energy_sources", "charger_selection"])
def test_mutually_exclusive_prepare_options_fail_at_argument_parsing(
    local_inputs, capsys, conflict
):
    extra = (
        ["--eved", "irrelevant.csv"]
        if conflict == "energy_sources"
        else ["--no-chargers", "--charger-id", "charge:1"]
    )
    with pytest.raises(SystemExit) as error:
        cli.main(prepare_args(local_inputs, "--energy-rate", "0.2", *extra))
    assert error.value.code == 2
    assert capsys.readouterr().err
    assert not local_inputs.output.exists()
