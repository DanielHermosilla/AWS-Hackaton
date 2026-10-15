"""Extensiones verificadas con cuentas manuales, ambos solvers y calendarios alterados."""

import json

import pyomo.environ as pyo
import pytest
from pydantic import ValidationError

from ev_routing import cli
from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    Operations,
    ProblemInstance,
    SolverConfig,
)
from ev_routing.heuristics import analyze_horizon, build_greedy_start
from ev_routing.inputs import load_instance, save_instance
from ev_routing.metrics import compute_metrics
from ev_routing.model import build_model
from ev_routing.operations import arc_energy
from ev_routing.service_graph import (
    PathArchive,
    build_service_graph,
    expand_and_validate,
    fingerprint,
)
from ev_routing.solve import _load_initial_values, solve_instance
from ev_routing.validation import validate_solution


def tiny(**options):
    nodes = [Node(node_id=i, node_type="base" if i == "0" else "visit") for i in ["0", "A", "B"]]
    return ProblemInstance(
        nodes=nodes,
        arcs=[
            Arc(
                from_node_id=i.node_id, to_node_id=j.node_id, energy_kwh=1,
                distance_m=500, travel_time_seconds=60,
            )
            for i in nodes for j in nodes if i != j
        ],
        parameters=ModelParameters(
            vehicle_count=2, movement_limit=3, battery_capacity_kwh=10, reserve_kwh=1,
        ),
        operations=Operations(**options),
    )


def charging_case(**overrides):
    # 0-F-A-0: 8 kWh; mínimo 3 kWh de recarga para salir con 6 y regresar con 1.
    options = dict(
        max_route_seconds=3420, service_seconds=120,
        include_charging_time=True, charging_power_kw=4, charging_efficiency=0.9,
    )
    options.update(overrides)
    return ProblemInstance(
        nodes=[
            Node(node_id="0", node_type="base"), Node(node_id="A", node_type="visit"),
            Node(node_id="F", node_type="charger", connector_types=["J1772"], max_power_kw=50),
        ],
        arcs=[
            Arc(from_node_id=i, to_node_id=j, energy_kwh=e, distance_m=100, travel_time_seconds=100)
            for i, j, e in [("0", "F", 2), ("F", "A", 3), ("A", "0", 3)]
        ],
        parameters=ModelParameters(
            vehicle_count=1, movement_limit=3, battery_capacity_kwh=10, reserve_kwh=1,
        ),
        operations=Operations(**options),
    )


@pytest.fixture(params=["gurobi", "scip"])
def backend(request):
    plugin = "gurobi_direct" if request.param == "gurobi" else "scip"
    if not pyo.SolverFactory(plugin).available(exception_flag=False):
        pytest.skip(f"{request.param} no instalado")
    return request.param


def solve(instance, backend, initial=None):
    result = solve_instance(
        instance, SolverConfig(solver=backend, time_limit_seconds=15), initial_solution=initial,
    )
    if result.status == "unavailable":
        pytest.skip(result.message)
    assert result.status == "optimal", result.model_dump()
    assert result.lexicographic_optimal
    report = validate_solution(instance, result.solution)
    assert report.feasible, report.violations
    return result.solution


@pytest.mark.solver
def test_duration_makes_two_vehicles_necessary_without_forcing_them(backend):
    baseline = solve(tiny(), backend)
    assert baseline.net_energy_kwh == pytest.approx(3)
    instance = tiny(service_seconds=100, max_route_seconds=250)
    model = build_model(instance)
    assert not hasattr(model, "arrival_time")  # Jornada agregada, sin relojes por parada.
    limited = solve(instance, backend, build_greedy_start(instance))
    assert len(limited.served_visit_ids) == 2
    assert limited.net_energy_kwh == pytest.approx(4)
    assert [r.duration_seconds for r in limited.routes] == pytest.approx([220, 220])
    metrics = compute_metrics(instance, limited, validate_solution(instance, limited))
    assert metrics["operational_duration_seconds"] == 220
    assert metrics["total_vehicle_time_seconds"] == 440


