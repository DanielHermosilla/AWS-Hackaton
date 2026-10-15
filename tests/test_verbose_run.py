"""Trazabilidad de prompts, cambios efectivos y logs completos sin llamadas AWS."""

import importlib.util
import io
import json
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest

from ev_routing.contracts import Node, ProblemInstance
from ev_routing.inputs import save_instance
from ev_routing.llm.bedrock import BedrockPolicyClient, BedrockResponseError
from ev_routing.route_policy import ROUTE_PROMPT, choose_route_policy
from ev_routing.search_policy import BedrockConfig, SearchConfig
from ev_routing.service_graph import REPRESENTATION


class BedrockDouble:
    def __init__(self, text):
        self.text, self.calls = text, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "stopReason": "end_turn",
            "output": {"message": {"content": [{"text": self.text}]}},
            "usage": {"totalTokens": 25},
            "ResponseMetadata": {"HTTPHeaders": {"not-to-be-logged": "transport"}},
        }


def test_trace_contains_exact_converse_body_and_response_without_headers(tmp_path):
    native = BedrockDouble('{"branching":"mostinf"}')
    client = BedrockPolicyClient(
        BedrockConfig(model_id="test-model"), client=native,
        system_prompt=ROUTE_PROMPT, temperature=0, trace_directory=str(tmp_path),
    )
    request = {"structure": {"customers": 20, "chargers": 60}}
    client(request)
    actual = json.loads((tmp_path / "llm-request.json").read_text())
    assert actual == native.calls[0]
    assert actual["system"][0]["text"] == ROUTE_PROMPT
    assert json.loads(actual["messages"][0]["content"][0]["text"]) == request
    assert actual["inferenceConfig"]["temperature"] == 0
    response = json.loads((tmp_path / "llm-response.json").read_text())
    assert response["output"]["message"]["content"][0]["text"] == native.text
    assert "ResponseMetadata" not in response
    assert "transport" not in (tmp_path / "llm-response.json").read_text()


def test_invalid_response_is_still_available_for_diagnosis(tmp_path):
    client = BedrockPolicyClient(
        BedrockConfig(model_id="test-model"), client=BedrockDouble("invalid JSON"),
        trace_directory=str(tmp_path),
    )
    with pytest.raises(BedrockResponseError, match="invalid_json"):
        client({})
    assert json.loads((tmp_path / "llm-response.json").read_text())["usage"]["totalTokens"] == 25


def test_only_changes_applicable_to_selected_algorithm_are_reported(tmp_path, capsys):
    config = SearchConfig(
        policy="adaptive", bedrock={"model_id": "test-model"}, log_directory=str(tmp_path),
        show_llm_trace=True,
    )
    _, report = choose_route_policy(
        config, {"applicable_actions": ["subtour_batch_size", "branching"]}, monotonic() + 60,
        provider=lambda _: {"policy": {"branching": "mostinf", "max_subset_rows": 3}},
    )
    record = report["decisions"][0]
    assert record["effective_changes"] == {"branching": {"before": "relpscost", "after": "mostinf"}}
    assert record["inactive_settings"]["max_subset_rows"] == 3
    assert json.loads((tmp_path / "llm-decision.json").read_text()) == report
    output = capsys.readouterr().out
    assert ROUTE_PROMPT in output
    assert '"before": "relpscost"' in output and '"after": "mostinf"' in output


def test_accepted_policy_with_no_effective_changes_is_explicit(tmp_path, capsys):
    config = SearchConfig(
        policy="adaptive", bedrock={"model_id": "test-model"}, log_directory=str(tmp_path),
        show_llm_trace=True,
    )
    _, report = choose_route_policy(config, {}, monotonic() + 60, provider=lambda _: {"policy": {}})
    assert report["calls"] == report["applied_decisions"] == 1
    assert not report["decisions"][0]["effective_changes"]
    assert "no cambia los parámetros efectivos" in capsys.readouterr().out


def test_skipped_call_records_reason_without_fabricating_a_prompt(tmp_path, capsys):
    config = SearchConfig(
        policy="adaptive", bedrock={"model_id": "test-model"}, log_directory=str(tmp_path),
        show_llm_trace=True,
    )
    _, report = choose_route_policy(config, {}, monotonic(), provider=lambda _: pytest.fail("AWS"))
    assert report["calls"] == 0 and report["reason"] == "insufficient_call_budget"
    assert (tmp_path / "llm-decision.json").is_file()
    assert not (tmp_path / "llm-request.json").exists()
    assert "Sin llamada" in capsys.readouterr().out


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[1] / "scripts/test_routing_verbose.py"
    spec = importlib.util.spec_from_file_location("verbose_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path):
    instance = ProblemInstance(
        nodes=[
            Node(node_id="0", node_type="base"),
            *[Node(node_id=f"C{i}", node_type="visit") for i in range(20)],
            *[Node(node_id=f"F{i}", node_type="charger") for i in range(60)],
        ], arcs=[], provenance={"representation": {"kind": REPRESENTATION}},
    )
    source, road, archive = [tmp_path / f"{name}.json" for name in ("services", "roads", "paths")]
    save_instance(instance, source)
    road.write_text("{}")
    archive.write_text("{}")
    return [
        "--instance", str(source), "--road-instance", str(road), "--path-archive", str(archive),
        "--output-dir", str(tmp_path / "output"), "--bedrock-model", "test-model",
    ]


def test_script_streams_raw_solver_output_and_propagates_exit_status(script, inputs, monkeypatch,
                                                                  tmp_path, capsys):
    seen = []

    def popen(command, **kwargs):
        seen.append(command)
        assert kwargs["stdout"] == script.subprocess.PIPE
        return SimpleNamespace(stdout=io.StringIO("SCIP node log\nexact raw line\n"), wait=lambda: 1)

    monkeypatch.setattr(script.subprocess, "Popen", popen)
    assert script.main(inputs) == 1
    command = seen[0]
    assert "--tee" in command and "--show-llm-trace" in command
    assert command[command.index("--solver") + 1] == "scip-routes"
    assert command[command.index("--llm-max-calls") + 1] == "1"
    assert (tmp_path / "output/run.log").read_text() == "SCIP node log\nexact raw line\n"
    assert "SCIP node log\nexact raw line\n" in capsys.readouterr().out
    manifest = json.loads((tmp_path / "output/run-config.json").read_text())
    assert (manifest["customers"], manifest["chargers"]) == (20, 60)
    assert manifest["search_config"]["log_directory"] == str(tmp_path / "output/logs")


def test_script_rejects_wrong_counts_before_starting_solver(script, inputs, monkeypatch, capsys):
    source = Path(inputs[1])
    data = json.loads(source.read_text())
    data["nodes"] = [node for node in data["nodes"] if node["node_id"] != "C0"]
    source.write_text(json.dumps(data))
    monkeypatch.setattr(script.subprocess, "Popen", lambda *a, **k: pytest.fail("solver"))
    assert script.main(inputs) == 2
    assert "20 clientes y 60 estaciones" in capsys.readouterr().err


def test_script_preserves_existing_logs(script, inputs, tmp_path, capsys):
    output = tmp_path / "output"
    output.mkdir()
    (output / "run.log").write_text("previous run")
    assert script.main(inputs) == 2
    assert "no está vacío" in capsys.readouterr().err
    assert (output / "run.log").read_text() == "previous run"
