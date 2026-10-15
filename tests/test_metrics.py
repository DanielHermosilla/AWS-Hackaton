import pytest

from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    ProblemInstance,
    RouteStep,
    Solution,
    ValidationReport,
    VehicleRoute,
)
from ev_routing.metrics import compute_metrics
from ev_routing.validation import validate_solution


def metric_example():
    instance = ProblemInstance(
        nodes=[
            Node(node_id="B", node_type="base"),
            Node(node_id="V", node_type="visit"),
            Node(node_id="W", node_type="visit"),
            Node(node_id="C", node_type="charger", connector_types=["J1772"]),
        ],
        arcs=[
            Arc(from_node_id="B", to_node_id="V", energy_kwh=0.4, distance_m=1000),
            Arc(from_node_id="V", to_node_id="C", energy_kwh=0.6, distance_m=1000),
            Arc(from_node_id="C", to_node_id="B", energy_kwh=1, distance_m=3000),
        ],
        parameters=ModelParameters(
            vehicle_count=1, battery_capacity_kwh=10, reserve_kwh=1, movement_limit=3
        ),
    )
    solution = Solution(
        routes=[
            VehicleRoute(
                vehicle_id="vehicle_1", net_energy_kwh=2,
                steps=[
                    RouteStep(position=0, node_id="B", battery_arrival_kwh=6, battery_departure_kwh=6,
                              next_node_id="V", predicted_arc_energy_kwh=0.4, effective_arc_energy_kwh=0.4),
                    RouteStep(position=1, node_id="V", battery_arrival_kwh=5.6, battery_departure_kwh=5.6,
                              delivered_visit_ids=["V"], next_node_id="C", predicted_arc_energy_kwh=0.6, effective_arc_energy_kwh=0.6),
                    RouteStep(position=2, node_id="C", battery_arrival_kwh=5, charged_to_battery_kwh=2,
                              battery_departure_kwh=7, next_node_id="B", predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
                    RouteStep(position=3, node_id="B", battery_arrival_kwh=6, battery_departure_kwh=6),
                ],
            )
        ],
        served_visit_ids=["V"], unserved_visit_ids=["W"], net_energy_kwh=2,
    )
    return instance, solution


def test_reports_manually_verified_distance_battery_charge_and_deliveries():
    instance, solution = metric_example()
    report = validate_solution(instance, solution)
    assert report.feasible
    metrics = compute_metrics(instance, solution, report)
    assert metrics["feasible"] is True
    assert metrics["served_deliveries"] == 1
    assert metrics["total_deliveries"] == 2
    assert metrics["net_battery_energy_kwh"] == pytest.approx(2)
    assert metrics["charged_to_battery_kwh"] == pytest.approx(2)
    assert metrics["distance_km"] == pytest.approx(5)
    assert metrics["charging_stops"] == 1
    assert metrics["minimum_battery_kwh"] == pytest.approx(5)


@pytest.mark.parametrize(
    "metric",
    ["grid_energy_kwh", "operational_duration_seconds", "time_saved_seconds", "co2e_saved_kg"],
)
def test_does_not_invent_grid_energy_runtime_or_environmental_savings(metric):
    instance, solution = metric_example()
    metrics = compute_metrics(instance, solution, validate_solution(instance, solution))
    assert metrics[metric] is None
    assert metrics["unavailable_reasons"][metric]


@pytest.mark.parametrize("case", ["no_solution", "no_validation", "invalid", "both_missing"])
def test_unvalidated_or_invalid_incumbents_do_not_produce_success_kpis(case):
    instance, solution = metric_example()
    report = ValidationReport(feasible=True)
    if case == "no_solution":
        solution = None
    elif case == "no_validation":
        report = None
    elif case == "invalid":
        solution.routes[0].steps[1].battery_arrival_kwh = -1
        report = validate_solution(instance, solution)
        assert not report.feasible
    else:
        solution, report = None, None
    metrics = compute_metrics(instance, solution, report)
    assert metrics["feasible"] is False
    assert metrics["total_deliveries"] == 2
    for key in (
        "served_deliveries", "net_battery_energy_kwh", "charged_to_battery_kwh",
        "distance_km", "charging_stops", "minimum_battery_kwh",
    ):
        assert metrics[key] is None


def test_idle_depot_route_has_zero_travel_but_no_claimed_savings():
    instance = ProblemInstance(
        nodes=[Node(node_id="B", node_type="base"), Node(node_id="V", node_type="visit")],
        arcs=[],
        parameters=ModelParameters(
            vehicle_count=1, battery_capacity_kwh=10, reserve_kwh=1, movement_limit=1
        ),
    )
    route = VehicleRoute(
        vehicle_id="vehicle_1", net_energy_kwh=0,
        steps=[
            RouteStep(position=0, node_id="B", battery_arrival_kwh=6, battery_departure_kwh=6,
                      next_node_id="B", predicted_arc_energy_kwh=0, effective_arc_energy_kwh=0),
            RouteStep(position=1, node_id="B", battery_arrival_kwh=6, battery_departure_kwh=6),
        ],
    )
    solution = Solution(
        routes=[route], served_visit_ids=[], unserved_visit_ids=["V"], net_energy_kwh=0
    )
    report = validate_solution(instance, solution)
    assert report.feasible
    metrics = compute_metrics(instance, solution, report)
    assert metrics["served_deliveries"] == 0
    assert metrics["distance_km"] == 0
    assert metrics["net_battery_energy_kwh"] == 0
    assert metrics["charging_stops"] == 0
    assert metrics["minimum_battery_kwh"] == 6
    assert metrics["co2e_saved_kg"] is None


def test_negative_net_energy_is_preserved_without_turning_it_into_avoided_emissions():
    instance = ProblemInstance(
        nodes=[Node(node_id="B", node_type="base"), Node(node_id="V", node_type="visit")],
        arcs=[
            Arc(from_node_id="B", to_node_id="V", energy_kwh=-2, distance_m=600),
            Arc(from_node_id="V", to_node_id="B", energy_kwh=1, distance_m=400),
        ],
        parameters=ModelParameters(
            vehicle_count=1, battery_capacity_kwh=10, reserve_kwh=1, movement_limit=2
        ),
        provenance={"assumptions": ["Synthetic signed-arc accounting test, not a physical road claim"]},
    )
    route = VehicleRoute(
        vehicle_id="vehicle_1", net_energy_kwh=-1,
        steps=[
            RouteStep(position=0, node_id="B", battery_arrival_kwh=6, battery_departure_kwh=6,
                      next_node_id="V", predicted_arc_energy_kwh=-2, effective_arc_energy_kwh=-2),
            RouteStep(position=1, node_id="V", battery_arrival_kwh=8, battery_departure_kwh=8,
                      delivered_visit_ids=["V"], next_node_id="B", predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
            RouteStep(position=2, node_id="B", battery_arrival_kwh=7, battery_departure_kwh=7),
        ],
    )
    solution = Solution(routes=[route], served_visit_ids=["V"], unserved_visit_ids=[], net_energy_kwh=-1)
    report = validate_solution(instance, solution)
    assert report.feasible
    metrics = compute_metrics(instance, solution, report)
    assert metrics["net_battery_energy_kwh"] == -1
    assert metrics["charged_to_battery_kwh"] == 0
    assert metrics["distance_km"] == 1
    assert metrics["co2e_saved_kg"] is None


def test_repeated_streets_are_counted_every_time_not_deduplicated():
    instance = ProblemInstance(
        nodes=[Node(node_id="B", node_type="base"), Node(node_id="V", node_type="visit")],
        arcs=[
            Arc(from_node_id="B", to_node_id="V", energy_kwh=1, distance_m=1000),
            Arc(from_node_id="V", to_node_id="B", energy_kwh=1, distance_m=1500),
        ],
        parameters=ModelParameters(
            vehicle_count=1, battery_capacity_kwh=10, reserve_kwh=1, movement_limit=4
        ),
    )
    route = VehicleRoute(
        vehicle_id="vehicle_1", net_energy_kwh=4,
        steps=[
            RouteStep(position=0, node_id="B", battery_arrival_kwh=6, battery_departure_kwh=6,
                      next_node_id="V", predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
            RouteStep(position=1, node_id="V", battery_arrival_kwh=5, battery_departure_kwh=5,
                      next_node_id="B", predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1, delivered_visit_ids=["V"]),
            RouteStep(position=2, node_id="B", battery_arrival_kwh=4, battery_departure_kwh=4,
                      next_node_id="V", predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
            RouteStep(position=3, node_id="V", battery_arrival_kwh=3, battery_departure_kwh=3,
                      next_node_id="B", predicted_arc_energy_kwh=1, effective_arc_energy_kwh=1),
            RouteStep(position=4, node_id="B", battery_arrival_kwh=2, battery_departure_kwh=2),
        ],
    )
    solution = Solution(routes=[route], served_visit_ids=["V"], unserved_visit_ids=[], net_energy_kwh=4)
    report = validate_solution(instance, solution)
    assert report.feasible
    metrics = compute_metrics(instance, solution, report)
    assert metrics["distance_km"] == 5  # Two full tours, not 2.5 km.
    assert metrics["served_deliveries"] == 1
    assert metrics["minimum_battery_kwh"] == 2