@pytest.mark.solver
@pytest.mark.parametrize("limit,count", [(3420, 1), (3419, 0)])
def test_partial_charging_time_and_efficiency_are_not_free(backend, limit, count):
    instance = charging_case(max_route_seconds=limit)
    solution = solve(instance, backend)
    assert len(solution.served_visit_ids) == count
    if count:
        # 3/(4*.9) horas = 3000 s; más 300 de viaje y 120 de servicio.
        assert solution.routes[0].duration_seconds == pytest.approx(3420)
        step = next(s for s in solution.routes[0].steps if s.node_id == "F")
        assert step.charged_to_battery_kwh == pytest.approx(3)
        assert step.charging_duration_seconds == pytest.approx(3000)
        metrics = compute_metrics(instance, solution, validate_solution(instance, solution))
        assert metrics["grid_energy_kwh"] == pytest.approx(3 / 0.9)
        model = build_model(instance)
        _load_initial_values(model, instance, solution)
        assert all(v.value is not None for v in model.component_data_objects(pyo.Var))


@pytest.mark.solver
def test_disabling_a_station_removes_charging_not_the_road_location(backend):
    instance = charging_case(disabled_charger_ids=["F"])
    assert instance.charger_ids == ["F"] and instance.chargers_for("vehicle_1") == []
    assert not solve(instance, backend).served_visit_ids


@pytest.mark.solver
def test_final_reserve_applies_to_return_not_all_intermediate_positions(backend):
    instance = charging_case(final_reserve_soc=0.4, max_route_seconds=6500)
    instance.arcs[0].energy_kwh = 3  # Llega a F con 3 (<4), recarga 6 y regresa con 4.
    instance.arcs[1].energy_kwh = 2
    solution = solve(instance, backend)
    route = solution.routes[0]
    assert solution.served_visit_ids == ["A"]
    assert min(s.battery_arrival_kwh for s in route.steps) < 4
    assert route.steps[-1].battery_arrival_kwh >= 4 - 1e-6
    # With no charging available, 50% at return leaves only 1 kWh for driving.
    assert not solve(tiny(final_reserve_soc=0.5), backend).served_visit_ids


def test_disabled_windows_and_neutral_options_add_no_variables_or_constraints():
    baseline = build_model(tiny())
    inactive = build_model(tiny(
        use_customer_time_windows=False,
        customer_time_windows={"A": {"open_seconds": 0, "close_seconds": 0}},
    ))
    assert not hasattr(inactive, "arrival_time")
    assert inactive.nvariables() == baseline.nvariables()
    assert inactive.nconstraints() == baseline.nconstraints()


@pytest.mark.solver
def test_energy_margin_applied_once_changes_feasibility(backend):
    instance = tiny(energy_margin_fraction=1)
    solution = solve(instance, backend)
    assert len(solution.served_visit_ids) == 2
    assert solution.net_energy_kwh == pytest.approx(8)  # 2 autos * 2 arcos * 2 kWh.
    assert all(a.energy_kwh == 1 for a in instance.arcs)  # Snapshot nominal conservado.
    assert arc_energy(Arc(from_node_id="x", to_node_id="y", energy_kwh=-2), instance.operations) == -2


@pytest.mark.solver
def test_windows_allow_wait_and_require_service_completion(backend):
    instance = tiny(
        service_seconds=50, max_route_seconds=500, use_customer_time_windows=True,
        customer_time_windows={
            "A": {"open_seconds": 200, "close_seconds": 250},
            "B": {"open_seconds": 0, "close_seconds": 100},
        },
    )
    solution = solve(instance, backend)
    assert solution.served_visit_ids == ["A"]  # B llega a 60, pero termina a 110 > 100.
    visit = next(s for r in solution.routes for s in r.steps if s.delivered_visit_ids)
    assert visit.arrival_seconds == 60
    assert visit.service_start_seconds == 200
    assert visit.departure_seconds == 250
    model = build_model(instance)
    _load_initial_values(model, instance, solution)
    for con in model.component_data_objects(pyo.Constraint, active=True):
        value = pyo.value(con.body)
        assert con.lower is None or value >= pyo.value(con.lower) - 1e-6, con.name
        assert con.upper is None or value <= pyo.value(con.upper) + 1e-6, con.name


