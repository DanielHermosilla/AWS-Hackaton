"""End-to-end contracts of the merged road/SCIP/Bedrock web integration."""

import copy
import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import networkx as nx
import osmnx as ox
import pytest
from test_resource_graph import window_case
from test_web_bridge import native_request, prepare_request

from backend import daniel_adapter, service
from backend.local_server import make_server
from backend.runtime import PreparedContext, Runtime
from ev_routing.contracts import SolverConfig
from ev_routing.pipeline import run_instance
from ev_routing.resource_graph import prepare_service_graph


@pytest.fixture
def runtime(tmp_path):
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_edge(1, 2, length=100.0)
    graph.add_edge(2, 1, length=200.0)
    path = tmp_path / "roads.graphml"
    ox.save_graphml(graph, path)
    return Runtime(graphml=path, network_profile="drive", log_directory=tmp_path / "logs")


def road_request():
    return {**prepare_request(), "network_mode": "road"}


def test_actual_http_prepares_solves_expands_and_retrieves(runtime):
    server = make_server(port=0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    def post(endpoint, data):
        with urlopen(Request(
            root + endpoint, data=service.json_bytes(data),
            headers={"Content-Type": "application/json"},
        ), timeout=15) as response:
            return json.load(response)

    try:
        prepared = post("/prepare", road_request())
        payload = {
            "api_version": "3.0", "instance": prepared["instance"],
            "prepared_instance_id": prepared["prepared_instance_id"],
            "solver": {"time_limit_seconds": 3, "search_policy": "standard"},
        }
        envelope = post("/solve", payload)
        result = envelope["result"]
        assert result["validation"]["feasible"]
        assert result["raw"]["result"]["road_validation"]["feasible"]
        assert result["served_count"] == 1
        assert result["total_energy_kwh"] == pytest.approx(0.3)
        route = next(r for r in result["routes"] if r["served_visit_ids"])
        assert route["distance_km"] == pytest.approx(0.3)
        assert route["geometry"]["coordinates"] == [[0, 0], [0.001, 0], [0, 0]]
        assert any(s["node_id"].startswith("osm:") for s in route["steps"])
        assert result["network"]["vial"]
        assert result["raw"]["prepare_request"] == road_request()
        assert result["raw"]["effective_config"]["solver"]["energy_relative_gap"] == 0.005
        with urlopen(root + "/solve?run_id=" + result["run_id"], timeout=5) as response:
            assert json.load(response) == envelope
        assert post("/prepare", road_request())["prepared_instance_id"] == prepared["prepared_instance_id"]
        bad = copy.deepcopy(payload["instance"])
        bad["arcs"][0]["energy_kwh"] += 1
        with pytest.raises(service.SolveRequestError, match="corresponde"):
            runtime.get_context(prepared["prepared_instance_id"], bad)
        runtime.contexts.clear()
        with pytest.raises(service.SolveRequestError, match="expiró"):
            service.solve(payload, runtime=runtime)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_parallel_resource_paths_use_selected_arc_and_expand_streets(tmp_path):
    road = window_case()
    # Independent geometries for the slower and faster alternatives.
    positions = {"0": (0, 0), "j": (0.001, 0.001), "C": (0, 0.002)}
    for node in road.nodes:
        node.latitude, node.longitude = positions[node.node_id]
    for arc in road.arcs:
        arc.geometry = [positions[arc.from_node_id], positions[arc.to_node_id]]
        arc.distance_m = 200 if arc.from_node_id == "0" and arc.to_node_id == "C" else 100
    compact, archive = prepare_service_graph(road)
    assert compact.schema_version == "1.1"
    assert len([a for a in compact.arcs if a.from_node_id == "0" and a.to_node_id == "C"]) == 2
    config = SolverConfig(time_limit_seconds=3)
    native = run_instance(compact, config, road_instance=road, path_archive=archive)
    projected = daniel_adapter.project_result(compact, config, native, road_instance=road)
    assert projected["validation"]["feasible"]
    assert projected["routes"][0]["geometry"]["coordinates"] == [
        [0, 0], [0.002, 0], [0, 0],
    ]
    assert projected["routes"][0]["distance_km"] == pytest.approx(0.3)
    assert projected["total_energy_kwh"] == pytest.approx(3)
    # Compact geometry must choose the exact arc_id, not the last (origin,destination).
    raw_projection = daniel_adapter.project_result(compact, config, native)
    assert raw_projection["routes"][0]["distance_km"] == pytest.approx(0.3)
    context = PreparedContext(
        compact, road, archive, {}, 0, service.fingerprint(compact.model_dump(mode="json")), 1,
    )
    runtime = Runtime(log_directory=tmp_path)
    runtime.contexts["test-id"] = ("key", context)
    payload = {
        "api_version": "3.0", "instance": compact.model_dump(mode="json"),
        "prepared_instance_id": "test-id", "solver": {"time_limit_seconds": 3},
    }
    assert service.solve(payload, runtime=runtime)["result"]["validation"]["feasible"]
    del payload["prepared_instance_id"]
    with pytest.raises(service.SolveRequestError, match="preparación vial"):
        service.solve(payload, runtime=runtime)


def test_bedrock_failure_is_visible_and_does_not_lose_solution(runtime, monkeypatch):
    def denied(*args, **kwargs):
        raise RuntimeError("simulated access denied")

    monkeypatch.setattr("ev_routing.llm.bedrock.create_bedrock_client", denied)
    payload = native_request()
    payload["solver"]["search_policy"] = "adaptive"
    result = service.solve(payload, runtime=runtime)["result"]
    assert result["validation"]["feasible"]
    assert result["tuning"]["requested_policy"] == "adaptive"
    assert result["tuning"]["status"] == "fallback"
    assert result["tuning"]["applied_decisions"] == 0
    assert result["raw"]["effective_config"]["search_policy"] == "adaptive"
    assert result["tuning"]["model_id"] == "us.openai.gpt-5.6-luna"


def test_bounded_server_gpt_configuration(runtime, monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "test-profile")
    config = runtime.search_config("adaptive", "test-run")
    assert config.bedrock.model_id == "us.openai.gpt-5.6-luna"
    assert config.bedrock.reasoning_effort == "low"
    assert config.bedrock.profile == "test-profile"
    assert config.max_llm_calls == 2
    assert config.bedrock.timeout_seconds == 8
    assert config.instance_context_bytes == 8000
    assert config.log_directory.endswith("test-run/logs")
    payload = native_request()
    for forbidden in ("model_id", "aws_profile", "relative_gap", "log_directory"):
        payload["solver"][forbidden] = "browser-cannot-set-this"
        with pytest.raises(service.SolveRequestError, match="campos no admitidos"):
            service.validate_request(payload)
        del payload["solver"][forbidden]


def test_csv_road_operations_reach_resource_preprocessor(runtime):
    payload = road_request()
    payload["operations"] = {
        "max_route_seconds": 3600, "assumed_speed_kph": 30,
        "include_charging_time": True, "charging_power_kw": 6.6,
    }
    prepared = service.prepare(payload, runtime=runtime)
    assert prepared["instance"]["schema_version"] == "1.1"
    assert prepared["instance"]["provenance"]["representation"]["kind"] == "resource_paths"
    assert prepared["instance"]["operations"]["max_route_seconds"] == 3600
    result = service.solve({
        "api_version": "3.0", "instance": prepared["instance"],
        "prepared_instance_id": prepared["prepared_instance_id"],
        "solver": {"time_limit_seconds": 3},
    }, runtime=runtime)["result"]
    assert result["validation"]["feasible"]
    assert result["raw"]["result"]["road_validation"]["feasible"]
    assert result["served_count"] == 1


def test_browser_number_serialization_preserves_context_but_not_changed_data(runtime):
    prepared = service.prepare(road_request(), runtime=runtime)

    def javascript_numbers(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, list):
            return [javascript_numbers(v) for v in item]
        if isinstance(item, dict):
            return {k: javascript_numbers(v) for k, v in item.items()}
        return item

    browser_instance = javascript_numbers(prepared["instance"])
    context = runtime.get_context(prepared["prepared_instance_id"], browser_instance)
    assert context.instance.parameters.battery_capacity_kwh == 10
    for invalid in (True, "10", 10.000000000000002):
        changed = copy.deepcopy(browser_instance)
        changed["parameters"]["battery_capacity_kwh"] = invalid
        with pytest.raises(service.SolveRequestError, match="corresponde"):
            runtime.get_context(prepared["prepared_instance_id"], changed)


def test_gap_tolerance_is_neither_timeout_nor_exact_optimum():
    fixture = json.loads((Path(__file__).parents[1] / "backend/fixtures/native-response.json").read_text())
    native = copy.deepcopy(fixture["result"]["raw"]["result"])
    instance, config = service.validate_request(fixture["result"]["raw"]["input"])
    native["solve"]["lexicographic_optimal"] = False
    energy = next(p for p in native["solve"]["phases"] if p["name"] == "energy")
    energy.update(termination_condition="energy_gap_limit", proven_optimal=False, relative_gap=0.004)
    projected = daniel_adapter.project_result(instance, config, native)
    assert projected["metadata"]["time_limit_reached"] is None
    assert projected["metadata"]["lexicographic_optimal"] is False
    assert projected["validation"]["feasible"]
    assert projected["phases"][-1]["termination_condition"] == "energy_gap_limit"
