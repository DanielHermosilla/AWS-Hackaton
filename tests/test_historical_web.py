"""History HTTP contract: separate uploads, explicit fallback and cache invalidation."""

import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import networkx as nx
import osmnx as ox
import pytest

from backend import service
from backend.history_store import HistoryStore
from backend.local_server import make_server
from backend.runtime import Runtime
from test_web_bridge import prepare_request


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
