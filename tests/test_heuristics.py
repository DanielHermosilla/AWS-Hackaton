"""Certificados de H y testigos físicos, sin optimizar ni leer soluciones previas."""

import json

import pytest

from ev_routing import cli, heuristics, pipeline
from ev_routing.contracts import Arc, ModelParameters, Node, ProblemInstance, SolveResult
from ev_routing.heuristics import InitialSolution, analyze_horizon, build_initial_solution
from ev_routing.inputs import load_instance, save_instance
from ev_routing.service_graph import PathArchive, build_service_graph, check_service_context
from ev_routing.validation import validate_solution


@pytest.fixture
def road():
    # Triángulo equilátero de clientes/depósito: una ruta cuesta 3; dividirla
    # cuesta 4. El cargador opcional no puede reducir el consumo.
    nodes = [
        Node(node_id="base", node_type="base"),
        Node(node_id="client/A", node_type="visit"),
        Node(node_id="client B", node_type="visit"),
        Node(node_id="charge", node_type="charger", connector_types=["J1772"]),
    ]
    return ProblemInstance(
        nodes=nodes,
        arcs=[
            Arc(from_node_id=i.node_id, to_node_id=j.node_id, energy_kwh=1, distance_m=100)
            for i in nodes for j in nodes if i != j
        ],
        parameters=ModelParameters(
            vehicle_count=2, battery_capacity_kwh=10, reserve_kwh=1, movement_limit=9,
        ),
    )


@pytest.fixture
def compact(road):
    return build_service_graph(road, 9)[0]


def test_small_h_has_a_witness_and_does_not_claim_the_witness_energy_is_optimal(compact):
    before = compact.model_dump()
    result = analyze_horizon(compact)
    assert result.status == "certified_minimal"
    assert result.recommended_horizon == result.minimum_horizon == 3
    assert result.tour_energy_kwh == 3
    assert result.structural_upper_bound == 6
    assert result.metric_verified and result.minimum_depot_shortcut_saving_kwh == 1
    assert result.starts_tried == 1  # Termina al tener un certificado, sin búsqueda local.
    assert result.runtime_seconds >= 0
    assert compact.model_dump() == before
    compact.parameters.movement_limit = 3
    candidate = build_initial_solution(compact, result.tour)
    assert candidate is not None and validate_solution(compact, candidate).feasible
    assert candidate.net_energy_kwh == 3
    assert all(s.node_id == compact.depot_id for s in candidate.routes[1].steps)


def test_triangle_with_equality_does_not_certify_minimal_h(compact):
    # Los dos recorridos base-A-base y base-B-base consumen 4 en total.
    # Unirlos también consume 4: H=3 basta, pero H=2 podría conservar el óptimo.
    for arc in compact.arcs:
        if arc.from_node_id in compact.customer_ids and arc.to_node_id in compact.customer_ids:
            arc.energy_kwh = 2
    result = analyze_horizon(compact)
    assert result.status == "certified_sufficient"
    assert result.recommended_horizon == 3
    assert result.minimum_horizon is None
    assert result.minimum_depot_shortcut_saving_kwh == 0
    assert result.tour_energy_kwh == 4


def test_zero_energy_and_zero_usable_battery_do_not_imply_one_active_vehicle(compact):
    for arc in compact.arcs:
        arc.energy_kwh = 0
    compact.parameters.reserve_kwh = compact.parameters.initial_energy_kwh
    result = analyze_horizon(compact)
    assert result.status == "certified_sufficient"
    assert result.recommended_horizon == 3 and result.minimum_horizon is None
    assert result.tour_energy_kwh == result.usable_initial_energy_kwh == 0
    assert build_initial_solution(compact, result.tour) is not None


def test_a_failed_heuristic_never_substitutes_an_unproven_small_h(compact):
    compact.parameters.battery_capacity_kwh = 4
    result = analyze_horizon(compact)
    assert result.status == "not_certified"
    assert result.recommended_horizon is None
    assert result.structural_upper_bound == 6
    assert result.tour_energy_kwh == 3 > result.usable_initial_energy_kwh
    assert build_initial_solution(compact, result.tour) is None


