"""Comprobaciones del PDF con recorridos explícitos y óptimos independientes."""

from __future__ import annotations

from fractions import Fraction
from random import Random

import pyomo.environ as pyo
import pytest
from oracle import integer_walk_oracle, no_charge_walk_oracle

from ev_routing import validation
from ev_routing.contracts import Arc, ModelParameters, Node, ProblemInstance
from ev_routing.model import activate_energy_phase, build_model, extract_solution


def _instance(
    *,
    nodes: list[tuple[str, str]],
    arcs: list[tuple[str, str, float]],
    movements: int,
    vehicles: int = 1,
    initial_soc: float = 0.6,
) -> ProblemInstance:
    """Usar IDs opacos y unidades pequeñas para poder revisar cada cálculo."""
    return ProblemInstance(
        name="tiny_model_fixture",
        nodes=[
            Node(
                node_id=node,
                node_type=kind,
                connector_types=["J1772"] if kind == "charger" else [],
            )
            for node, kind in nodes
        ],
        arcs=[
            Arc(from_node_id=origin, to_node_id=destination, energy_kwh=energy)
            for origin, destination, energy in arcs
        ],
        parameters=ModelParameters(
            vehicle_count=vehicles,
            battery_capacity_kwh=10,
            reserve_kwh=1,
            initial_soc=initial_soc,
            movement_limit=movements,
        ),
    )


def _revisit_instance() -> ProblemInstance:
    return _instance(
        nodes=[("depot", "base"), ("client", "visit"), ("station", "charger")],
        arcs=[
            ("depot", "client", 1),
            ("client", "station", 1),
            ("station", "client", 1),
            ("client", "depot", 1),
        ],
        movements=4,
        vehicles=2,
    )


def _saturation_instance() -> ProblemInstance:
    return _instance(
        nodes=[("depot", "base"), ("downhill", "junction"), ("client", "visit")],
        arcs=[("depot", "downhill", -8), ("downhill", "client", 7), ("client", "depot", 1)],
        movements=3,
    )


def _scarce_energy_instance() -> ProblemInstance:
    return _instance(
        nodes=[
            ("depot", "base"),
            ("near", "visit"),
            ("far", "visit"),
            ("unreachable", "visit"),
            ("station", "charger"),
        ],
        arcs=[
            ("depot", "near", 2),
            ("near", "depot", 2),
            ("depot", "far", 4),
            ("far", "station", 1),
            ("station", "depot", 2),
            ("depot", "station", -2),
            ("station", "near", 1),
            ("depot", "unreachable", 6),
            ("unreachable", "depot", 6),
        ],
        movements=4,
        vehicles=2,
    )


def _assign_walks(
    model: pyo.ConcreteModel,
    walks: dict[str, list[str]],
    *,
    charges: dict[tuple[str, int], float] | None = None,
    deliveries: set[tuple[str, str, int]] | None = None,
) -> None:
    """Cargar un punto explícito; también permite construir puntos infactibles."""
    charges = charges or {}
    deliveries = deliveries or set()
    for variable in model.component_data_objects(pyo.Var):
        variable.set_value(0, skip_validation=True)
    total_energy = 0.0
    for vehicle in model.K:
        walk = walks.get(vehicle, [model.depot_id] * len(model.R))
        assert len(walk) == len(model.R)
        battery = float(pyo.value(model.initial_energy))
        for position, node in enumerate(walk):
            model.z[node, vehicle, position].set_value(1)
            model.b[vehicle, position].set_value(battery, skip_validation=True)
            if position not in model.R_moves:
                continue
            destination = walk[position + 1]
            model.x[node, destination, vehicle, position].set_value(1)
            charge = charges.get((vehicle, position), 0.0)
            departure = battery + charge
            uncapped = departure - float(pyo.value(model.e[node, destination]))
            arrival = min(float(pyo.value(model.B)), uncapped)
            energy = departure - arrival
            model.q[vehicle, position].set_value(charge, skip_validation=True)
            model.b_departure[vehicle, position].set_value(departure, skip_validation=True)
            model.u[vehicle, position].set_value(uncapped)
            model.gamma[vehicle, position].set_value(int(uncapped > pyo.value(model.B)))
            model.E[vehicle, position].set_value(energy)
            total_energy += energy
            battery = arrival
    for customer, vehicle, position in deliveries:
        model.a[customer, vehicle, position].set_value(1)
        model.y[customer].set_value(1)
    model.E_total.set_value(total_energy)


