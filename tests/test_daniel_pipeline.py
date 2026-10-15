"""Aceptación del contrato importado, con óptimos sintéticos calculados a mano."""

import json
import sys
from pathlib import Path

import pytest

from ev_routing import cli, pipeline
from ev_routing.contracts import SolverConfig, SolveResult
from ev_routing.inputs import load_instance

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.solver
@pytest.mark.parametrize("name,deliveries,energy,charge", [
    ("toy_recharge.json", 2, 14, 9),
    ("toy_regeneration.json", 1, 2, 0),
])
def test_native_examples_preserve_data_and_report_physical_results(name, deliveries, energy, charge):
    instance = load_instance(EXAMPLES / name)
    original = instance.model_dump(mode="json")
    result = pipeline.run_instance(instance, SolverConfig(time_limit_seconds=10))
    assert instance.model_dump(mode="json") == original
    assert result["schema_version"] == "1.0"
    assert result["validation"]["feasible"], result
    assert result["kpis"]["served_deliveries"] == deliveries
    assert result["kpis"]["net_battery_energy_kwh"] == pytest.approx(energy)
    assert result["kpis"]["charged_to_battery_kwh"] == pytest.approx(charge)
    assert result["formulation"]["movement_limit_used"] is None
    assert result["solve"]["used_solver"] == "scip-routes"
    assert result["tuning"]["status"] == "disabled"
    assert result["tuning"]["calls"] == 0
    assert result["solve"]["lexicographic_optimal"]
    assert [phase["name"] for phase in result["solve"]["phases"]] == ["deliveries", "energy"]
    json.dumps(result, allow_nan=False)
    assert "ev_routing.service_graph" not in sys.modules
    assert not any(name == "evrp" or name.startswith("evrp.") for name in sys.modules)


@pytest.mark.parametrize("representation", [
    {"kind": "service_paths_nonnegative"}, "service_paths_nonnegative",
])
def test_excluded_representation_is_rejected_before_solver(monkeypatch, representation):
    instance = load_instance(EXAMPLES / "toy_recharge.json")
    instance.provenance["representation"] = representation
    monkeypatch.setattr(pipeline, "solve_instance", lambda *a, **kw: pytest.fail("solver called"))
    with pytest.raises(ValueError, match="arcos elementales"):
        pipeline.run_instance(instance)


def test_no_incumbent_stays_unavailable_without_fake_kpis(monkeypatch):
    instance = load_instance(EXAMPLES / "toy_recharge.json")
    monkeypatch.setattr(
        pipeline, "solve_instance",
        lambda *a, **kw: SolveResult(requested_solver="scip-routes", status="time_limit"),
    )
    result = pipeline.run_instance(instance)
    assert result["status"] == "time_limit"
    assert result["validation"] is None
    assert result["solve"]["solution"] is None
    assert result["kpis"]["served_deliveries"] is None
    assert result["kpis"]["net_battery_energy_kwh"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.solver
def test_cli_uses_the_same_native_pipeline(tmp_path):
    output = tmp_path / "run.json"
    assert cli.main([
        "run", "--instance", str(EXAMPLES / "toy_recharge.json"),
        "--output", str(output), "--time-limit-seconds", "10",
    ]) == 0
    result = json.loads(output.read_text())
    assert result["schema_version"] == "1.0"
    assert result["solve"]["used_solver"] == "scip-routes"
    assert result["validation"]["feasible"]
    assert result["kpis"]["served_deliveries"] == 2
    assert result["kpis"]["net_battery_energy_kwh"] == pytest.approx(14)


@pytest.mark.parametrize("text", ['{"schema_version":"1.0","schema_version":"2.0"}', '{"x":NaN}'])
def test_cli_rejects_ambiguous_or_nonfinite_json(tmp_path, text):
    instance = tmp_path / "invalid.json"
    instance.write_text(text)
    with pytest.raises(SystemExit) as error:
        cli.main(["run", "--instance", str(instance), "--output", str(tmp_path / "result.json")])
    assert error.value.code == 2


def test_cli_rejects_boolean_energy_like_the_web(tmp_path, monkeypatch):
    payload = json.loads((EXAMPLES / "toy_recharge.json").read_text())
    payload["arcs"][0]["energy_kwh"] = True
    source = tmp_path / "boolean-energy.json"
    source.write_text(json.dumps(payload))
    monkeypatch.setattr(cli, "run_instance", lambda *a, **kw: pytest.fail("solver called"))
    with pytest.raises(SystemExit) as error:
        cli.main(["run", "--instance", str(source), "--output", str(tmp_path / "result.json")])
    assert error.value.code == 2
