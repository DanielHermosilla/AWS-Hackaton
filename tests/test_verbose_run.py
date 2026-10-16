"""Trazabilidad de prompts, cambios efectivos y logs completos sin llamadas AWS."""

import importlib.util
import io
import json
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest

from ev_routing.contracts import Arc, Node, ProblemInstance
from ev_routing.inputs import load_instance, save_instance
from ev_routing.llm.bedrock import BedrockPolicyClient, BedrockResponseError
from ev_routing.route_policy import ROUTE_PROMPT, choose_route_policy
from ev_routing.search_policy import BedrockConfig, SearchConfig
from ev_routing.service_graph import REPRESENTATION, PathArchive, check_service_context


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


def test_live_response_prints_even_invalid_output_without_transport_or_reasoning(capsys):
    class WithReasoning(BedrockDouble):
        def converse(self, **kwargs):
            response = super().converse(**kwargs)
            response["output"]["message"]["content"].append({
                "reasoningContent": {"reasoningText": {"text": "private reasoning block"}},
            })
            return response
    native = WithReasoning("invalid JSON response")
    client = BedrockPolicyClient(
        BedrockConfig(model_id="test-model"), client=native, show_trace=True,
    )
    with pytest.raises(BedrockResponseError, match="invalid_json"):
        client({"event": "pricing_progress"})
    output = capsys.readouterr().out
    assert "invalid JSON response" in output
    assert "pricing_progress" in output and '"totalTokens": 25' in output
    assert "todavía no implica aplicación" in output
    assert "not-to-be-logged" not in output
    assert "private reasoning block" not in output


def test_reasoning_model_omits_sampling_temperature_and_parses_only_final_text(tmp_path):
    class ReasoningDouble(BedrockDouble):
        def converse(self, **kwargs):
            response = super().converse(**kwargs)
            response["output"]["message"]["content"].insert(
                0, {"reasoningContent": {"reasoningText": {"text": "not policy JSON"}}},
            )
            return response

    native = ReasoningDouble('{"branching":"mostinf"}')
    client = BedrockPolicyClient(
        BedrockConfig(model_id="us.anthropic.claude-fable-5", reasoning_effort="max"),
        client=native, temperature=0, trace_directory=str(tmp_path),
    )
    response = client({"event": "before_search"})
    assert response["policy"] == {"branching": "mostinf"}
    payload = json.loads((tmp_path / "llm-request.json").read_text())
    assert "temperature" not in payload["inferenceConfig"]
    assert payload["additionalModelRequestFields"] == {"output_config": {"effort": "max"}}


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
    assert script.main([
        *inputs, "--llm-reasoning-effort", "max", "--bedrock-fast-model", "fast-model",
        "--llm-fast-timeout-seconds", "6", "--llm-instance-context-bytes", "8000",
        "--decision-interval-seconds", "10",
        "--energy-relative-gap", "0.003",
    ]) == 1
    command = seen[0]
    assert "--tee" in command and "--show-llm-trace" in command
    assert command[command.index("--solver") + 1] == "scip-routes"
    assert command[command.index("--energy-relative-gap") + 1] == "0.003"
    assert command[command.index("--llm-max-calls") + 1] == "4"
    assert command[command.index("--llm-reasoning-effort") + 1] == "max"
    assert command[command.index("--bedrock-fast-model") + 1] == "fast-model"
    assert command[command.index("--llm-fast-timeout-seconds") + 1] == "6.0"
    assert command[command.index("--llm-instance-context-bytes") + 1] == "8000"
    assert command[command.index("--decision-interval-seconds") + 1] == "10.0"
    assert (tmp_path / "output/run.log").read_text() == "SCIP node log\nexact raw line\n"
    assert "SCIP node log\nexact raw line\n" in capsys.readouterr().out
    manifest = json.loads((tmp_path / "output/run-config.json").read_text())
    assert (manifest["customers"], manifest["chargers"]) == (20, 60)
    assert manifest["search_config"]["log_directory"] == str(tmp_path / "output/logs")
    assert manifest["solver_config"]["energy_relative_gap"] == .003


