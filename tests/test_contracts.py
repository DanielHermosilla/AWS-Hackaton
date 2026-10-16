import pytest
from pydantic import ValidationError

from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    ProblemInstance,
    RouteStep,
    SolverConfig,
    finite_or_none,
)


def graph_payload():
    return {
        "nodes": [
            {"node_id": "B", "node_type": "base"},
            {"node_id": "V", "node_type": "visit"},
            {"node_id": "AC", "node_type": "charger", "connector_types": ["J1772"]},
            {"node_id": "DC", "node_type": "charger", "connector_types": ["CCS"]},
            {"node_id": "unknown", "node_type": "charger"},
        ],
        "arcs": [{"from_node_id": "B", "to_node_id": "V", "energy_kwh": 0.2}],
    }


def test_official_initial_soc_and_vehicle_defaults_do_not_prevent_explicit_scenarios():
    default = ModelParameters()
    assert default.vehicle_count == 2
    assert default.initial_soc == 0.6
    explicit = ModelParameters(
        vehicle_count=3, battery_capacity_kwh=8, reserve_kwh=1,
        initial_soc=0.75, movement_limit=11
    )
    assert explicit.initial_energy_kwh == 6
    assert explicit.movement_limit == 11
    assert "time_horizon_seconds" not in explicit.model_dump()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vehicle_count", 0), ("vehicle_count", 1.5),
        ("battery_capacity_kwh", 0), ("battery_capacity_kwh", -10),
        ("reserve_kwh", 0), ("reserve_kwh", 15),
        ("initial_soc", 0), ("initial_soc", 1.001),
        ("movement_limit", 0), ("movement_limit", 1.5),
    ],
)
def test_problem_parameters_reject_invalid_bounds_and_fractional_counts(field, value):
    with pytest.raises(ValidationError):
        ModelParameters(**{field: value})


def test_reserve_equal_to_initial_energy_is_valid_but_higher_is_not():
    valid = ModelParameters(battery_capacity_kwh=10, initial_soc=0.6, reserve_kwh=6)
    assert valid.reserve_kwh == valid.initial_energy_kwh
    with pytest.raises(ValidationError, match="energía inicial"):
        ModelParameters(battery_capacity_kwh=10, initial_soc=0.6, reserve_kwh=6.0001)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["battery_capacity_kwh", "reserve_kwh", "initial_soc"])
def test_nonfinite_physical_parameters_rejected(field, value):
    with pytest.raises(ValidationError):
        ModelParameters(**{field: value})


@pytest.mark.parametrize(
    "values",
    [
        {"latitude": 42}, {"longitude": -83},
        {"latitude": 91, "longitude": -83},
        {"latitude": 42, "longitude": -181},
        {"latitude": float("nan"), "longitude": -83},
        {"latitude": 42, "longitude": float("inf")},
    ],
)
def test_node_coordinates_are_paired_finite_and_geographic(values):
    with pytest.raises(ValidationError):
        Node(node_id="N", node_type="visit", **values)


def test_coordinate_boundary_and_synthetic_nodes_without_locations_are_valid():
    assert Node(node_id="north", node_type="junction", latitude=90, longitude=180).latitude == 90
    assert Node(node_id="south", node_type="junction", latitude=-90, longitude=-180).longitude == -180
    assert Node(node_id="synthetic", node_type="visit").latitude is None


@pytest.mark.parametrize(
    "values",
    [
        {"node_id": ""},
        {"node_type": "delivery"},
        {"total_ports": -1},
        {"dc_fast_ports": 1.5},
        {"max_power_kw": 0},
        {"max_power_kw": float("nan")},
    ],
)
def test_node_identifiers_types_and_charger_units_reject_invalid_values(values):
    payload = {"node_id": "N", "node_type": "charger", **values}
    with pytest.raises(ValidationError):
        Node(**payload)


def test_signed_energy_is_preserved_but_negative_distance_is_invalid():
    arc = Arc(from_node_id="A", to_node_id="B", energy_kwh=-0.25, distance_m=300)
    assert arc.energy_kwh == -0.25
    with pytest.raises(ValidationError):
        Arc(from_node_id="A", to_node_id="B", energy_kwh=-0.25, distance_m=-300)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_arc_and_route_energy_cannot_serialize_nonfinite_numbers(value):
    with pytest.raises(ValidationError):
        Arc(from_node_id="A", to_node_id="B", energy_kwh=value)
    with pytest.raises(ValidationError):
        RouteStep(position=0, node_id="B", battery_arrival_kwh=value, battery_departure_kwh=6)