def test_without_compatible_chargers_structural_bound_does_not_need_full_service(compact):
    compact.parameters.battery_capacity_kwh = 4
    compact.compatible_chargers = {k: [] for k in compact.vehicle_ids}
    result = analyze_horizon(compact)
    assert result.status == "certified_sufficient"
    assert result.recommended_horizon == result.structural_upper_bound == 3
    assert result.minimum_horizon is None
    assert build_initial_solution(compact, result.tour) is None


@pytest.mark.parametrize("corruption", ["road", "negative", "triangle", "missing_arc", "junction"])
def test_rejects_unsupported_hypotheses(compact, corruption):
    if corruption == "road":
        compact.provenance = {}
    elif corruption == "negative":
        compact.arcs[0].energy_kwh = -1
    elif corruption == "triangle":
        compact.arcs[0].energy_kwh = 100
    elif corruption == "missing_arc":
        compact.arcs.pop()
    else:
        compact.nodes[1].node_type = "junction"
    result = analyze_horizon(compact)
    assert result.status == "not_certified"
    assert result.recommended_horizon is None
    assert not result.metric_verified


def test_no_customers_needs_one_idle_step_even_with_chargers(road):
    road.nodes = [n for n in road.nodes if n.node_type != "visit"]
    ids = {n.node_id for n in road.nodes}
    road.arcs = [a for a in road.arcs if a.from_node_id in ids and a.to_node_id in ids]
    compact, _ = build_service_graph(road, 1)
    result = analyze_horizon(compact)
    assert result.status == "certified_minimal"
    assert result.recommended_horizon == result.minimum_horizon == 1
    solution = build_initial_solution(compact, result.tour)
    assert solution is not None and solution.net_energy_kwh == 0


def test_disconnected_customer_does_not_get_an_invented_route(road):
    road.nodes.append(Node(node_id="unreachable", node_type="visit"))
    compact, _ = build_service_graph(road, 9)
    result = analyze_horizon(compact)
    assert result.metric_verified
    assert result.status == "not_certified" and result.tour == []
    assert result.structural_upper_bound == 8


def test_budget_expiry_returns_no_small_certificate(compact, monkeypatch):
    clock = iter([0, 1, 1])
    monkeypatch.setattr(heuristics, "perf_counter", lambda: next(clock))
    result = analyze_horizon(compact, time_limit_seconds=0.5)
    assert result.recommended_horizon is None
    assert result.starts_tried == 0 and not result.metric_verified
    assert "presupuesto" in result.reason


@pytest.mark.parametrize("kwargs", [
    {"max_starts": 0}, {"max_starts": True}, {"max_starts": 2.5},
    {"time_limit_seconds": 0}, {"time_limit_seconds": float("inf")},
])
def test_heuristic_budget_is_validated(compact, kwargs):
    with pytest.raises(ValueError):
        analyze_horizon(compact, **kwargs)


def test_initial_route_is_not_truncated_or_silently_repaired(compact):
    tour = ["base", "client/A", "client B", "base"]
    compact.parameters.movement_limit = 2
    assert build_initial_solution(compact, tour) is None
    compact.parameters.movement_limit = 3
    assert build_initial_solution(compact, ["base", "client/A", "client/A", "base"]) is None
    assert build_initial_solution(compact, tour[:-1]) is None


