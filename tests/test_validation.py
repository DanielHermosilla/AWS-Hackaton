"""Rutas auditadas a mano: ninguna fixture se genera con Pyomo o el checker."""

import pytest

from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    ProblemInstance,
    RouteStep,
    Solution,
    VehicleRoute,
)
from ev_routing.validation import validate_solution


def step(position, node, arrival, *, following=None, predicted=None, effective=None, charge=0, deliveries=()):
    return RouteStep(
        position=position,
        node_id=node,
        battery_arrival_kwh=arrival,
        charged_to_battery_kwh=charge,
        battery_departure_kwh=arrival + charge,
        delivered_visit_ids=list(deliveries),
        next_node_id=following,
        predicted_arc_energy_kwh=predicted,
        effective_arc_energy_kwh=effective,
    )


def manual_example():
    """Batería 6→4→3, carga a 9, regenera hasta 10→9→7→5→5.

    El tramo -4 recupera solo 1 kWh por saturación. Energía neta = 7;
    balance 6 inicial + 6 recargada - 5 final = 7. Se revisitan base y V,
    atendiendo V una sola vez; el segundo vehículo permanece inactivo.
    """
    instance = ProblemInstance(
        nodes=[
            Node(node_id="B", node_type="base"),
            Node(node_id="V", node_type="visit"),
            Node(node_id="W", node_type="visit"),
            Node(node_id="C", node_type="charger", connector_types=["J1772"]),
            Node(node_id="J", node_type="junction"),
        ],
        arcs=[
            Arc(from_node_id="B", to_node_id="V", energy_kwh=2, distance_m=1000),
            Arc(from_node_id="V", to_node_id="C", energy_kwh=1, distance_m=500),
            Arc(from_node_id="C", to_node_id="J", energy_kwh=-4, distance_m=200),
            Arc(from_node_id="J", to_node_id="B", energy_kwh=1, distance_m=1500),
            Arc(from_node_id="V", to_node_id="B", energy_kwh=2, distance_m=1200),
        ],
        parameters=ModelParameters(
            battery_capacity_kwh=10, reserve_kwh=1, vehicle_count=2, movement_limit=7
        ),
    )
    active = VehicleRoute(
        vehicle_id="vehicle_1",
        net_energy_kwh=7,
        steps=[
            step(0, "B", 6, following="V", predicted=2, effective=2),
            step(1, "V", 4, following="C", predicted=1, effective=1, deliveries=["V"]),
            step(2, "C", 3, charge=6, following="J", predicted=-4, effective=-1),
            step(3, "J", 10, following="B", predicted=1, effective=1),
            step(4, "B", 9, following="V", predicted=2, effective=2),
            step(5, "V", 7, following="B", predicted=2, effective=2),
            step(6, "B", 5, following="B", predicted=0, effective=0),
            step(7, "B", 5),
        ],
    )
    idle = VehicleRoute(
        vehicle_id="vehicle_2",
        net_energy_kwh=0,
        steps=[
            *(step(r, "B", 6, following="B", predicted=0, effective=0) for r in range(7)),
            step(7, "B", 6),
        ],
    )
    solution = Solution(
        routes=[active, idle], served_visit_ids=["V"], unserved_visit_ids=["W"], net_energy_kwh=7
    )
    return instance, solution


def test_accepts_manual_saturation_revisits_intermediate_depot_and_idle_vehicle():
    instance, solution = manual_example()
    report = validate_solution(instance, solution)
    assert report.feasible
    assert report.violations == []
    assert all(report.checks.values())
    # The validator must not "fix" a route or mark the repeated client as served twice.
    assert solution.routes[0].steps[5].delivered_visit_ids == []
    assert solution.routes[0].steps[2].effective_arc_energy_kwh == -1


@pytest.mark.parametrize(
    ("position", "field", "value", "category"),
    [
        (0, "battery_arrival_kwh", 5, "battery"),
        (1, "battery_arrival_kwh", 0.5, "battery"),
        (2, "battery_departure_kwh", 11, "battery"),
        (3, "battery_arrival_kwh", 13, "battery"),  # Uncapped regeneration.
        (3, "battery_arrival_kwh", 9, "battery"),  # Ignored regeneration.
        (2, "charged_to_battery_kwh", -1, "charging"),
        (1, "charged_to_battery_kwh", 1, "charging"),  # Customer is not a charger.
        (0, "charged_to_battery_kwh", 1, "charging"),
        (4, "charged_to_battery_kwh", 1, "charging"),  # No depot recharge on revisit.
        (2, "battery_departure_kwh", 8, "charging"),
        (0, "next_node_id", "C", "topology"),
        (3, "node_id", "missing", "topology"),
        (1, "position", 5, "topology"),
        (2, "predicted_arc_energy_kwh", -3, "energy"),
        (2, "effective_arc_energy_kwh", -4, "energy"),  # Credits discarded regen.
        (0, "predicted_arc_energy_kwh", None, "energy"),
        (0, "effective_arc_energy_kwh", None, "energy"),
        (1, "delivered_visit_ids", ["W"], "deliveries"),
        (0, "delivered_visit_ids", ["B"], "deliveries"),
        (5, "delivered_visit_ids", ["V"], "deliveries"),  # Duplicate on revisit.
        (7, "delivered_visit_ids", ["V"], "deliveries"),
        (7, "next_node_id", "V", "topology"),
        (7, "charged_to_battery_kwh", 1, "topology"),
        (7, "predicted_arc_energy_kwh", 0, "energy"),
        (7, "effective_arc_energy_kwh", 0, "energy"),
        (7, "node_id", "V", "topology"),  # Fails return even if final battery is fine.
    ],
)
def test_rejects_tampered_steps(position, field, value, category):
    instance, original = manual_example()
    altered = original.model_copy(deep=True)
    setattr(altered.routes[0].steps[position], field, value)
    report = validate_solution(instance, altered)
    assert not report.feasible
    assert not report.checks[category]
    assert report.violations