def _violations(model: pyo.ConcreteModel) -> list[str]:
    """Evaluar dominios y desigualdades del punto, sin ejecutar ningún solver."""
    violations = []
    tolerance = 1e-8
    for variable in model.component_data_objects(pyo.Var):
        value = pyo.value(variable)
        if variable.lb is not None and value < variable.lb - tolerance:
            violations.append(f"{variable.name}:lower")
        if variable.ub is not None and value > variable.ub + tolerance:
            violations.append(f"{variable.name}:upper")
        if variable.is_binary() and min(abs(value), abs(value - 1)) > tolerance:
            violations.append(f"{variable.name}:binary")
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(constraint.body)
        if constraint.lower is not None and body < pyo.value(constraint.lower) - tolerance:
            violations.append(f"{constraint.name}:lower")
        if constraint.upper is not None and body > pyo.value(constraint.upper) + tolerance:
            violations.append(f"{constraint.name}:upper")
    return violations


def test_dimensions_domains_and_only_the_depot_dummy_are_preserved():
    instance = _revisit_instance()
    model = build_model(instance)
    nodes, arcs, customers, vehicles, movements = 3, 5, 1, 2, 4
    assert set(model.A) == {
        (arc.from_node_id, arc.to_node_id) for arc in instance.arcs
    } | {("depot", "depot")}
    assert len(model.z) == nodes * vehicles * (movements + 1)
    assert len(model.x) == arcs * vehicles * movements
    assert len(model.a) == customers * vehicles * movements
    assert len(model.y) == customers
    assert len(model.b) == vehicles * (movements + 1)
    for component in (model.q, model.b_departure, model.u, model.gamma, model.E):
        assert len(component) == vehicles * movements
    for component in (model.y, model.z, model.x, model.a, model.gamma):
        assert all(variable.is_binary() for variable in component.values())
    assert model.q["vehicle_1", 0].lb == 0
    assert model.E["vehicle_1", 0].lb is None
    assert model.u["vehicle_1", 0].ub is None
    assert model.b["vehicle_1", 0].bounds == (1, 10)
    assert pyo.value(model.M) == 11
    assert [objective.name for objective in model.component_objects(pyo.Objective, active=True)] == [
        "deliveries_objective"
    ]


def test_customer_can_be_crossed_before_delivery_and_idle_vehicle_is_retained():
    instance = _revisit_instance()
    model = build_model(instance)
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "client", "station", "client", "depot"]},
        charges={("vehicle_1", 2): 3},
        deliveries={("client", "vehicle_1", 3)},
    )
    assert _violations(model) == []
    solution = extract_solution(model, instance)
    first, idle = solution.routes
    assert first.steps[1].delivered_visit_ids == []
    assert first.steps[3].delivered_visit_ids == ["client"]
    assert first.steps[2].charged_to_battery_kwh == 3
    assert first.net_energy_kwh == 4
    assert all(step.node_id == "depot" for step in idle.steps)
    assert idle.net_energy_kwh == 0
    assert solution.served_visit_ids == ["client"]
    assert first.steps[-1].next_node_id is None
    assert first.steps[-1].charged_to_battery_kwh == 0


def test_repeated_delivery_is_rejected_even_at_the_same_customer():
    model = build_model(_revisit_instance())
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "client", "station", "client", "depot"]},
        deliveries={("client", "vehicle_1", 1), ("client", "vehicle_1", 3)},
    )
    assert any("eq06_unique_delivery" in violation for violation in _violations(model))


def test_delivery_cannot_be_claimed_from_another_location():
    model = build_model(_revisit_instance())
    _assign_walks(model, {}, deliveries={("client", "vehicle_1", 1)})
    assert any("eq05_service_location" in violation for violation in _violations(model))


