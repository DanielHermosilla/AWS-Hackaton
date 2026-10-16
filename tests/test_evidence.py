"""Protecciones de inferencia y medición, con óptimos pequeños conocidos."""

import json
from pathlib import Path

import pytest
from test_operations import tiny

from ev_routing.contracts import Node
from ev_routing.evidence import (
    compare_pair,
    impact_metrics,
    main,
    scenario_road,
)
from ev_routing.inputs import save_instance


def measured(**changes):
    row = {
        "case": "base", "budget": 10, "seed": 0, "repetition": 0, "policy": "standard",
        "feasible": True, "deliveries": 2, "energy_kwh": 4, "distance_km": 10,
        "wall_seconds": 2, "instance_sha256": "same", "llm_effective": False,
        "deliveries_proven_optimal": True, "energy_proven_optimal": True,
        "energy_relative_gap": 0, "energy_best_bound": 4,
    }
    return {**row, **changes}


def test_timeout_ratio_is_not_speedup_and_worse_energy_is_kept():
    ref = measured(energy_proven_optimal=False, energy_relative_gap=.2)
    other = measured(policy="adaptive", energy_kwh=5, wall_seconds=1)
    pair = compare_pair(ref, other, .005)
    assert pair["certified_speedup"] is None
    assert pair["energy_saving_percent"] == -25


def test_different_coverage_and_different_instance_are_not_energy_comparisons():
    for other in (measured(deliveries=1), measured(instance_sha256="different"), measured(feasible=False)):
        pair = compare_pair(measured(), other, .005)
        assert pair["energy_saving_percent"] is None
        assert pair["certified_speedup"] is None
    assert compare_pair(measured(), measured(wall_seconds=1), .005)["certified_speedup"] == 2


def test_emissions_count_initial_energy_and_keep_negative_net_savings():
    factors = {
        "diesel_kg_co2_per_litre": 2.5, "diesel_litres_per_100km": 8,
        "factor_source": "test fixture", "factor_date": "2026-01-01",
        "consumption_assumption": "synthetic", "geography": "synthetic",
        "grid_kg_co2_per_kwh": 1, "grid_source": "test fixture", "grid_date": "2026-01-01",
        "charging_efficiency": .8,
    }
    result = impact_metrics(measured(), factors)
    # 10 km * .08 L/km * 2.5 kg/L = 2 kg. 4 kWh / .8 = 5 kWh.
    assert result["tailpipe_co2_avoided_kg"] == 2
    assert result["operational_co2_difference_kg"] == -3
    assert impact_metrics(measured(), None)["tailpipe_co2_avoided_kg"] is None
    factors["grid_source"] = None
    with pytest.raises(ValueError, match="fuente"):
        impact_metrics(measured(), factors)


def test_generated_demand_keeps_all_streets_and_original_input():
    road = tiny()
    # B is an existing reachable junction, not a duplicate of another service.
    road.nodes[2] = Node(node_id="B", node_type="junction")
    original = road.model_dump_json()
    case = {
        "id": "scale", "kind": "generated_demand", "customers": 2, "vehicles": 3,
        "parameters": {}, "operations": {}, "scenario_seed": 9,
    }
    result = scenario_road(road, case)
    assert set(result.customer_ids) == {"A", "B"}
    assert result.parameters.vehicle_count == 3
    assert result.arcs == road.arcs
    assert road.model_dump_json() == original
    assert result.provenance["experiment"]["street_network_changed"] is False


@pytest.mark.solver
def test_campaign_processes_known_optimum_and_rejects_tampering(tmp_path):
    road = tmp_path / "road.json"
    instance = tiny()
    # Base official SoC is already .6. Tiny capacity/reserve are declared assumptions.
    save_instance(instance, road)
    output = tmp_path / "evidence"
    argv = [
        "campaign", "--road-instance", str(road), "--output-dir", str(output),
        "--customers", "--seeds", "0", "--budgets", "5", "--execute",
    ]
    assert main(argv) == 0
    rows = json.loads((output / "runs.json").read_text())
    assert len(rows) == 2
    assert all(r["feasible"] and r["deliveries"] == 2 for r in rows)
    # Independent known optimum: 0-A-B-0 costs 3 with one vehicle inactive.
    assert all(r["energy_kwh"] == pytest.approx(3) for r in rows)
    assert all(r["llm_calls"] == 0 for r in rows)
    previous = [p.read_bytes() for p in sorted((output / "runs").glob("*/execution.json"))]
    assert main([*argv, "--resume"]) == 0
    assert previous == [p.read_bytes() for p in sorted((output / "runs").glob("*/execution.json"))]
    path = next((output / "runs").glob("*/result.json"))
    result = json.loads(path.read_text())
    external = tmp_path / "external.json"
    external.write_text(json.dumps({
        "method": "untrusted submission", "instance_sha256": result["instance_sha256"],
        "solution": result["solve"]["solution"], "wall_seconds": .1,
    }))
    audit = tmp_path / "audit.json"
    external_args = [
        "validate-external", "--case-dir", str(output / "cases/base"),
        "--result", str(external), "--output", str(audit),
    ]
    assert main(external_args) == 0
    assert json.loads(audit.read_text())["kpis"]["net_battery_energy_kwh"] == pytest.approx(3)
    invalid = json.loads(external.read_text())
    invalid["solution"]["routes"][0]["steps"][0]["battery_arrival_kwh"] = -1
    external.write_text(json.dumps(invalid))
    assert main(external_args) == 2
    path.write_text("{}")
    assert main([*argv, "--resume"]) == 2


def test_impact_example_conversion():
    path = Path(__file__).resolve().parents[1] / "config/benchmark-impact.example.json"
    factor = json.loads(path.read_text())["diesel_kg_co2_per_litre"]
    assert factor == pytest.approx(10.180 / 3.785411784, rel=1e-8)