@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        ("served_visit_ids", [], "deliveries"),
        ("served_visit_ids", ["V", "V"], "deliveries"),
        ("served_visit_ids", ["V", "W"], "deliveries"),
        ("unserved_visit_ids", [], "deliveries"),
        ("unserved_visit_ids", ["V", "W"], "deliveries"),
        ("unserved_visit_ids", ["W", "W"], "deliveries"),
        ("net_energy_kwh", 6.5, "energy"),
    ],
)
def test_does_not_trust_reported_delivery_or_energy_totals(field, value, category):
    instance, solution = manual_example()
    setattr(solution, field, value)
    report = validate_solution(instance, solution)
    assert not report.feasible
    assert not report.checks[category]


def test_rejects_route_energy_inconsistent_with_physical_steps():
    instance, solution = manual_example()
    solution.routes[0].net_energy_kwh = 4
    assert not validate_solution(instance, solution).checks["energy"]


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "unknown"])
def test_fleet_must_have_exactly_one_route_per_configured_vehicle(corruption):
    instance, solution = manual_example()
    if corruption == "missing":
        solution.routes.pop()
    elif corruption == "duplicate":
        solution.routes[1].vehicle_id = "vehicle_1"
    else:
        solution.routes[1].vehicle_id = "vehicle_9"
    report = validate_solution(instance, solution)
    assert not report.feasible
    assert not report.checks["fleet"]


@pytest.mark.parametrize("empty", [True, False])
def test_empty_or_truncated_routes_fail_h_position_contract(empty):
    instance, solution = manual_example()
    solution.routes[0].steps = [] if empty else solution.routes[0].steps[:-1]
    report = validate_solution(instance, solution)
    assert not report.feasible
    assert not report.checks["topology"]


def test_rejects_nonexistent_street_even_when_reported_next_node_is_consistent():
    instance, solution = manual_example()
    solution.routes[0].steps[2].next_node_id = "W"
    solution.routes[0].steps[3].node_id = "W"
    report = validate_solution(instance, solution)
    assert not report.checks["topology"]
    assert any("arco no permitido" in text for text in report.violations)


def test_explicit_vehicle_compatibility_is_checked_before_accepting_recharge():
    instance, solution = manual_example()
    instance.compatible_chargers = {"vehicle_1": [], "vehicle_2": ["C"]}
    report = validate_solution(instance, solution)
    assert not report.feasible
    assert not report.checks["charging"]


def test_global_net_zero_cannot_hide_intermediate_battery_deficit():
    instance = ProblemInstance(
        nodes=[Node(node_id="B", node_type="base"), Node(node_id="J", node_type="junction")],
        arcs=[
            Arc(from_node_id="B", to_node_id="J", energy_kwh=7),
            Arc(from_node_id="J", to_node_id="B", energy_kwh=-7),
        ],
        parameters=ModelParameters(
            battery_capacity_kwh=10, reserve_kwh=1, vehicle_count=1, movement_limit=2
        ),
    )
    solution = Solution(
        routes=[
            VehicleRoute(
                vehicle_id="vehicle_1",
                net_energy_kwh=0,
                steps=[
                    step(0, "B", 6, following="J", predicted=7, effective=7),
                    step(1, "J", -1, following="B", predicted=-7, effective=-7),
                    step(2, "B", 6),
                ],
            )
        ],
        served_visit_ids=[], unserved_visit_ids=[], net_energy_kwh=0,
    )
    report = validate_solution(instance, solution)
    assert not report.feasible
    assert not report.checks["battery"]


def test_multiple_violations_are_collected_instead_of_stopping_at_first_error():
    instance, solution = manual_example()
    solution.routes[0].steps[1].battery_arrival_kwh = 0
    solution.routes[0].steps[5].delivered_visit_ids = ["V"]
    solution.net_energy_kwh = -99
    report = validate_solution(instance, solution)
    assert not report.checks["battery"]
    assert not report.checks["deliveries"]
    assert not report.checks["energy"]
    assert len(report.violations) >= 3


def test_small_solver_roundoff_is_tolerated():
    instance, solution = manual_example()
    solution.routes[0].steps[1].battery_arrival_kwh += 1e-7
    solution.routes[0].steps[1].battery_departure_kwh += 1e-7
    solution.net_energy_kwh += 1e-7
    assert validate_solution(instance, solution).feasible


@pytest.mark.parametrize("tolerance", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_tolerance_must_be_finite_and_positive(tolerance):
    instance, solution = manual_example()
    with pytest.raises(ValueError, match="tolerance"):
        validate_solution(instance, solution, tolerance=tolerance)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_checker_rejects_nonfinite_tampering_even_if_contract_validation_was_bypassed(value):
    instance, solution = manual_example()
    solution.routes[0].steps[1].battery_arrival_kwh = value
    solution.net_energy_kwh = value
    assert not validate_solution(instance, solution).feasible