def test_intermediate_depot_return_does_not_force_the_vehicle_to_stay():
    model = build_model(_revisit_instance())
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "client", "depot", "client", "depot"]},
        deliveries={("client", "vehicle_1", 3)},
    )
    assert _violations(model) == []


def test_depot_charging_is_forbidden_at_initial_and_intermediate_positions():
    model = build_model(_revisit_instance())
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "client", "depot", "client", "depot"]},
        charges={("vehicle_1", 0): 1, ("vehicle_1", 2): 1},
    )
    violations = _violations(model)
    assert any("eq07_initial_charge" in violation for violation in violations)
    assert any("eq10_compatible_charge[vehicle_1,2]" in violation for violation in violations)


def test_incompatible_station_does_not_allow_charging():
    instance = _revisit_instance()
    instance = instance.model_copy(
        update={"compatible_chargers": {"vehicle_1": [], "vehicle_2": ["station"]}}
    )
    model = build_model(instance)
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "client", "station", "client", "depot"]},
        charges={("vehicle_1", 2): 1},
    )
    assert any(
        "eq10_compatible_charge[vehicle_1,2]" in violation for violation in _violations(model)
    )


def test_saturation_discards_regeneration_and_energy_uses_actual_battery():
    instance = _saturation_instance()
    model = build_model(instance)
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "downhill", "client", "depot"]},
        deliveries={("client", "vehicle_1", 2)},
    )
    assert _violations(model) == []
    assert pyo.value(model.u["vehicle_1", 0]) == 14
    assert pyo.value(model.gamma["vehicle_1", 0]) == 1
    assert pyo.value(model.b["vehicle_1", 1]) == 10
    assert pyo.value(model.E["vehicle_1", 0]) == -4
    assert sum(arc.energy_kwh for arc in instance.arcs) == 0
    assert pyo.value(model.E_total) == 4
    assert extract_solution(model, instance).net_energy_kwh == 4
    model.gamma["vehicle_1", 0].set_value(0)
    assert any("eq13_uncapped_branch" in violation for violation in _violations(model))


@pytest.mark.parametrize("saturation_branch", [0, 1])
def test_both_saturation_branches_are_valid_exactly_at_capacity(saturation_branch):
    instance = _instance(
        nodes=[("depot", "base"), ("downhill", "junction"), ("client", "visit")],
        arcs=[("depot", "downhill", -4), ("downhill", "client", 1), ("client", "depot", 1)],
        movements=3,
    )
    model = build_model(instance)
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "downhill", "client", "depot"]},
        deliveries={("client", "vehicle_1", 2)},
    )
    assert pyo.value(model.u["vehicle_1", 0]) == pyo.value(model.B)
    model.gamma["vehicle_1", 0].set_value(saturation_branch)
    assert _violations(model) == []
    solution = extract_solution(model, instance)
    assert solution.net_energy_kwh == -2
    assert validation.validate_solution(instance, solution).feasible


def test_unjustified_battery_discard_is_forbidden_below_capacity():
    model = build_model(_revisit_instance())
    _assign_walks(model, {})
    model.b["vehicle_1", 1].set_value(5)
    assert any("eq13_uncapped_branch" in violation for violation in _violations(model))


def test_intermediate_deficit_cannot_be_hidden_by_later_regeneration():
    instance = _instance(
        nodes=[("depot", "base"), ("uphill", "junction"), ("client", "visit")],
        arcs=[("depot", "uphill", 8), ("uphill", "client", -8), ("client", "depot", 1)],
        movements=3,
    )
    model = build_model(instance)
    _assign_walks(
        model,
        {"vehicle_1": ["depot", "uphill", "client", "depot"]},
        deliveries={("client", "vehicle_1", 2)},
    )
    assert pyo.value(model.b["vehicle_1", 3]) == 5
    assert "b[vehicle_1,1]:lower" in _violations(model)