def test_unknown_fields_and_wrong_units_are_not_silently_ignored():
    with pytest.raises(ValidationError, match="distance_km"):
        Arc(from_node_id="A", to_node_id="B", energy_kwh=1, distance_km=1)
    with pytest.raises(ValidationError, match="time_horizon_seconds"):
        ModelParameters(time_horizon_seconds=3600)
    with pytest.raises(ValidationError, match="objective_weights"):
        ModelParameters(objective_weights=[1, 1])


@pytest.mark.parametrize("kind", ["duplicate_id", "no_base", "two_bases", "unknown_arc", "parallel", "self_loop"])
def test_instance_graph_contract_rejects_ambiguous_or_invalid_structure(kind):
    payload = graph_payload()
    if kind == "duplicate_id":
        payload["nodes"].append({"node_id": "V", "node_type": "visit"})
    elif kind == "no_base":
        payload["nodes"][0]["node_type"] = "junction"
    elif kind == "two_bases":
        payload["nodes"][1]["node_type"] = "base"
    elif kind == "unknown_arc":
        payload["arcs"][0]["to_node_id"] = "missing"
    elif kind == "parallel":
        payload["arcs"].append({"from_node_id": "B", "to_node_id": "V", "energy_kwh": 0.3})
    else:
        payload["arcs"][0]["to_node_id"] = "B"
    with pytest.raises(ValidationError):
        ProblemInstance.model_validate(payload)


def test_charger_inference_requires_known_shared_connector():
    instance = ProblemInstance.model_validate(graph_payload())
    assert instance.chargers_for("vehicle_1") == ["AC"]
    assert instance.chargers_for("vehicle_2") == ["AC"]
    with pytest.raises(ValueError, match="desconocido"):
        instance.chargers_for("vehicle_3")


def test_explicit_compatibility_overrides_connector_inference_per_vehicle():
    instance = ProblemInstance.model_validate(
        {**graph_payload(), "compatible_chargers": {"vehicle_1": ["DC"], "vehicle_2": []}}
    )
    assert instance.chargers_for("vehicle_1") == ["DC"]
    assert instance.chargers_for("vehicle_2") == []


@pytest.mark.parametrize(
    "mapping",
    [
        {"vehicle_1": ["AC"]},
        {"vehicle_1": ["AC"], "vehicle_2": [], "vehicle_3": []},
        {"vehicle_1": ["missing"], "vehicle_2": []},
        {"vehicle_1": ["V"], "vehicle_2": []},
        {"vehicle_1": ["B"], "vehicle_2": []},
    ],
)
def test_compatibility_must_cover_exact_fleet_and_reference_only_chargers(mapping):
    with pytest.raises(ValidationError):
        ProblemInstance.model_validate({**graph_payload(), "compatible_chargers": mapping})


def test_json_schema_version_and_unknown_fields_are_validated():
    with pytest.raises(ValidationError):
        ProblemInstance.model_validate({**graph_payload(), "schema_version": "2.0"})
    instance = ProblemInstance.model_validate(graph_payload())
    assert ProblemInstance.model_validate_json(instance.model_dump_json()) == instance


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("solver", "invented_backend"), ("time_limit_seconds", 0),
        ("time_limit_seconds", float("inf")), ("relative_gap", -0.1),
        ("relative_gap", 1.1), ("threads", 0), ("seed", -1), ("seed", 2_000_000_001),
    ],
)
def test_solver_resource_bounds_do_not_accept_invalid_or_unknown_settings(field, value):
    with pytest.raises(ValidationError):
        SolverConfig(**{field: value})


@pytest.mark.parametrize("value", [None, "", "not-a-number", float("nan"), float("inf"), -float("inf")])
def test_unavailable_solver_bounds_become_json_null(value):
    assert finite_or_none(value) is None


@pytest.mark.parametrize("value", [0, -2, 1.5, "3.25"])
def test_finite_solver_bounds_preserve_sign_and_value(value):
    assert finite_or_none(value) == float(value)