@pytest.mark.solver
def test_passing_customer_does_not_apply_its_window_or_service(backend):
    instance = ProblemInstance(
        nodes=[Node(node_id=i, node_type=t) for i, t in [("0", "base"), ("A", "visit"), ("B", "visit")]],
        arcs=[
            Arc(from_node_id=i, to_node_id=j, energy_kwh=1, travel_time_seconds=10)
            for i, j in [("0", "A"), ("A", "B"), ("B", "A"), ("A", "0")]
        ],
        parameters=ModelParameters(
            vehicle_count=1, movement_limit=4, battery_capacity_kwh=10, reserve_kwh=1,
        ),
        operations=Operations(
            service_seconds_by_customer={"A": 100, "B": 5},
            max_route_seconds=50, use_customer_time_windows=True,
            customer_time_windows={"A": {"open_seconds": 0, "close_seconds": 0}},
        ),
    )
    solution = solve(instance, backend)
    assert solution.served_visit_ids == ["B"]
    assert solution.routes[0].duration_seconds == 45


@pytest.mark.parametrize("options", [
    {"service_seconds": -1},
    {"charging_efficiency": 0},
    {"assumed_speed_kph": 0},
    {"use_customer_time_windows": True},
    {"use_customer_time_windows": True, "customer_time_windows": {"A": {"open_seconds": 0, "close_seconds": 50}}},
    {"customer_time_windows": {"A": {"open_seconds": 50, "close_seconds": 0}}},
    {"service_seconds_by_customer": {"unknown": 1}},
    {"disabled_charger_ids": ["unknown"]},
])
def test_invalid_operational_configuration_is_actionable(options):
    with pytest.raises(ValidationError):
        tiny(**options)


def test_temporal_charging_requires_explicit_effective_power():
    with pytest.raises(ValidationError, match="potencia efectiva"):
        charging_case(charging_power_kw=None)
    with pytest.raises(ValidationError, match="supera max_power_kw"):
        charging_case(charging_power_kw=51)
    with pytest.raises(ValidationError, match="include_charging_time"):
        charging_case(include_charging_time=False)


def test_missing_times_need_explicit_speed_and_customer_durations_can_be_overridden():
    data = tiny(service_seconds=50, service_seconds_by_customer={"A": 80}).model_dump()
    for arc in data["arcs"]:
        arc["travel_time_seconds"] = None
    with pytest.raises(ValidationError, match="assumed_speed_kph"):
        ProblemInstance.model_validate(data)
    data["operations"]["assumed_speed_kph"] = 36
    instance = ProblemInstance.model_validate(data)
    solution = build_greedy_start(instance)
    assert solution is not None
    assert sorted(s.service_duration_seconds for r in solution.routes for s in r.steps if s.delivered_visit_ids) == [50, 80]
    assert all(s.travel_time_seconds == 50 for r in solution.routes for s in r.steps if s.next_node_id and s.node_id != s.next_node_id)


@pytest.mark.parametrize("change", ["arrival", "service", "charging", "total", "window", "reserve"])
def test_independent_checker_rejects_corrupted_operational_results(change):
    instance = tiny(
        service_seconds=20, max_route_seconds=300, final_reserve_soc=0.2,
        use_customer_time_windows=True,
        customer_time_windows={"A": {"open_seconds": 100, "close_seconds": 180}},
    )
    solution = build_greedy_start(instance)
    assert solution and len(solution.served_visit_ids) == 2
    step = next(s for r in solution.routes for s in r.steps if "A" in s.delivered_visit_ids)
    if change == "arrival":
        step.arrival_seconds += 1
    elif change == "service":
        step.service_duration_seconds = 0
    elif change == "charging":
        step.charging_duration_seconds = 1
    elif change == "total":
        solution.routes[0].duration_seconds += 1
    elif change == "window":
        instance.operations.customer_time_windows["A"].close_seconds = 105
    else:
        instance.operations.final_reserve_soc = 0.59
    assert not validate_solution(instance, solution).feasible