def test_initial_soc_is_scenario_configuration_and_no_customers_is_valid():
    instance = _instance(nodes=[("base-x", "base")], arcs=[], movements=1, initial_soc=0.8)
    model = build_model(instance)
    _assign_walks(model, {})
    assert _violations(model) == []
    assert pyo.value(model.initial_energy) == 8
    activate_energy_phase(model, 0)
    assert _violations(model) == []
    assert extract_solution(model, instance).served_visit_ids == []


def test_isolated_customer_does_not_break_empty_adjacency_constraints():
    instance = _instance(
        nodes=[("depot", "base"), ("isolated", "visit")], arcs=[], movements=2
    )
    model = build_model(instance)
    _assign_walks(model, {})
    assert _violations(model) == []
    model.z["isolated", "vehicle_1", 1].set_value(1)
    assert any("eq03_departure[isolated" in violation for violation in _violations(model))


def test_second_phase_fixes_deliveries_without_claiming_an_optimality_certificate():
    model = build_model(_revisit_instance())
    activate_energy_phase(model, 1)
    assert not model.deliveries_objective.active
    assert model.energy_objective.active
    assert model.served_count_constraint.active
    assert pyo.value(model.served_count_target) == 1
    # Volver a preparar la fase no duplica restricciones ni cambia la formulación.
    activate_energy_phase(model, 0)
    assert pyo.value(model.served_count_target) == 0
    for invalid in (-1, 2, 0.5, True):
        with pytest.raises(ValueError, match="served_count"):
            activate_energy_phase(model, invalid)


def test_extraction_rejects_absent_fractional_or_disconnected_values():
    instance = _revisit_instance()
    model = build_model(instance)
    with pytest.raises(ValueError, match="sin valor"):
        extract_solution(model, instance)
    _assign_walks(model, {})
    model.y["client"].set_value(0.25, skip_validation=True)
    with pytest.raises(ValueError, match="no binario"):
        extract_solution(model, instance)
    _assign_walks(model, {})
    model.x["depot", "depot", "vehicle_1", 0].set_value(0)
    with pytest.raises(ValueError, match="arco inconsistente"):
        extract_solution(model, instance)


@pytest.fixture(scope="module")
def installed_solver(record_testsuite_property):
    """Gurobi primero y SCIP después; una licencia ausente no invalida tests puros."""
    errors = []
    for name in ("gurobi_direct", "scip"):
        try:
            solver = pyo.SolverFactory(name)
            if not solver.available(exception_flag=False):
                errors.append(f"{name}: no disponible")
                continue
            probe = pyo.ConcreteModel()
            probe.x = pyo.Var(domain=pyo.Binary)
            probe.objective = pyo.Objective(expr=probe.x, sense=pyo.maximize)
            result = solver.solve(probe)
            if not pyo.check_optimal_termination(result):
                errors.append(f"{name}: la prueba de licencia no terminó óptima")
                continue
            record_testsuite_property("model_test_solver", name)
            record_testsuite_property("model_test_solver_version", str(solver.version()))
            return solver
        except Exception as error:
            errors.append(f"{name}: {type(error).__name__}: {error}")
    pytest.skip("; ".join(errors))


@pytest.mark.solver
@pytest.mark.parametrize(
    ("make_instance", "known_optimum"),
    [
        (_saturation_instance, (1, 4)),
        (_scarce_energy_instance, (2, 8)),
    ],
)
def test_lexicographic_optimum_matches_independent_exhaustive_walks(
    installed_solver, make_instance, known_optimum
):
    instance = make_instance()
    assert integer_walk_oracle(instance) == known_optimum
    model = build_model(instance)
    first = installed_solver.solve(model)
    assert pyo.check_optimal_termination(first)
    served = round(pyo.value(model.served_count))
    assert served == known_optimum[0]
    activate_energy_phase(model, served)
    second = installed_solver.solve(model)
    assert pyo.check_optimal_termination(second)
    assert pyo.value(model.E_total) == pytest.approx(known_optimum[1], abs=1e-6)
    solution = extract_solution(model, instance)
    assert len(solution.served_visit_ids) == known_optimum[0]
    assert solution.net_energy_kwh == pytest.approx(known_optimum[1], abs=1e-6)
    assert _violations(model) == []


