"""Operator controls reach the native motor without altering physical rules."""

import json
import threading
from urllib.request import Request, urlopen

import pytest

from backend import local_server, service
from backend.runtime import Runtime
from ev_routing.network import ServiceAccessError
from test_web_bridge import native_request, prepare_request


def test_solver_controls_and_machine_resources_reach_effective_configuration(monkeypatch):
    monkeypatch.setattr(service, "available_solver_threads", lambda: 4)
    payload = native_request()
    payload["solver"].update(energy_relative_gap=0.012, random_seed=17)
    result = service.solve(payload)["result"]
    config = result["raw"]["effective_config"]["solver"]
    assert (config["threads"], config["seed"], config["energy_relative_gap"]) == (4, 17, .012)
    assert config["relative_gap"] == 0
    assert result["validation"]["feasible"]


@pytest.mark.parametrize("field,value", [
    ("random_seed", -1), ("random_seed", 1.5), ("random_seed", 2_000_000_001),
    ("random_seed", True), ("energy_relative_gap", -.1),
    ("energy_relative_gap", 1.1), ("energy_relative_gap", True),
])
def test_solver_controls_reject_invalid_values(field, value):
    payload = native_request()
    payload["solver"][field] = value
    with pytest.raises(service.SolveRequestError):
        service.validate_request(payload)


def test_two_client_case_from_screenshot_returns_valid_visible_synthetic_route():
    payload = prepare_request()
    payload["nodes"] = [
        {"node_id": "B", "node_type": "base", "latitude": -33.45, "longitude": -70.66},
        {"node_id": "C1", "node_type": "visit", "latitude": -33.451, "longitude": -70.661},
        {"node_id": "C2", "node_type": "visit", "latitude": -33.452, "longitude": -70.659},
    ]
    payload["fleet"].update(num_vehicles=1, battery_capacity_kwh=7, reserve_kwh=2)
    prepared = service.prepare(payload)
    result = service.solve({
        "api_version": "3.0", "instance": prepared["instance"],
        "solver": {"time_limit_seconds": 3},
    })["result"]
    assert result["served_count"] == 2
    assert result["validation"]["feasible"]
    assert result["network"]["vial"] is False
    assert result["network"]["geometry_source"] == "synthetic_haversine"
    route = result["routes"][0]
    assert route["geometry"]["coordinates"][0] == [-70.66, -33.45]
    assert route["geometry"]["coordinates"][-1] == [-70.66, -33.45]
    assert len(route["geometry"]["coordinates"]) >= 4


def test_road_coverage_failure_explains_action_without_loosening_snap(tmp_path, monkeypatch):
    graph = tmp_path / "roads.graphml"
    graph.write_text("unused test graph")
    runtime = Runtime(graphml=graph)

    def outside(*args, **kwargs):
        assert kwargs["max_snap_distance_m"] == 100
        raise ServiceAccessError("BASE#fin", 8516388.6, 100)

    monkeypatch.setattr("ev_routing.network.build_osm_instance", outside)
    with pytest.raises(service.SolveRequestError, match="BASE#fin.*8516389 m.*calle.*100 m.*coordenadas"):
        service.prepare({**prepare_request(), "network_mode": "road"}, runtime=runtime)


def test_large_native_request_is_accepted_solved_and_retrieved_over_http():
    payload = native_request()
    # The complete export repeats this value and exceeds the former 32 MiB cache.
    # This exercises transport, strict parsing and retrieval, not graph performance.
    payload["instance"]["provenance"]["source_note"] = "x" * (12 * 1024 * 1024)
    server = local_server.make_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(Request(
            f"http://127.0.0.1:{server.server_port}/solve",
            data=service.json_bytes(payload),
            headers={"Content-Type": "application/json"},
        ), timeout=20) as response:
            envelope = json.load(response)
            result = envelope["result"]
        assert result["validation"]["feasible"]
        assert result["raw"]["input"]["instance"]["provenance"] == payload["instance"]["provenance"]
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/solve?run_id={result['run_id']}", timeout=20
        ) as response:
            assert json.load(response) == envelope
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