def test_horizon_certificate_disabled_only_when_hypotheses_change():
    road = tiny()
    compact, _ = build_service_graph(road, 3)
    assert analyze_horizon(compact).recommended_horizon == 3
    for options in [
        Operations(max_route_seconds=300),
        Operations(final_reserve_soc=0.2),
    ]:
        changed = ProblemInstance.model_validate({**dict(compact), "operations": options})
        result = analyze_horizon(changed)
        assert result.status == "not_certified"
        assert result.structural_upper_bound is None
    changed = ProblemInstance.model_validate({
        **dict(compact), "operations": Operations(energy_margin_fraction=0.1),
    })
    assert analyze_horizon(changed).tour_energy_kwh == pytest.approx(3.3)


def test_cli_reuses_dijkstra_paths_and_updates_hashes_without_mutating_inputs(tmp_path, monkeypatch, capsys):
    road = tiny()
    compact, archive = build_service_graph(road, 3)
    source, services, paths = [tmp_path / name for name in ["road.json", "services.json", "paths.json"]]
    save_instance(road, source)
    save_instance(compact, services)
    paths.write_text(archive.model_dump_json())
    original = services.read_bytes()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"operations": {
        "service_seconds": 100, "max_route_seconds": 250, "energy_margin_fraction": 0.1,
    }}))
    output, outpaths = tmp_path / "new.json", tmp_path / "new-paths.json"

    def forbidden(*args, **kwargs):
        pytest.fail("No volver a ejecutar Dijkstra al reutilizar el grafo")

    monkeypatch.setattr(cli, "build_service_graph", forbidden)
    args = [
        "service-graph", "--road-instance", str(source), "--reuse-instance", str(services),
        "--reuse-path-archive", str(paths), "--config", str(config),
        "--output", str(output), "--path-archive", str(outpaths),
    ]
    assert cli.main([*args, "--service-movements", "auto"]) == 2  # Referencia posicional.
    assert "H explícito" in capsys.readouterr().err
    assert cli.main(args + ["--service-movements", "3"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reused_service_graph"] and not summary["horizon_certified"]
    configured = load_instance(output)
    new_archive = PathArchive.model_validate_json(outpaths.read_text())
    assert new_archive.service_instance_sha256 == fingerprint(configured)
    assert fingerprint(compact) != fingerprint(configured)
    assert services.read_bytes() == original
    candidate = build_greedy_start(configured)
    _, report, _ = expand_and_validate(configured, road, new_archive, candidate)
    assert report.feasible, report.violations
    assert candidate.net_energy_kwh == pytest.approx(4.4)


def test_expansion_keeps_margin_times_and_pass_through_semantics():
    road = ProblemInstance(
        nodes=[Node(node_id=i, node_type=t) for i, t in [
            ("0", "base"), ("j", "junction"), ("A", "visit"),
        ]],
        arcs=[
            Arc(from_node_id=i, to_node_id=j, energy_kwh=1, distance_m=100, travel_time_seconds=t)
            for i, j, t in [("0", "j", 10), ("j", "A", 20), ("A", "0", 30)]
        ],
        parameters=ModelParameters(
            vehicle_count=1, movement_limit=3, battery_capacity_kwh=10, reserve_kwh=1,
        ),
        operations=Operations(
            service_seconds=40, energy_margin_fraction=0.2, max_route_seconds=100,
        ),
    )
    compact, archive = build_service_graph(road, 2)
    candidate = build_greedy_start(compact)
    assert candidate and candidate.served_visit_ids == ["A"]
    expanded, report, counts = expand_and_validate(compact, road, archive, candidate)
    assert report.feasible, report.violations
    assert expanded.net_energy_kwh == pytest.approx(3.6)
    assert expanded.routes[0].duration_seconds == pytest.approx(100)
    assert counts == {"vehicle_1": 3}
    assert expanded.routes[0].steps[1].service_duration_seconds == 0