def _solve_against_oracle(
    solver,
    instance: ProblemInstance,
    *,
    fractional_without_charge: bool = False,
):
    """Comparar ambas fases y verificar sus dos incumbentes fuera de Pyomo."""
    oracle = no_charge_walk_oracle if fractional_without_charge else integer_walk_oracle
    expected_count, expected_energy = oracle(instance)
    model = build_model(instance)
    first_result = solver.solve(model)
    assert pyo.check_optimal_termination(first_result)
    assert pyo.value(model.served_count) == pytest.approx(expected_count, abs=1e-6)
    first_solution = extract_solution(model, instance)
    first_validation = validation.validate_solution(instance, first_solution)
    assert first_validation.feasible, first_validation.violations
    assert len(first_solution.served_visit_ids) == expected_count

    activate_energy_phase(model, expected_count)
    second_result = solver.solve(model)
    assert pyo.check_optimal_termination(second_result)
    assert pyo.value(model.served_count) == pytest.approx(expected_count, abs=1e-6)
    assert pyo.value(model.E_total) == pytest.approx(float(expected_energy), abs=1e-6)
    solution = extract_solution(model, instance)
    final_validation = validation.validate_solution(instance, solution)
    assert final_validation.feasible, final_validation.violations
    assert solution.net_energy_kwh == pytest.approx(float(expected_energy), abs=1e-6)
    assert _violations(model) == []
    return model, solution


def _seeded_instance(seed: int, *, fractional_without_charge: bool) -> ProblemInstance:
    """Generar redes dirigidas pequeñas sin mirar el resultado del solver."""
    rng = Random(seed)
    depot = f"depot:{seed}"
    visits = [f"customer:{seed}:{index}" for index in range(2 + seed % 2)]
    junction = f"junction:{seed}"
    station = f"charger:{seed}"
    node_specs = [
        (depot, "base"),
        *((node, "visit") for node in visits),
        (junction, "junction"),
    ]
    with_charger = not fractional_without_charge and seed % 3 != 0
    if with_charger:
        node_specs.append((station, "charger"))
    values = (
        [-2.75, -1.25, 0.0, 0.75, 1.5, 3.25, 5.5]
        if fractional_without_charge
        else list(range(-3, 6))
    )
    arcs = {}
    for origin, _ in node_specs:
        for destination, _ in node_specs:
            if origin != destination and rng.random() < 0.4:
                arcs[origin, destination] = rng.choice(values)
    # Al menos una entrega es posible; las demás dependen de la red y la energía.
    arcs[depot, visits[0]] = 1.25 if fractional_without_charge else rng.choice([1, 2])
    arcs[visits[0], depot] = 1.75 if fractional_without_charge else rng.choice([1, 2])
    rng.shuffle(node_specs)
    instance = _instance(
        nodes=node_specs,
        arcs=[(origin, destination, energy) for (origin, destination), energy in arcs.items()],
        movements=3 + seed % 3,
        vehicles=1 + seed % 2,
    )
    if with_charger and seed % 2:
        # Un vehículo no puede cargar; el otro sí. No inferir compatibilidad global.
        instance = ProblemInstance.model_validate(
            instance.model_dump() | {
                "compatible_chargers": {"vehicle_1": [], "vehicle_2": [station]}
            }
        )
    return instance


@pytest.mark.solver
@pytest.mark.parametrize("seed", range(12), ids=lambda seed: f"integer-seed-{seed}")
def test_seeded_integer_networks_have_exact_continuous_charge_optima(installed_solver, seed):
    instance = _seeded_instance(seed, fractional_without_charge=False)
    _solve_against_oracle(installed_solver, instance)


@pytest.mark.solver
@pytest.mark.parametrize("seed", range(20, 26), ids=lambda seed: f"fractional-seed-{seed}")
def test_seeded_fractional_networks_match_exact_no_charge_enumeration(installed_solver, seed):
    instance = _seeded_instance(seed, fractional_without_charge=True)
    _solve_against_oracle(installed_solver, instance, fractional_without_charge=True)