def test_auto_cli_writes_consistent_snapshot_analysis_and_initial_solution(
    road, tmp_path, capsys, monkeypatch
):
    source, target, paths = (tmp_path / name for name in ("road.json", "services.json", "paths.json"))
    save_instance(road, source)
    assert cli.main([
        "service-graph", "--service-movements", "auto", "--road-instance", str(source), "--output", str(target),
        "--path-archive", str(paths),
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["service_movements"] == 3 and summary["horizon_certified"]
    instance = load_instance(target)
    archive = PathArchive.model_validate_json(paths.read_text())
    check_service_context(instance, road, archive)
    initial = InitialSolution.model_validate_json(target.with_suffix(".start.json").read_text())
    assert initial.solution is not None
    assert initial.instance_sha256 == archive.service_instance_sha256
    assert validate_solution(instance, initial.solution).feasible
    assert json.loads(target.with_suffix(".horizon.json").read_text())["minimum_horizon"] == 3

    seen = []

    def execute(instance, config, *, initial_solution, **options):
        seen.append(initial_solution)
        return SolveResult(requested_solver="auto", status="feasible", solution=initial_solution)

    monkeypatch.setattr(pipeline, "solve_instance", execute)
    output = tmp_path / "result.json"
    assert cli.main([
        "run", "--instance", str(target), "--road-instance", str(source),
        "--path-archive", str(paths), "--initial-solution", str(target.with_suffix(".start.json")),
        "--output", str(output),
    ]) == 0
    assert seen == [initial.solution]
    result = json.loads(output.read_text())
    assert result["initial_solution"]["validated"]
    assert result["road_validation"]["feasible"]
    assert result["kpis"]["served_deliveries"] == 2


def test_auto_failure_writes_diagnostic_but_never_launches_a_large_model(road, tmp_path, capsys):
    road.parameters.battery_capacity_kwh = 4
    source, target, paths = (tmp_path / name for name in ("road.json", "services.json", "paths.json"))
    save_instance(road, source)
    assert cli.main([
        "service-graph", "--service-movements", "auto", "--road-instance", str(source), "--output", str(target),
        "--path-archive", str(paths),
    ]) == 2
    assert "No se certificó un H pequeño" in capsys.readouterr().err
    assert not target.exists() and not paths.exists()
    assert json.loads(target.with_suffix(".horizon.json").read_text())["structural_upper_bound"] == 6


def test_manual_h_is_preserved_and_not_falsely_certified(road, tmp_path, capsys):
    source, target, paths = (tmp_path / name for name in ("road.json", "services.json", "paths.json"))
    save_instance(road, source)
    assert cli.main([
        "service-graph", "--road-instance", str(source), "--output", str(target),
        "--path-archive", str(paths), "--service-movements", "2",
    ]) == 0
    assert not json.loads(capsys.readouterr().out)["horizon_certified"]
    assert load_instance(target).parameters.movement_limit == 2
    assert InitialSolution.model_validate_json(target.with_suffix(".start.json").read_text()).solution is None


def test_cli_rejects_a_start_from_another_snapshot(compact, tmp_path, capsys):
    source, initial, output = (tmp_path / name for name in ("input.json", "start.json", "run.json"))
    save_instance(compact, source)
    initial.write_text(InitialSolution(instance_sha256="wrong").model_dump_json())
    assert cli.main([
        "run", "--instance", str(source), "--initial-solution", str(initial),
        "--output", str(output),
    ]) == 2
    assert "snapshot seleccionado" in capsys.readouterr().err
    assert not output.exists()


def test_initial_road_paths_are_checked_before_calling_the_solver(road, monkeypatch):
    compact, archive = build_service_graph(road, 3)
    analysis = analyze_horizon(compact)
    initial = build_initial_solution(compact, analysis.tour)
    path = next(p for p in archive.paths if p.from_node_id == compact.depot_id
                and p.to_node_id == analysis.tour[1])
    path.node_ids = [compact.depot_id, "charge", analysis.tour[1]]  # Costaría 2, no 1.

    def forbidden(*args, **kwargs):
        pytest.fail("No enviar un testigo vial alterado al solver")

    monkeypatch.setattr(pipeline, "solve_instance", forbidden)
    with pytest.raises(ValueError, match="energía.*no coincide"):
        pipeline.run_instance(
            compact, road_instance=road, path_archive=archive, initial_solution=initial
        )
