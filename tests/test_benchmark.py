"""Integración CLI en procesos separados y protección contra comparaciones falsas."""

import json

import pytest
from test_operations import tiny

from ev_routing.benchmark import build_parser, run_benchmark, summarize_run
from ev_routing.heuristics import InitialSolution, build_greedy_start
from ev_routing.inputs import save_instance
from ev_routing.service_graph import build_service_graph, fingerprint


def test_adaptive_without_applied_policy_is_ineligible():
    result = {
        "status": "optimal",
        "tuning": {"status": "fallback", "calls": 1, "applied_decisions": 0},
        "kpis": {"feasible": True, "served_deliveries": 2},
    }
    row = summarize_run("adaptive", 0, 0, 1.2, 0, result)
    assert not row["llm_comparison_eligible"]
    assert row["deliveries"] == 2
    assert row["energy_kwh"] is None
    assert row["deliveries_best_bound"] is None
    assert row["llm_totalTokens"] is None


def test_planning_decisions_are_not_counted_as_updates_during_native_search():
    result = {
        "tuning": {
            "calls": 4,
            "applied_decisions": 3,
            "decisions": [
                {"event": "before_search", "status": "applied"},
                {"event": "after_seed", "status": "applied"},
                {"event": "search_stagnation", "status": "applied"},
                {"event": "search_stagnation", "status": "rejected"},
            ],
        },
    }
    row = summarize_run("adaptive", 0, 0, 1, 0, result)
    assert row["llm_updates_during_solve"] == 1
    assert row["llm_applied"] == 3
    assert row["llm_totalTokens"] is None


@pytest.mark.solver
def test_process_benchmark_service_validation_resume_and_integrity(tmp_path):
    pytest.importorskip("pygcgopt")
    road = tiny(service_seconds=100, max_route_seconds=250)
    compact, archive = build_service_graph(road, 3)
    road_path, instance_path, archive_path = [tmp_path / p for p in ["road.json", "instance.json", "paths.json"]]
    save_instance(road, road_path)
    save_instance(compact, instance_path)
    archive_path.write_text(archive.model_dump_json())
    output = tmp_path / "benchmark"
    args = build_parser().parse_args([
        "--instance", str(instance_path), "--road-instance", str(road_path),
        "--path-archive", str(archive_path), "--output-dir", str(output),
        "--policies", "standard", "deterministic",
        "--seeds", "0", "--time-limit-seconds", "10",
    ])
    assert run_benchmark(args) == 0
    rows = json.loads((output / "summary.json").read_text())
    assert len(rows) == 2
    assert {r["policy"] for r in rows} == {"standard", "deterministic"}
    assert all(r["feasible"] and r["lexicographic_optimal"] for r in rows)
    assert all(r["deliveries"] == 2 and r["energy_kwh"] == pytest.approx(4) for r in rows)
    records = list(output.glob("*/execution.json"))
    previous = [p.read_bytes() for p in records]
    assert all("--config" in json.loads(p.read_text())["command"] for p in records)
    for path in output.glob("*/result.json"):
        result = json.loads(path.read_text())
        assert result["road_validation"]["feasible"]
        assert result["tuning"]["calls"] == 0
    args.resume = True
    assert run_benchmark(args) == 0
    assert previous == [p.read_bytes() for p in records]
    result_path = next(output.glob("*/result.json"))
    result_path.write_text("{}")
    with pytest.raises(ValueError, match="modificado"):
        run_benchmark(args)


@pytest.mark.parametrize("model_id", [None, "", " \t "])
def test_adaptive_model_is_required_before_running_processes(tmp_path, model_id):
    path = tmp_path / "instance.json"
    save_instance(tiny(), path)
    args = build_parser().parse_args(["--instance", str(path), "--output-dir", str(tmp_path / "out")])
    args.bedrock_model = model_id
    with pytest.raises(ValueError, match="export BEDROCK_MODEL_ID"):
        run_benchmark(args)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("problem", ["missing", "stale", "invalid"])
def test_initial_solution_is_checked_before_any_benchmark_process(tmp_path, monkeypatch, problem):
    instance = tiny()
    path, initial_path, output = [tmp_path / name for name in ("instance.json", "start.json", "out")]
    save_instance(instance, path)
    if problem != "missing":
        initial = InitialSolution(
            instance_sha256="outdated" if problem == "stale" else fingerprint(instance),
            solution=build_greedy_start(instance),
        )
        if problem == "invalid":
            initial.solution.routes[0].steps[0].battery_arrival_kwh = -1
        initial_path.write_text(initial.model_dump_json())
    args = build_parser().parse_args([
        "--instance", str(path), "--initial-solution", str(initial_path),
        "--output-dir", str(output), "--policies", "standard",
    ])

    def forbidden(*args, **kwargs):
        pytest.fail("No lanzar procesos con archivos de arranque inválidos")

    monkeypatch.setattr("ev_routing.benchmark.subprocess.run", forbidden)
    with pytest.raises(ValueError, match={
        "missing": "No existe el archivo --initial-solution",
        "stale": "no corresponde al snapshot",
        "invalid": "Solución inicial inválida",
    }[problem]):
        run_benchmark(args)
    assert not output.exists()
