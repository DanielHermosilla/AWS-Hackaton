"""History HTTP contract: separate uploads, explicit fallback and cache invalidation."""

import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import networkx as nx
import osmnx as ox
import pytest
from test_web_bridge import prepare_request

from backend import service
from backend.history_store import HistoryStore
from backend.local_server import make_server
from backend.runtime import Runtime


def eved_bytes():
    header = (
        "VehId,Trip,Timestamp,Vehicle Speed[km/h],HV Battery Current[A],"
        "HV Battery Voltage[V],HV Battery SOC[%],Matched Latitude[deg],"
        "Matched Longitude[deg],Match Type\n"
    )
    rows = []
    for trip in range(4):
        for second in range(3):
            rows.append(
                f"EV,{trip},2026-10-16T00:0{trip}:0{second}Z,36,-10,360,60,0,"
                f"{second * .0001},0\n"
            )
    return (header + "".join(rows)).encode()


class OfflineBedrock:
    def status(self):
        return {
            "state": "missing_credentials", "connected": False,
            "message": "Conecta con AWS.", "reasoning_effort": "high",
        }

    def disconnect(self):
        return self.status()

    def analyze(self, profile):
        raise RuntimeError("private SDK exception must not leak")


@pytest.fixture
def history_server(tmp_path):
    runtime = Runtime(log_directory=tmp_path / "logs")
    runtime.bedrock = OfflineBedrock()
    runtime.histories = HistoryStore(runtime.bedrock)
    server = make_server(port=0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def fetch(path, data=None, *, headers=None):
        options = dict(headers or {})
        if isinstance(data, dict):
            data = service.json_bytes(data)
            options.setdefault("Content-Type", "application/json")
        try:
            response = urlopen(Request(
                f"http://127.0.0.1:{server.server_port}" + path,
                data=data, headers=options,
            ), timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    yield server, fetch
    server.shutdown()
    server.server_close()
    thread.join(5)


def upload(fetch, content=None):
    return fetch("/history/upload", eved_bytes() if content is None else content, headers={
        "Content-Type": "application/octet-stream", "X-History-Filename": "historia.csv",
    })


def test_health_reports_history_upload_limits_by_format(history_server, monkeypatch):
    # Capability limits do not depend on loading the native solver libraries.
    monkeypatch.setattr("backend.daniel_adapter.provider_available", lambda: False)
    _, fetch = history_server
    code, envelope = fetch("/health")
    assert code == 200, envelope
    assert envelope["api_version"] == "3.0"
    capabilities = envelope["capabilities"]
    assert capabilities["historical_upload_max_bytes"] == 4 * 1024 ** 3
    assert capabilities["historical_upload_max_bytes_by_format"] == {
        "csv": 4 * 1024 ** 3,
        "json": 256 * 1024 ** 2,
    }


@pytest.mark.parametrize("filename, length, error_code", [
    ("big.csv", 4 * 1024 ** 3 + 1, "payload_too_large"),
    ("big.json", 256 * 1024 ** 2 + 1, "history_too_large"),
])
def test_history_upload_rejects_format_limit_before_reading_body(
    history_server, filename, length, error_code,
):
    server, fetch = history_server
    code, envelope = fetch("/history/upload", b"", headers={
        "Content-Type": "application/octet-stream",
        "Content-Length": str(length),
        "X-History-Filename": filename,
    })
    assert code == 413, envelope
    assert envelope["error"]["code"] == error_code
    assert not server.runtime.histories.entries


def test_history_is_separate_and_synthetic_keeps_explicit_fallback(history_server):
    server, fetch = history_server
    code, envelope = upload(fetch)
    assert code == 200, envelope
    profile = envelope["profile"]
    assert profile["status"] == "ready"
    assert profile["summary"]["row_count"] == 12
    identifier = profile["profile_id"]
    code, retrieved = fetch("/history?profile_id=" + identifier)
    assert code == 200 and retrieved["profile"] == profile
    request = {**prepare_request(), "energy_profile_id": identifier}
    code, prepared = fetch("/prepare", request)
    assert code == 200, prepared
    source = prepared["instance"]["provenance"]["energy_model"]
    assert source["kind"] == "manual_fallback"
    assert prepared["preparation"]["energy_profile"]["summary"]["arc_coverage_fraction"] == 0
    baseline = service.prepare(prepare_request())["instance"]["arcs"]
    assert prepared["instance"]["arcs"] == baseline
    path = server.runtime.histories.get(identifier).path
    assert path.exists()
    code, removed = fetch("/history/remove", {"profile_id": identifier})
    assert code == 200 and removed["removed"]
    assert not path.exists()
    assert fetch("/history?profile_id=" + identifier)[0] == 404
    assert fetch("/prepare", request)[0] == 404


def test_unknown_history_can_fall_back_and_ai_failures_are_sanitized(history_server):
    _, fetch = history_server
    code, envelope = upload(fetch, b"vehicle,date,value\nx,2026-10-16,42\n")
    assert code == 200, envelope
    profile = envelope["profile"]
    assert profile["status"] == "needs_mapping"
    code, analyzed = fetch("/history/analyze", {"profile_id": profile["profile_id"]})
    assert code == 200 and analyzed["profile"]["status"] == "needs_mapping"
    assert "private SDK" not in json.dumps(analyzed)
    assert analyzed["profile"]["ai_analysis"]["status"] == "error"


def test_credentials_and_upload_endpoints_keep_origin_limits_and_disconnect(history_server):
    server, fetch = history_server
    assert fetch("/bedrock/session")[0] == 200
    assert fetch("/bedrock/session", {"secret_access_key": "example"}, headers={
        "Origin": "https://another.example",
    })[0] == 403
    assert fetch("/bedrock/session", {"secret_access_key": "s" * 20_000})[0] == 413
    assert fetch("/history/upload", b"not CSV", headers={
        "Content-Type": "application/octet-stream", "X-History-Filename": "../../file.exe",
    })[0] == 400
    server.solve_lock.acquire()
    try:
        assert fetch("/bedrock/disconnect", {})[0] == 200
        assert upload(fetch)[0] == 409
    finally:
        server.solve_lock.release()


def test_history_store_reuses_identical_upload_and_evicts_temporary_file():
    store = HistoryStore(OfflineBedrock(), max_profiles=1)
    try:
        original = eved_bytes()
        first = store.upload(io.BytesIO(original), len(original), "original.csv")
        old_path = store.get(first["profile_id"]).path
        same = store.upload(io.BytesIO(original), len(original), "copy.csv")
        assert same["profile_id"] == first["profile_id"]
        changed = original.replace(b"-10,", b"-12,")
        new = store.upload(io.BytesIO(changed), len(changed), "other.csv")
        assert new["profile_id"] != first["profile_id"]
        assert not old_path.exists()
    finally:
        store.close()


def test_invalid_eved_is_not_reinterpreted_by_ai(history_server):
    _, fetch = history_server
    broken = eved_bytes().replace(b",360,", b",-360,")
    code, envelope = upload(fetch, broken)
    assert code == 200, envelope
    profile = envelope["profile"]
    assert profile["status"] == "error"
    code, analyzed = fetch("/history/analyze", {"profile_id": profile["profile_id"]})
    assert code == 200 and analyzed["profile"]["status"] == "error"

def test_actual_file_inspection_is_accepted_by_bedrock_interpretation(tmp_path):
    from ev_routing.historical_energy import inspect_history, normalize_history
    from ev_routing.llm.history import analyze_history_profile
    from ev_routing.search_policy import BedrockConfig

    path = tmp_path / "eved.csv"
    path.write_bytes(eved_bytes())
    inspected = inspect_history(path)
    inspected["computed_summary"] = normalize_history(path).summary
    replies = []

    def provider(request):
        replies.append(request)
        return {"policy": {
            "schema_version": "1.0", "mapping": None, "observations": [],
            "assumptions": [], "limitations": ["Estimación histórica."],
            "unresolved_fields": [],
        }, "usage": {"totalTokens": 20}, "stop_reason": "end_turn"}

    result = analyze_history_profile(
        inspected, provider=provider,
        config=BedrockConfig(model_id="us.openai.gpt-5.6-luna", reasoning_effort="high"),
    )
    assert replies and result["ai"]["usage"]["totalTokens"] == 20


def test_history_store_keeps_validated_ai_report_and_tokens():
    class ConnectedBedrock(OfflineBedrock):
        def status(self):
            return {**super().status(), "connected": True, "model_id": "configured-model"}

        def analyze(self, profile):
            return {"interpretation": {
                "mapping": None, "observations": [], "assumptions": [],
                "limitations": [], "unresolved_fields": [],
            }, "ai": {"usage": {"totalTokens": 40}}}

    store = HistoryStore(ConnectedBedrock())
    try:
        content = eved_bytes()
        reply = store.upload(io.BytesIO(content), len(content), "ev.csv")
        assert reply["status"] == "ready"
        assert reply["ai_analysis"]["status"] == "reviewed"
        assert reply["ai_analysis"]["usage"]["totalTokens"] == 40
    finally:
        store.close()


def test_history_energy_is_applied_before_path_preparation_and_invalidates_cache(tmp_path):
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_edge(1, 2, length=100.0)
    graph.add_edge(2, 1, length=100.0)
    path = tmp_path / "map.graphml"
    ox.save_graphml(graph, path)
    runtime = Runtime(graphml=path, network_profile="drive")
    revision = [1]

    class ControlledHistory:
        def get(self, identifier):
            assert identifier == "profile"

        def cache_key(self, identifier):
            return {"revision": revision[0]}

        def apply(self, identifier, road, rate):
            for arc in road.arcs:
                if arc.source_id.startswith("osm:"):
                    arc.energy_kwh = .2 * revision[0]
            return road, {"summary": {"calibrated_arc_count": 2}}

        def close(self):
            pass

    runtime.histories = ControlledHistory()
    request = {
        **prepare_request(), "network_mode": "road", "energy_profile_id": "profile",
    }
    try:
        first = service.prepare(request, runtime=runtime)
        assert max(arc["energy_kwh"] for arc in first["instance"]["arcs"]) == pytest.approx(.2)
        assert service.prepare(request, runtime=runtime)["prepared_instance_id"] == first["prepared_instance_id"]
        revision[0] = 2
        second = service.prepare(request, runtime=runtime)
        assert second["prepared_instance_id"] != first["prepared_instance_id"]
        assert max(arc["energy_kwh"] for arc in second["instance"]["arcs"]) == pytest.approx(.4)
        assert first["instance"] != second["instance"]
    finally:
        runtime.close()


def test_editing_fleet_reuses_calibration_but_changed_streets_do_not(monkeypatch):
    from test_historical_energy import eved, road

    from ev_routing import historical_energy

    store = HistoryStore(OfflineBedrock())
    content = eved().to_csv(index=False).encode()
    profile = store.upload(io.BytesIO(content), len(content), "ev.csv")
    calls = []
    fit = historical_energy.fit_historical_energy

    def recorded(*args, **kwargs):
        calls.append(True)
        return fit(*args, **kwargs)

    monkeypatch.setattr(historical_energy, "fit_historical_energy", recorded)
    try:
        streets = road()
        store.apply(profile["profile_id"], streets, .2)
        different_capacity = streets.model_copy(deep=True)
        different_capacity.parameters.battery_capacity_kwh = 30
        store.apply(profile["profile_id"], different_capacity, .2)
        assert len(calls) == 1
        different_street = streets.model_copy(deep=True)
        different_street.arcs[0].energy_kwh *= 2
        store.apply(profile["profile_id"], different_street, .2)
        assert len(calls) == 2
    finally:
        store.close()


def test_hackathon_endpoint_reads_local_csv_without_exposing_arbitrary_paths(
    history_server, tmp_path, monkeypatch,
):
    from backend import scenarios
    from ev_routing.inputs import ROUTING_COLUMNS

    for dataset, latitude in (("competition", 42.27708), ("evaluation", 42.28)):
        (tmp_path / f"{dataset}_routing_nodes.csv").write_text(
            ",".join(ROUTING_COLUMNS) + "\n"
            f"BASE,base,{latitude},-83.76281,,,,,,,\n"
            "V1,visit,42.28,-83.76,,,,,,,\n",
        )
    load = scenarios.hackathon_scenario
    monkeypatch.setattr(
        scenarios, "hackathon_scenario",
        lambda dataset: load(dataset, data_directory=tmp_path),
    )
    _, fetch = history_server
    for dataset, latitude in (("competition", 42.27708), ("evaluation", 42.28)):
        code, envelope = fetch(f"/scenarios/hackathon?dataset={dataset}")
        assert code == 200, envelope
        scenario = envelope["scenario"]
        assert scenario["nodes"][0]["latitude"] == latitude
        assert scenario["nodes"][0]["longitude"] == -83.76281
        request = {**prepare_request(), "nodes": scenario["nodes"]}
        assert fetch("/prepare", request)[0] == 200
    assert fetch("/scenarios/hackathon?dataset=../../secret")[0] == 400
    assert fetch("/scenarios/hackathon?dataset=competition&dataset=evaluation")[0] == 400
    (tmp_path / "competition_routing_nodes.csv").unlink()
    code, response = fetch("/scenarios/hackathon?dataset=competition")
    assert code == 404 and response["error"]["code"] == "scenario_unavailable"


def test_history_upload_and_parser_share_large_csv_limit():
    from backend.history_store import MAX_HISTORY_BYTES
    from ev_routing import historical_energy

    assert MAX_HISTORY_BYTES == historical_energy.MAX_HISTORY_BYTES == 4 * 1024 ** 3
    store = HistoryStore(OfflineBedrock())
    try:
        with pytest.raises(service.ProviderError, match="CSV"):
            store.upload(io.BytesIO(b""), 300 * 1024 ** 2, "big.json")
        with pytest.raises(service.ProviderError, match="4 GiB"):
            store.upload(io.BytesIO(b""), MAX_HISTORY_BYTES + 1, "big.csv")
        # An accepted CSV length above 256 MiB reaches streaming, and an
        # interrupted upload cleans its temporary file instead of becoming ready.
        with pytest.raises(service.SolveRequestError, match="interrumpió"):
            store.upload(io.BytesIO(eved_bytes()), 300 * 1024 ** 2, "big.csv")
        assert not store.entries
    finally:
        store.close()


@pytest.fixture
def local_hackathon(tmp_path, monkeypatch):
    from backend import scenarios
    from ev_routing.inputs import ROUTING_COLUMNS

    for dataset in ("competition", "evaluation"):
        (tmp_path / f"{dataset}_routing_nodes.csv").write_text(
            ",".join(ROUTING_COLUMNS) + "\n"
            "BASE,base,0,0,,,,,,,\n"
            "V1,visit,0.0002,0.0002,,,,,,,\n"
            "V2,visit,0.0028,0.0028,,,,,,,\n"
            "F1,charger,0.001,0.001,Original,Local,2,1,1,J1772;CHAdeMO,50\n",
        )
    (tmp_path / "eVED_EV.csv").write_bytes(eved_bytes())
    monkeypatch.setattr(scenarios, "data_directory_path", lambda directory=None: tmp_path)
    return tmp_path


def test_complete_historical_case_reuses_profile_and_preserves_originals(
    history_server, local_hackathon,
):
    server, fetch = history_server
    originals = {path.name: path.read_bytes() for path in local_hackathon.glob("*.csv")}
    code, first = fetch("/scenarios/hackathon", {"dataset": "competition"})
    assert code == 200, first
    assert first["profile"]["status"] == "ready"
    assert first["profile"]["filename"] == "eVED_EV.csv"
    assert first["profile"]["summary"]["row_count"] == 12
    assert first["scenario"]["scenario"] == {"kind": "hackathon", "dataset": "competition"}
    identifier = first["profile"]["profile_id"]
    assert server.runtime.histories.get(identifier).path.parent != local_hackathon
    code, second = fetch("/scenarios/hackathon", {"dataset": "evaluation"})
    assert code == 200 and second["profile"]["profile_id"] == identifier
    code, variant = fetch("/scenarios/hackathon", {
        "dataset": "competition", "energy_profile_id": identifier,
        "simulation": {"customers": 1, "chargers": 0, "seed": 7},
    })
    assert code == 200, variant
    nodes = variant["scenario"]["nodes"]
    assert len(nodes) == 2
    assert nodes[0] == first["scenario"]["nodes"][0]
    assert variant["profile"]["profile_id"] == identifier
    assert variant["scenario"]["scenario"]["kind"] == "hackathon_simulation"
    assert variant["scenario"]["simulation"]["added_customers"] == 0
    assert {path.name: path.read_bytes() for path in local_hackathon.glob("*.csv")} == originals


def test_historical_case_adds_reproducible_services_on_connected_streets(
    history_server, local_hackathon,
):
    server, fetch = history_server
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for row in range(4):
        for column in range(4):
            identifier = row * 4 + column
            graph.add_node(identifier, x=column * .001, y=row * .001)
    for row in range(4):
        for column in range(4):
            for other_row, other_column in ((row + 1, column), (row, column + 1)):
                if other_row >= 4 or other_column >= 4:
                    continue
                a, b = row * 4 + column, other_row * 4 + other_column
                for source, target in ((a, b), (b, a)):
                    graph.add_edge(source, target, length=111, highway="residential")
    path = local_hackathon / "streets.graphml"
    ox.save_graphml(graph, path)
    server.runtime.graphml = path
    server.runtime.network_profile = "drive"
    payload = {"dataset": "competition", "simulation": {"customers": 4, "chargers": 2, "seed": 9}}
    code, first = fetch("/scenarios/hackathon", payload)
    assert code == 200, first
    scenario = first["scenario"]
    nodes = scenario["nodes"]
    assert len([n for n in nodes if n["node_type"] == "visit"]) == 4
    assert len([n for n in nodes if n["node_type"] == "charger"]) == 2
    added = [n for n in nodes if n["node_id"].startswith("SIM-")]
    assert {(n["latitude"], n["longitude"]) for n in added} == {
        (.001, .002), (.002, .001), (.002, .002),
    }
    assert len({n["node_id"] for n in nodes}) == len(nodes)
    charger = next(n for n in added if n["node_type"] == "charger")
    assert charger["connector_types"] == "J1772;CHAdeMO"
    assert charger["max_power_kw"] == 50
    assert scenario["simulation"]["added_chargers"] == 1
    code, repeated = fetch("/scenarios/hackathon", payload)
    assert code == 200 and repeated == first
    request = {
        **prepare_request(), "network_mode": "road", "nodes": nodes,
        "scenario": scenario["scenario"], "operations": {"energy_margin_fraction": .15},
        "energy_profile_id": first["profile"]["profile_id"],
    }
    code, prepared = fetch("/prepare", request)
    assert code == 200, prepared
    assert prepared["instance"]["operations"]["energy_margin_fraction"] == .15
    context = next(iter(server.runtime.contexts.values()))[1]
    assert context.road.provenance["scenario"] == scenario["scenario"]
    code, impossible = fetch("/scenarios/hackathon", {
        "dataset": "competition", "simulation": {"customers": 20, "chargers": 2},
    })
    assert code == 400 and "nodos viales elegibles" in impossible["error"]["message"]


@pytest.mark.parametrize("payload", [
    {"dataset": []},
    {"dataset": "competition", "path": "/secret.csv"},
    {"dataset": "competition", "energy_profile_id": []},
    {"dataset": "competition", "simulation": {"customers": True, "chargers": 0}},
    {"dataset": "competition", "simulation": {"customers": 199, "chargers": 1}},
    {"dataset": "competition", "simulation": {"customers": 1, "chargers": -1}},
    {"dataset": "competition", "simulation": {"customers": 1, "chargers": 0, "seed": -1}},
])
def test_historical_case_rejects_invalid_options(history_server, local_hackathon, payload):
    _, fetch = history_server
    assert fetch("/scenarios/hackathon", payload)[0] in (400, 404)


def test_missing_local_history_or_streets_has_actionable_error(history_server, local_hackathon):
    _, fetch = history_server
    code, missing_streets = fetch("/scenarios/hackathon", {
        "dataset": "competition", "simulation": {"customers": 3, "chargers": 1},
    })
    assert code == 400 and "red de Ann Arbor" in missing_streets["error"]["message"]
    (local_hackathon / "eVED_EV.csv").unlink()
    code, missing = fetch("/scenarios/hackathon", {"dataset": "competition"})
    assert code == 404 and missing["error"]["code"] == "example_history_unavailable"
