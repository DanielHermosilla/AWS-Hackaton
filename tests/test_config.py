"""Configuración estricta y separación entre escenario físico y resolución."""

import json

import pytest
from pydantic import ValidationError

from ev_routing.config import ProjectConfig, load_config


def test_default_scenario_and_solver_selection_are_explicit():
    config = load_config()
    assert config.model.vehicle_count == 2
    assert config.model.initial_soc == pytest.approx(0.6)
    assert config.model.initial_energy_kwh == pytest.approx(
        0.6 * config.model.battery_capacity_kwh
    )
    assert config.solver.solver == "auto"
    assert config.solver.relative_gap == 0
    assert "llm" not in config.model_dump()


def test_partial_bom_config_preserves_unset_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"model": {"movement_limit": 7}, "solver": {"solver": "scip", "seed": 11}}),
        encoding="utf-8-sig",
    )
    config = load_config(path)
    assert config.model.movement_limit == 7
    assert config.model.initial_soc == 0.6
    assert config.model.vehicle_count == 2
    assert config.solver.solver == "scip"
    assert config.solver.seed == 11
    assert config.solver.time_limit_seconds == 60
    assert config.solver.threads == 1


def test_separate_config_loads_do_not_share_mutable_defaults():
    first, second = load_config(), load_config()
    first.model.vehicle_connector_types.append("experimental")
    first.solver.threads = 8
    assert "experimental" not in second.model.vehicle_connector_types
    assert second.solver.threads == 1


@pytest.mark.parametrize(
    "values",
    [
        {"llm": {"enabled": True}},
        {"solver": {"movement_limit": 4}},
        {"solver": {"battery_capacity_kwh": 40}},
        {"solver": {"reserve_kwh": 0.1}},
        {"solver": {"feasibility_tolerance": 0.01}},
        {"solver": {"parameters": {"MIPFocus": 1}}},
        {"model": {"time_limit_seconds": 20}},
        {"model": {"time_horizon_seconds": 3600}},
        {"model": {"objective_weights": [25, 25, 20, 15, 15]}},
    ],
)
def test_unsupported_settings_are_not_silently_ignored(values):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProjectConfig.model_validate(values)


@pytest.mark.parametrize(
    "values",
    [
        {"model": {"vehicle_count": 0}},
        {"model": {"movement_limit": 0}},
        {"model": {"movement_limit": 1.5}},
        {"model": {"battery_capacity_kwh": 0}},
        {"model": {"reserve_kwh": 0}},
        {"model": {"battery_capacity_kwh": 10, "reserve_kwh": 7, "initial_soc": 0.6}},
        {"model": {"initial_soc": 1.01}},
        {"solver": {"solver": "highs"}},
        {"solver": {"time_limit_seconds": 0}},
        {"solver": {"relative_gap": -0.01}},
        {"solver": {"relative_gap": 1.01}},
        {"solver": {"threads": 0}},
        {"solver": {"threads": 1.5}},
        {"solver": {"seed": -1}},
        {"solver": {"seed": 2_000_000_001}},
    ],
)
def test_impossible_or_unsupported_resources_fail_before_execution(values):
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(values)


@pytest.mark.parametrize("text", ['{"model":', "[]", "null", '{"solver":{"seed":NaN}}'])
def test_malformed_or_nonfinite_json_config_is_rejected(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path)


def test_missing_config_is_an_actionable_file_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.json")
