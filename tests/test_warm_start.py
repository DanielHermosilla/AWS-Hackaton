"""Arranques factibles, soporte real del adaptador y conservación ante fallos."""

from copy import deepcopy

import pyomo.environ as pyo
import pytest
from pyomo.opt import SolverResults, SolverStatus, TerminationCondition

from ev_routing import pipeline, solve
from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    PhaseResult,
    ProblemInstance,
    RouteStep,
    Solution,
    SolverConfig,
    VehicleRoute,
)
from ev_routing.model import build_model, extract_solution
from ev_routing.validation import validate_solution


@pytest.fixture
def case():
    instance = ProblemInstance(
        nodes=[Node(node_id="base", node_type="base"), Node(node_id="A", node_type="visit")],
        arcs=[
            Arc(from_node_id="base", to_node_id="A", energy_kwh=1),
            Arc(from_node_id="A", to_node_id="base", energy_kwh=1),
        ],
        parameters=ModelParameters(
            vehicle_count=1, movement_limit=2, battery_capacity_kwh=10, reserve_kwh=1,
        ),
    )
    initial = Solution(
        routes=[VehicleRoute(
            vehicle_id="vehicle_1", net_energy_kwh=2,
            steps=[
                RouteStep(position=0, node_id="base", next_node_id="A",
                          battery_arrival_kwh=6, battery_departure_kwh=6,
                          predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
                RouteStep(position=1, node_id="A", next_node_id="base",
                          battery_arrival_kwh=5, battery_departure_kwh=5,
                          delivered_visit_ids=["A"],
                          predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
                RouteStep(position=2, node_id="base",
                          battery_arrival_kwh=4, battery_departure_kwh=4),
            ],
        )],
        served_visit_ids=["A"], unserved_visit_ids=[], net_energy_kwh=2,
    )
    return instance, initial


@pytest.mark.parametrize("regeneration", [False, True])
def test_values_are_complete_feasible_and_do_not_fix_variables(case, regeneration):
    instance, initial = case
    if regeneration:
        instance.arcs[0].energy_kwh = -8
        instance.arcs[1].energy_kwh = 7
        initial.routes[0].steps[0].predicted_arc_energy_kwh = -8
        initial.routes[0].steps[0].effective_arc_energy_kwh = -4
        initial.routes[0].steps[1].battery_arrival_kwh = 10
        initial.routes[0].steps[1].battery_departure_kwh = 10
        initial.routes[0].steps[1].predicted_arc_energy_kwh = 7
        initial.routes[0].steps[1].effective_arc_energy_kwh = 7
        initial.routes[0].steps[2].battery_arrival_kwh = 3
        initial.routes[0].steps[2].battery_departure_kwh = 3
        initial.routes[0].net_energy_kwh = initial.net_energy_kwh = 3
    assert validate_solution(instance, initial).feasible
    model = build_model(instance)
    solve._load_initial_values(model, instance, initial)
    assert all(v.value is not None and not v.fixed for v in model.component_data_objects(pyo.Var))
    extracted = extract_solution(model, instance)
    assert validate_solution(instance, extracted).feasible
    assert extracted.net_energy_kwh == initial.net_energy_kwh
    assert pyo.value(model.gamma["vehicle_1", 0]) == int(regeneration)
    # Además del checker independiente, comprobar que el vector puede enviarse
    # como MIP start de la plantilla concreta, incluidas auxiliares.
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(constraint.body)
        assert constraint.lower is None or body >= pyo.value(constraint.lower) - 1e-8
        assert constraint.upper is None or body <= pyo.value(constraint.upper) + 1e-8


def test_invalid_initial_solution_is_rejected_before_building_the_model(case, monkeypatch):
    instance, initial = case
    initial.routes[0].steps[1].battery_arrival_kwh = 100

    def forbidden(*args):
        pytest.fail("Una ruta inválida no debe llegar a construir el MILP")

    monkeypatch.setattr(solve, "build_model", forbidden)
    with pytest.raises(ValueError, match="Solución inicial inválida"):
        solve.solve_instance(instance, SolverConfig(solver="auto"), initial_solution=initial)
    with pytest.raises(ValueError, match="Solución inicial inválida"):
        pipeline.run_instance(instance, initial_solution=initial)


def test_initial_values_preserve_a_required_positive_charge(case):
    instance, _ = case
    instance.nodes.append(Node(node_id="C", node_type="charger", connector_types=["J1772"]))
    instance.parameters.movement_limit = 3
    instance.arcs = [
        Arc(from_node_id=i, to_node_id=j, energy_kwh=4)
        for i, j in [("base", "C"), ("C", "A"), ("A", "base")]
    ]
    steps = [
        RouteStep(
            position=r, node_id=node, next_node_id=target, battery_arrival_kwh=arrival,
            battery_departure_kwh=arrival + charge, charged_to_battery_kwh=charge,
            delivered_visit_ids=["A"] if node == "A" else [],
            predicted_arc_energy_kwh=4 if target else None,
            effective_arc_energy_kwh=4 if target else None,
        )
        for r, (node, target, arrival, charge) in enumerate([
            ("base", "C", 6, 0), ("C", "A", 2, 7),
            ("A", "base", 5, 0), ("base", None, 1, 0),
        ])
    ]
    seed = Solution(
        routes=[VehicleRoute(vehicle_id="vehicle_1", steps=steps, net_energy_kwh=12)],
        served_visit_ids=["A"], unserved_visit_ids=[], net_energy_kwh=12,
    )
    assert validate_solution(instance, seed).feasible
    model = build_model(instance)
    solve._load_initial_values(model, instance, seed)
    assert pyo.value(model.q["vehicle_1", 1]) == 7
    assert validate_solution(instance, extract_solution(model, instance)).feasible


@pytest.mark.parametrize("capable", [False, True])
def test_timeout_without_native_incumbent_keeps_seed_and_labels_its_origin(
    case, monkeypatch, capable
):
    instance, initial = case
    before = deepcopy(initial)

    class Backend:
        def __init__(self):
            self.options = {}
            self.calls = []

        def warm_start_capable(self):
            return capable

        def solve(self, model, **kwargs):
            self.calls.append(kwargs)
            result = SolverResults()
            result.solver.status = SolverStatus.ok
            result.solver.termination_condition = TerminationCondition.maxTimeLimit
            result.problem.number_of_solutions = 0
            result.problem.upper_bound = 1
            result.problem.lower_bound = 0
            return result

        def close(self):
            pass

    backend = Backend()
    monkeypatch.setattr(solve, "_make_backend", lambda name: solve._Backend(name, backend, "test"))
    result = solve.solve_instance(instance, SolverConfig(solver="gurobi"), initial_solution=initial)
    assert result.status == "feasible" and not result.lexicographic_optimal
    assert result.solution == initial == before
    assert result.solution_source == "initial_solution"
    assert all(p.incumbent_source == "provided_incumbent" for p in result.phases)
    assert all(p.termination_condition == "maxTimeLimit" for p in result.phases)
    assert [p.incumbent for p in result.phases] == [1, 2]
    assert [p.warm_start for p in result.phases] == [
        "submitted" if capable else "unsupported"
    ] * 2
    assert all(call.get("warmstart", False) == capable for call in backend.calls)


def test_budget_exhausted_before_solver_still_returns_the_validated_route(case, monkeypatch):
    instance, initial = case
    real_build = solve.build_model
    clock = [0.0]
    monkeypatch.setattr(solve, "monotonic", lambda: clock[0])

    def slow_build(instance):
        clock[0] = 2
        return real_build(instance)

    monkeypatch.setattr(solve, "build_model", slow_build)
    result = solve.solve_instance(
        instance, SolverConfig(solver="auto", time_limit_seconds=1), initial_solution=initial
    )
    assert result.solution == initial and result.status == "feasible"
    assert result.used_solver is None
    assert all(p.termination_condition == "maxTimeLimit" for p in result.phases)
    assert not result.lexicographic_optimal


def test_all_backends_unavailable_is_not_misreported_as_solver_success(case, monkeypatch):
    instance, initial = case

    def unavailable(name):
        raise solve._BackendUnavailable(f"{name}: no disponible")

    monkeypatch.setattr(solve, "_make_backend", unavailable)
    result = solve.solve_instance(instance, SolverConfig(solver="auto"), initial_solution=initial)
    assert result.solution == initial and result.status == "feasible"
    assert result.used_solver is None and result.solution_source == "initial_solution"
    assert not result.lexicographic_optimal
    assert all(p.termination_condition == "unavailable" for p in result.phases)
    assert all(p.warm_start == "not_requested" for p in result.phases)


def test_a_better_seed_contradicts_optimality_even_without_a_native_bound(case):
    _, initial = case
    native = initial.model_copy(deep=True)
    native.net_energy_kwh = 3
    phase = PhaseResult(
        name="energy", sense="minimize", status="optimal", termination_condition="optimal",
        has_solution=True, proven_optimal=True, incumbent=3, best_bound=None,
        incumbent_source="solver",
    )
    phase, selected = solve._retain_incumbent(phase, native, initial, SolverConfig(solver="auto"))
    assert selected == initial and phase.incumbent == 2
    assert not phase.proven_optimal and phase.status == "feasible"
    assert "certificado anterior incompatible" in phase.message


def test_wrong_fixed_count_cannot_reappear_as_an_energy_certificate(case):
    _, initial = case
    wrong = initial.model_copy(deep=True)
    wrong.served_visit_ids = []
    wrong.net_energy_kwh = 0
    phase = PhaseResult(
        name="energy", sense="minimize", status="optimal", termination_condition="optimal",
        has_solution=True, proven_optimal=True, incumbent=0, best_bound=0,
        incumbent_source="solver",
    )
    phase, candidate = solve._retain_incumbent(phase, wrong, initial, SolverConfig(solver="auto"))
    assert candidate == initial and phase.incumbent == 2
    assert not phase.proven_optimal and phase.best_bound is None
    assert "cambió el número" in phase.message


@pytest.mark.parametrize("name,sense", [("deliveries", "maximize"), ("energy", "minimize")])
def test_optimal_termination_without_native_vector_or_bound_does_not_certify_seed(case, name, sense):
    _, initial = case
    phase = PhaseResult(
        name=name, sense=sense, status="error", termination_condition="optimal",
        has_solution=False, proven_optimal=False,
        message="No se pudo extraer el vector nativo.",
    )
    phase, candidate = solve._retain_incumbent(phase, None, initial, SolverConfig(solver="auto"))
    assert candidate == initial and phase.has_solution
    assert not phase.proven_optimal and phase.status == "feasible"


@pytest.mark.solver
@pytest.mark.parametrize("backend", ["gurobi", "scip"])
def test_real_backends_report_actual_start_support_and_keep_known_optimum(case, backend, capfd):
    instance, initial = case
    result = solve.solve_instance(
        instance, SolverConfig(solver=backend, time_limit_seconds=10, tee=True),
        initial_solution=initial,
    )
    if any(p.termination_condition == "unavailable" for p in result.phases):
        pytest.skip("Backend no disponible: " + result.message)
    assert result.lexicographic_optimal
    assert result.solution.net_energy_kwh == 2
    assert validate_solution(instance, result.solution).feasible
    assert all(p.warm_start == ("submitted" if backend == "gurobi" else "unsupported")
               for p in result.phases)
    if backend == "gurobi":
        assert "Loaded user MIP start" in capfd.readouterr().out