@pytest.mark.solver
def test_optimal_route_crosses_an_articulation_customer_twice_but_delivers_once(installed_solver):
    instance = _instance(
        nodes=[("depot", "base"), ("bridge", "visit"), ("leaf", "visit")],
        arcs=[
            ("depot", "bridge", 1),
            ("bridge", "depot", 1),
            ("bridge", "leaf", 1),
            ("leaf", "bridge", 1),
        ],
        movements=4,
    )
    assert integer_walk_oracle(instance) == (2, 4)
    _, solution = _solve_against_oracle(installed_solver, instance)
    bridge_steps = [step for step in solution.routes[0].steps if step.node_id == "bridge"]
    assert len(bridge_steps) == 2
    assert sum("bridge" in step.delivered_visit_ids for step in bridge_steps) == 1


@pytest.mark.solver
def test_optimal_route_must_leave_after_an_intermediate_depot_return(installed_solver):
    instance = _instance(
        nodes=[("depot", "base"), ("left", "visit"), ("right", "visit")],
        arcs=[
            ("depot", "left", 1), ("left", "depot", 1),
            ("depot", "right", 1), ("right", "depot", 1),
        ],
        movements=4,
    )
    assert integer_walk_oracle(instance) == (2, 4)
    _, solution = _solve_against_oracle(installed_solver, instance)
    steps = solution.routes[0].steps
    assert steps[2].node_id == "depot"
    assert steps[3].node_id in {"left", "right"}
    assert steps[1].node_id != steps[3].node_id


@pytest.mark.solver
def test_two_positive_charges_at_the_same_station_are_necessary(installed_solver):
    instance = _instance(
        nodes=[("depot", "base"), ("station", "charger"), ("client", "visit")],
        arcs=[
            ("depot", "station", 1),
            ("station", "client", 4),
            ("client", "station", 5),
            ("station", "depot", 2),
        ],
        movements=4,
    )
    assert integer_walk_oracle(instance) == (1, 12)
    _, solution = _solve_against_oracle(installed_solver, instance)
    steps = solution.routes[0].steps
    assert [step.node_id for step in steps] == [
        "depot", "station", "client", "station", "depot"
    ]
    assert steps[1].charged_to_battery_kwh == pytest.approx(5)
    assert steps[3].charged_to_battery_kwh >= 2 - 1e-6
    assert solution.net_energy_kwh == pytest.approx(12)


@pytest.mark.solver
def test_integer_oracle_does_not_impose_integer_charging_on_the_milp(installed_solver):
    instance = _instance(
        nodes=[("depot", "base"), ("station", "charger"), ("client", "visit")],
        arcs=[("depot", "station", 1), ("station", "client", 1), ("client", "depot", 1)],
        movements=3,
    )
    assert integer_walk_oracle(instance) == (1, 3)
    model, _ = _solve_against_oracle(installed_solver, instance)
    # Hay un óptimo entero, pero una recarga fraccionaria también es óptima:
    # el objetivo mide consumo en tramos, no energía comprada o batería final.
    model.q["vehicle_1", 1].fix(0.5)
    result = installed_solver.solve(model)
    assert pyo.check_optimal_termination(result)
    solution = extract_solution(model, instance)
    assert solution.routes[0].steps[1].charged_to_battery_kwh == pytest.approx(0.5)
    assert solution.net_energy_kwh == pytest.approx(3)
    report = validation.validate_solution(instance, solution)
    assert report.feasible, report.violations


@pytest.mark.solver
def test_later_regeneration_does_not_make_an_intermediate_deficit_feasible(installed_solver):
    instance = _instance(
        nodes=[("depot", "base"), ("uphill", "junction"), ("client", "visit")],
        arcs=[("depot", "uphill", 8), ("uphill", "client", -8), ("client", "depot", 1)],
        movements=3,
    )
    # El saldo final de la caminata sería 5 kWh, pero el primer tramo deja -2.
    assert sum(arc.energy_kwh for arc in instance.arcs) == 1
    assert integer_walk_oracle(instance) == (0, 0)
    _, solution = _solve_against_oracle(installed_solver, instance)
    assert all(step.node_id == "depot" for step in solution.routes[0].steps)