def test_script_rejects_wrong_counts_before_starting_solver(script, inputs, monkeypatch, capsys):
    source = Path(inputs[1])
    data = json.loads(source.read_text())
    data["nodes"] = [node for node in data["nodes"] if node["node_id"] != "F0"]
    source.write_text(json.dumps(data))
    monkeypatch.setattr(script.subprocess, "Popen", lambda *a, **k: pytest.fail("solver"))
    assert script.main(inputs) == 2
    assert "60 estaciones" in capsys.readouterr().err


def test_script_preserves_existing_logs(script, inputs, tmp_path, capsys):
    output = tmp_path / "output"
    output.mkdir()
    (output / "run.log").write_text("previous run")
    assert script.main(inputs) == 2
    assert "no está vacío" in capsys.readouterr().err
    assert (output / "run.log").read_text() == "previous run"


def test_script_prepares_40_customers_and_passes_matching_new_snapshots(script, inputs,
                                                                    tmp_path, monkeypatch):
    nodes = [
        Node(node_id="0", node_type="base", latitude=-1, longitude=-1),
        *[Node(node_id=f"C{i}", node_type="visit", latitude=i / 19, longitude=i / 19)
          for i in range(20)],
        *[Node(node_id=f"F{i}", node_type="charger", latitude=2, longitude=2 + i / 100)
          for i in range(60)],
        *[Node(node_id=f"J{i}", node_type="junction", latitude=i / 50, longitude=0.7)
          for i in range(25)],
    ]
    road = ProblemInstance(nodes=nodes, arcs=[
        Arc(from_node_id=a, to_node_id=b, energy_kwh=0.1)
        for node in nodes[1:] for a, b in (("0", node.node_id), (node.node_id, "0"))
    ])
    road_path = tmp_path / "roads.json"
    save_instance(road, road_path)
    original_bytes = road_path.read_bytes()
    commands = []

    def popen(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=io.StringIO("SCIP simulation\n"), wait=lambda: 0)

    monkeypatch.setattr(script.subprocess, "Popen", popen)
    assert script.main([*inputs, "--simulate-customers", "40", "--simulation-seed", "7"]) == 0
    output = tmp_path / "output"
    generated = load_instance(output / "instance.json")
    compact = load_instance(output / "service-instance.json")
    archive = PathArchive.model_validate_json((output / "service-paths.json").read_text())
    check_service_context(compact, generated, archive)
    assert len(compact.customer_ids) == 40 and len(compact.charger_ids) == 60
    assert compact.provenance["horizon_selection"]["movement_limit_used"] is None
    assert road_path.read_bytes() == original_bytes
    manifest = json.loads((output / "run-config.json").read_text())
    assert manifest["simulation"]["seed"] == 7
    assert len(manifest["simulation"]["added_customer_ids"]) == 20
    command = commands[0]
    assert command[command.index("--road-instance") + 1] == str(output / "instance.json")
    assert command[command.index("--path-archive") + 1] == str(output / "service-paths.json")
    # Se puede reutilizar la instancia de 40 sin volver a generar demanda ni caminos.
    assert script.main([
        "--instance", str(output / "service-instance.json"),
        "--road-instance", str(output / "instance.json"),
        "--path-archive", str(output / "service-paths.json"),
        "--output-dir", str(tmp_path / "reused"), "--search-policy", "standard",
    ]) == 0
    assert len(commands) == 2
    reused = json.loads((tmp_path / "reused/run-config.json").read_text())
    assert not reused["simulation_generated"]
    assert reused["simulation"] == manifest["simulation"]


def test_simulation_rejects_initial_solution_from_previous_snapshot(script, inputs, capsys):
    assert script.main([
        *inputs, "--simulate-customers", "40", "--initial-solution", "old.start.json",
    ]) == 2
    assert "nuevo snapshot" in capsys.readouterr().err
