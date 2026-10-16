"""Parada por cota global, independiente de la prueba de optimalidad exacta."""

from types import SimpleNamespace

import pytest
from test_route_orchestration import pairs

from ev_routing.contracts import SolverConfig
from ev_routing.route_solver import _energy_gap_reached, solve_routes
from ev_routing.validation import validate_solution


@pytest.mark.parametrize("target,should_price", [(.005, False), (0.0, True)])
def test_valid_energy_bound_stops_before_pricing_without_claiming_exact_optimum(
    monkeypatch, target, should_price,
):
    import ev_routing.route_solver as solver

    # Óptimo manual: 9 kWh. 8.964 es una cota inferior válida, separada un 0.4%.
    monkeypatch.setattr(solver, "energy_relaxation", lambda *a, **k: {
        "applicable": True, "bound_kwh": 8.964, "source": "test_valid_lower_bound",
    })
    monkeypatch.setattr(solver.HybridRoutes, "improve", lambda self, best, *a: best)
    original, calls = solver._master_phase, []

    def master(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(solver, "_master_phase", master)
    instance = pairs()
    result = solve_routes(instance, SolverConfig(time_limit_seconds=3, energy_relative_gap=target))
    energy = result.phases[1]
    assert bool(calls) == should_price
    assert result.phases[0].proven_optimal
    assert result.solution.net_energy_kwh == pytest.approx(9)
    assert validate_solution(instance, result.solution, enforce_movement_limit=False).feasible
    if should_price:
        assert result.lexicographic_optimal
    else:
        assert energy.termination_condition == "energy_gap_limit"
        assert energy.relative_gap == pytest.approx(.004)
        assert energy.status == "feasible"
        assert not energy.proven_optimal and not result.lexicographic_optimal
        assert result.search["phases"] == []


@pytest.mark.parametrize("incumbent,bound,accepted", [
    (100, 99.5, True), (100, 99.49, False), (-100, -100.4, True),
    (-100, -101, False), (0, -1, False), (.001, -.001, False),
    (100, None, False), (100, float("-inf"), False),
    (100, float("nan"), False), (100, 101, False),
])
def test_gap_handles_negative_zero_missing_and_invalid_bounds(incumbent, bound, accepted):
    assert _energy_gap_reached(SimpleNamespace(net_energy_kwh=incumbent), bound, .005) is accepted