@pytest.mark.solver
@pytest.mark.parametrize(("return_energy", "deliveries"), [(3.0, 1), (3.25, 0)])
def test_reserve_at_return_is_inclusive_and_cannot_be_violated(
    installed_solver, return_energy, deliveries
):
    instance = _instance(
        nodes=[("depot", "base"), ("client", "visit")],
        arcs=[("depot", "client", 2), ("client", "depot", return_energy)],
        movements=2,
    )
    expected_energy = Fraction(5) if deliveries else Fraction(0)
    assert no_charge_walk_oracle(instance) == (deliveries, expected_energy)
    _, solution = _solve_against_oracle(
        installed_solver, instance, fractional_without_charge=True
    )
    if deliveries:
        assert solution.routes[0].steps[-1].battery_arrival_kwh == pytest.approx(1)


@pytest.mark.solver
@pytest.mark.parametrize(("movements", "energy"), [(4, 0), (8, -4)])
def test_signed_gain_cycle_is_bounded_by_movements_and_capacity(installed_solver, movements, energy):
    # Caso algebraico deliberado: no se afirma que sea una predicción física real.
    instance = _instance(
        nodes=[("depot", "base"), ("gain", "junction"), ("client", "visit")],
        arcs=[
            ("depot", "gain", -2), ("gain", "depot", 0),
            ("depot", "client", 1), ("client", "depot", 1),
        ],
        movements=movements,
    )
    assert no_charge_walk_oracle(instance) == (1, energy)
    _, solution = _solve_against_oracle(
        installed_solver, instance, fractional_without_charge=True
    )
    assert solution.net_energy_kwh >= -4 - 1e-6
    assert len(solution.routes[0].steps) == movements + 1


@pytest.mark.solver
@pytest.mark.parametrize(("movements", "deliveries", "energy"), [(3, 0, 0), (4, 1, 4)])
def test_exact_movement_limit_changes_reachable_deliveries(
    installed_solver, movements, deliveries, energy
):
    instance = _instance(
        nodes=[
            ("depot", "base"), ("out", "junction"),
            ("client", "visit"), ("back", "junction"),
        ],
        arcs=[
            ("depot", "out", 1), ("out", "client", 1),
            ("client", "back", 1), ("back", "depot", 1),
        ],
        movements=movements,
    )
    assert integer_walk_oracle(instance) == (deliveries, energy)
    _, solution = _solve_against_oracle(installed_solver, instance)
    assert len(solution.served_visit_ids) == deliveries


@pytest.mark.solver
@pytest.mark.parametrize(("vehicles", "deliveries"), [(1, 1), (2, 2)])
def test_assignment_to_two_vehicles_increases_service_under_the_same_h(
    installed_solver, vehicles, deliveries
):
    instance = _instance(
        nodes=[("depot", "base"), ("left", "visit"), ("right", "visit")],
        arcs=[
            ("depot", "left", 1), ("left", "depot", 1),
            ("depot", "right", 1), ("right", "depot", 1),
        ],
        movements=2,
        vehicles=vehicles,
    )
    assert integer_walk_oracle(instance) == (deliveries, 2 * deliveries)
    _, solution = _solve_against_oracle(installed_solver, instance)
    assert all(
        sum(len(step.delivered_visit_ids) for step in route.steps) == 1
        for route in solution.routes
    )


def test_oracles_reject_unsupported_charging_or_fractional_grid_assumptions():
    fraction_instance = _instance(
        nodes=[("depot", "base"), ("client", "visit")],
        arcs=[("depot", "client", 0.25), ("client", "depot", 0.5)],
        movements=2,
    )
    assert no_charge_walk_oracle(fraction_instance) == (1, Fraction(3, 4))
    with pytest.raises(ValueError, match="energías enteras"):
        integer_walk_oracle(fraction_instance)
    with pytest.raises(ValueError, match="F_k vacío"):
        no_charge_walk_oracle(_revisit_instance())
