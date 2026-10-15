"""Estados, presupuesto, fallback y dos backends reales sobre un óptimo conocido."""

from dataclasses import dataclass
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest
from pyomo.opt import SolutionStatus, SolverResults, SolverStatus
from pyomo.opt import TerminationCondition as TC

from ev_routing import solve
from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    ProblemInstance,
    Solution,
    SolverConfig,
)


@pytest.fixture
def instance():
    return ProblemInstance(
        nodes=[Node(node_id="depot", node_type="base")]
        + [Node(node_id=str(i), node_type="visit") for i in range(1, 4)],
        arcs=[],
        parameters=ModelParameters(vehicle_count=1, movement_limit=4),
    )


@dataclass
class Reply:
    count: int | None = 2
    energy: float = 5
    bound: float | None = 2
    termination: TC = TC.optimal
    elapsed: float = 0
    error: Exception | None = None
    placeholder: bool = False
    solcount: bool = True
    extract_error: bool = False


class LicenseError(Exception):
    def __init__(self, errno):
        super().__init__("sensitive license detail that must not be copied")
        self.errno = errno


def result_from(reply):
    results = SolverResults()
    results.solver.status = SolverStatus.ok
    results.solver.termination_condition = reply.termination
    results.problem.upper_bound = reply.bound
    results.problem.lower_bound = reply.bound
    results.solver.dual_bound = reply.bound
    if reply.solcount:
        results.problem.number_of_solutions = int(reply.count is not None)
    if reply.count is not None or reply.placeholder:
        candidate = results.solution.add()
        candidate.status = (
            SolutionStatus.optimal if reply.termination == TC.optimal else SolutionStatus.stoppedByLimit
        )
        if reply.count is not None:
            candidate.variable = {
                f"y[{i}]": {"Value": int(i <= reply.count)} for i in range(1, 4)
            }
            candidate.variable["E_total"] = {"Value": reply.energy}
    return results


@pytest.fixture
def harness(monkeypatch, instance):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(solve, "monotonic", lambda: clock.now)
    model = pyo.ConcreteModel()
    model.y = pyo.Var(range(1, 4), domain=pyo.Binary)
    model.served_count = pyo.Expression(expr=sum(model.y.values()))
    model.E_total = pyo.Var()
    model.deliveries_objective = pyo.Objective(expr=model.served_count, sense=pyo.maximize)
    model.energy_objective = pyo.Objective(expr=model.E_total)
    model.energy_objective.deactivate()

    def load_from(results):
        for name, data in results.solution(0).variable.items():
            model.find_component(name).set_value(data["Value"])

    model.solutions.load_from = load_from
    monkeypatch.setattr(solve, "build_model", lambda _: model)

    def activate(m, count):
        m.deliveries_objective.deactivate()
        m.energy_objective.activate()
        m.fixed_count = pyo.Constraint(expr=m.served_count == count)

    monkeypatch.setattr(solve, "activate_energy_phase", activate)
    state = SimpleNamespace(latest=None)

    def extract(m, _):
        if state.latest.extract_error:
            raise ValueError("incomplete vector")
        served = [str(i) for i in range(1, 4) if pyo.value(m.y[i]) > 0.5]
        return Solution(
            routes=[],
            served_visit_ids=served,
            unserved_visit_ids=[i for i in instance.customer_ids if i not in served],
            net_energy_kwh=pyo.value(m.E_total),
        )

    monkeypatch.setattr(solve, "extract_solution", extract)
    solvers, requests, scripts = {}, [], {}

    class FakeSolver:
        def __init__(self, name):
            self.name, self.options, self.calls = name, {}, []
            self.closed = False

        def solve(self, _, **kwargs):
            self.calls.append((dict(self.options), kwargs))
            reply = scripts[self.name].pop(0)
            clock.now += reply.elapsed
            if reply.error:
                raise reply.error
            state.latest = reply
            return result_from(reply)

        def close(self):
            self.closed = True

    def factory(name):
        requests.append(name)
        if isinstance(scripts[name], Exception):
            raise scripts[name]
        backend = solvers.setdefault(name, FakeSolver(name))
        return solve._Backend(name, backend, "test.1")

    monkeypatch.setattr(solve, "_make_backend", factory)
    return SimpleNamespace(
        clock=clock, model=model, scripts=scripts, solvers=solvers, requests=requests
    )


def execute(instance, harness, *replies, backend="gurobi", **config):
    harness.scripts[backend] = list(replies)
    return solve.solve_instance(instance, SolverConfig(solver=backend, **config))


def test_two_phases_share_budget_and_record_separate_bounds(instance, harness):
    result = execute(
        instance,
        harness,
        Reply(count=3, energy=9, bound=3, elapsed=20),
        Reply(count=3, energy=4, bound=4, elapsed=5),
        time_limit_seconds=100,
        threads=2,
        seed=31,
    )
    assert result.status == "optimal" and result.lexicographic_optimal
    assert result.solution.net_energy_kwh == 4
    first, second = result.phases
    assert (first.sense, first.incumbent, first.best_bound) == ("maximize", 3, 3)
    assert (second.sense, second.incumbent, second.best_bound) == ("minimize", 4, 4)
    assert first.runtime_seconds == 20 and result.runtime_seconds == 25
    calls = harness.solvers["gurobi"].calls
    assert [call[0]["TimeLimit"] for call in calls] == [70, 80]
    assert calls[0][0] == {"TimeLimit": 70, "MIPGap": 0, "Threads": 2, "Seed": 31}
    assert calls[0][1] == {"load_solutions": False, "tee": False}
    assert harness.solvers["gurobi"].closed


def test_phase_one_timeout_makes_energy_optimum_conditional(instance, harness):
    result = execute(
        instance,
        harness,
        Reply(count=1, bound=3, termination=TC.maxTimeLimit),
        Reply(count=1, energy=2, bound=2),
    )
    assert result.solution is not None
    assert result.phases[1].proven_optimal
    assert not result.phases[0].proven_optimal
    assert not result.lexicographic_optimal
    assert result.status == "feasible" and "condicionada" in result.message
    assert result.phases[0].absolute_gap == 2
    assert result.phases[0].relative_gap == pytest.approx(2 / 3)


@pytest.mark.parametrize("solcount", [False, True])
def test_timeout_empty_placeholder_is_not_an_incumbent(instance, harness, solcount):
    result = execute(
        instance,
        harness,
        Reply(count=None, bound=3, termination=TC.maxTimeLimit, placeholder=True, solcount=solcount),
    )
    assert result.status == "time_limit"
    assert result.solution is None
    assert len(result.phases) == 1
    assert not result.phases[0].has_solution
    assert result.phases[0].best_bound == 3
    assert result.phases[0].relative_gap is None


@pytest.mark.parametrize(
    "second",
    [
        Reply(count=None, termination=TC.maxTimeLimit, placeholder=True),
        Reply(error=RuntimeError("numerical failure")),
        Reply(extract_error=True),
    ],
)
def test_phase_two_failure_keeps_phase_one_solution(instance, harness, second):
    result = execute(instance, harness, Reply(count=2, energy=5, bound=2), second)
    assert result.status == "feasible"
    assert result.solution.served_visit_ids == ["1", "2"]
    assert result.solution.net_energy_kwh == 5
    assert not result.lexicographic_optimal
    assert not result.phases[1].has_solution
    assert harness.requests == ["gurobi"]  # No fallback por fallo numérico o timeout.


def test_timeout_with_worse_incumbent_does_not_replace_better_one(instance, harness):
    result = execute(
        instance,
        harness,
        Reply(count=2, energy=5, bound=2),
        Reply(count=2, energy=9, bound=1, termination=TC.maxTimeLimit),
    )
    assert result.solution.net_energy_kwh == 5
    assert result.phases[1].incumbent == 9
    assert "fase 1" in result.phases[1].message
    assert not result.lexicographic_optimal


def test_phase_two_cannot_change_fixed_service_count(instance, harness):
    result = execute(
        instance, harness, Reply(count=2, bound=2), Reply(count=1, energy=1, bound=1)
    )
    assert result.solution.served_visit_ids == ["1", "2"]
    assert result.phases[1].status == "error"
    assert not result.lexicographic_optimal


def test_budget_exhausted_by_first_phase_does_not_reset_clock(instance, harness):
    result = execute(
        instance, harness, Reply(count=2, bound=3, elapsed=12, termination=TC.maxTimeLimit),
        time_limit_seconds=10,
    )
    assert result.solution is not None
    assert result.phases[1].status == "time_limit"
    assert len(harness.solvers["gurobi"].calls) == 1
    assert result.runtime_seconds == 12  # Reportar el exceso real, no truncarlo.


def test_model_build_time_is_charged_to_total_budget(instance, harness, monkeypatch):
    def expensive_build(_):
        harness.clock.now += 4
        return harness.model

    monkeypatch.setattr(solve, "build_model", expensive_build)
    result = execute(
        instance, harness, Reply(count=2, bound=2, elapsed=2),
        Reply(count=2, energy=3, bound=3), time_limit_seconds=10,
    )
    calls = harness.solvers["gurobi"].calls
    assert calls[0][0]["TimeLimit"] == pytest.approx(4.2)
    assert calls[1][0]["TimeLimit"] == pytest.approx(4)
    assert result.runtime_seconds == 6


def test_auto_falls_back_on_missing_backend(instance, harness):
    harness.scripts["gurobi"] = solve._BackendUnavailable("gurobi: no disponible")
    harness.scripts["scip"] = [Reply(count=2, bound=2), Reply(count=2, energy=3, bound=3)]
    result = solve.solve_instance(instance, SolverConfig())
    assert result.used_solver == "scip" and result.lexicographic_optimal
    assert result.fallback_reason == "gurobi: no disponible"
    assert harness.requests == ["gurobi", "scip"]


@pytest.mark.parametrize("errno", [10009, 10010])
def test_license_failure_in_actual_attempt_falls_back_without_resetting_budget(
    instance, harness, errno
):
    harness.scripts["gurobi"] = [Reply(error=LicenseError(errno), elapsed=4)]
    harness.scripts["scip"] = [Reply(count=2, bound=2, elapsed=2), Reply(energy=3, bound=3)]
    result = solve.solve_instance(instance, SolverConfig(time_limit_seconds=100))
    assert result.used_solver == "scip"
    assert result.fallback_reason and "licencia" in result.fallback_reason
    assert "sensitive" not in result.model_dump_json()
    assert harness.solvers["scip"].calls[0][0]["limits/time"] == 66
    assert harness.solvers["scip"].calls[1][0]["limits/time"] == 94
    assert harness.solvers["gurobi"].closed
    assert result.phases[0].runtime_seconds == 6


def test_license_size_failure_in_second_phase_preserves_delivery_certificate(instance, harness):
    harness.scripts["gurobi"] = [Reply(count=2, bound=2), Reply(error=LicenseError(10010))]
    harness.scripts["scip"] = [Reply(count=2, energy=3, bound=3)]
    result = solve.solve_instance(instance, SolverConfig())
    assert result.used_solver == "scip" and result.lexicographic_optimal
    assert "gurobi" in result.phases[0].message
    assert "scip" in result.phases[1].message
    assert result.solver_version == "test.1"


def test_failed_second_phase_fallback_retains_first_backend_provenance(instance, harness):
    harness.scripts["gurobi"] = [Reply(count=2, bound=2), Reply(error=LicenseError(10010))]
    harness.scripts["scip"] = solve._BackendUnavailable("scip: no disponible")
    result = solve.solve_instance(instance, SolverConfig())
    assert result.solution is not None and result.status == "feasible"
    assert result.used_solver == "gurobi" and result.solver_version == "test.1"
    assert result.phases[1].status == "unavailable"
    assert result.fallback_reason


def test_backend_cleanup_error_cannot_erase_solution():
    def bad_close():
        raise RuntimeError("backend cleanup failed")

    solve._Backend("gurobi", SimpleNamespace(close=bad_close), "test").close()


def test_explicit_solver_does_not_fall_back(instance, harness):
    result = execute(instance, harness, Reply(error=LicenseError(10009)))
    assert result.status == "unavailable"
    assert result.solution is None
    assert result.fallback_reason is None
    assert harness.requests == ["gurobi"]


@pytest.mark.parametrize(
    "termination,status",
    [(TC.infeasible, "infeasible"), (TC.infeasibleOrUnbounded, "infeasible_or_unbounded")],
)
def test_model_failure_never_triggers_fallback(instance, harness, termination, status):
    harness.scripts["gurobi"] = [Reply(count=None, bound=None, termination=termination)]
    result = solve.solve_instance(instance, SolverConfig())
    assert result.status == status and result.solution is None
    assert result.fallback_reason is None
    assert harness.requests == ["gurobi"]


def test_positive_gap_optimal_status_is_not_lexicographic_proof(instance, harness):
    result = execute(
        instance, harness, Reply(count=1, bound=2), Reply(count=1, energy=5, bound=4),
        relative_gap=0.5,
    )
    assert not result.phases[0].proven_optimal
    assert not result.phases[1].proven_optimal
    assert not result.lexicographic_optimal


def test_integer_delivery_bound_can_certify_count_before_timeout(instance, harness):
    result = execute(
        instance, harness, Reply(count=2, bound=2.8, termination=TC.maxTimeLimit),
        Reply(count=2, energy=4, bound=4),
    )
    assert result.lexicographic_optimal
    assert result.phases[0].termination_condition == "maxTimeLimit"
    assert result.phases[0].best_bound == 2.8


def test_negative_energy_and_scip_global_bound_have_correct_direction(instance, harness):
    result = execute(
        instance, harness, Reply(count=2, bound=2),
        Reply(count=2, energy=-3, bound=-5, termination=TC.maxTimeLimit), backend="scip",
    )
    second = result.phases[1]
    assert second.best_bound == -5 and second.incumbent == -3
    assert second.absolute_gap == 2 and second.relative_gap == pytest.approx(0.4)
    assert result.solution.net_energy_kwh == -3
    assert harness.solvers["scip"].calls[0][0]["parallel/maxnthreads"] == 1


def test_scip_timeout_uses_native_dual_bound_instead_of_missing_problem_bound():
    results = result_from(Reply(count=2, bound=7, termination=TC.maxTimeLimit))
    results.problem.upper_bound = None
    assert solve._best_bound(results, "scip", "maximize") == 7


@pytest.mark.parametrize("backend,value", [("scip", 1e20), ("gurobi", 1e100), ("gurobi", float("nan"))])
def test_infinite_sentinel_bounds_are_not_serialized_as_real_certificates(backend, value):
    results = result_from(Reply(bound=value))
    assert solve._best_bound(results, backend, "maximize") is None


def test_inconsistent_bound_cannot_certify_optimality(instance, harness):
    result = execute(
        instance, harness, Reply(count=2, bound=1), Reply(count=2, energy=3, bound=3)
    )
    assert result.phases[0].best_bound is None
    assert not result.lexicographic_optimal
    assert "incompatible" in result.phases[0].message


def test_both_backends_unavailable_produces_structured_result(instance, harness):
    harness.scripts["gurobi"] = solve._BackendUnavailable("gurobi: no disponible")
    harness.scripts["scip"] = solve._BackendUnavailable("scip: no disponible")
    result = solve.solve_instance(instance, SolverConfig())
    assert result.status == "unavailable"
    assert result.used_solver is None
    assert result.fallback_reason == "gurobi: no disponible"
    assert "scip" in result.message
    assert result.model_dump_json()


def test_activation_failure_keeps_first_incumbent(instance, harness, monkeypatch):
    def fail(*_):
        raise ValueError("formulation error")

    monkeypatch.setattr(solve, "activate_energy_phase", fail)
    result = execute(instance, harness, Reply(count=2, bound=2))
    assert result.status == "feasible" and result.solution is not None
    assert not result.lexicographic_optimal


@pytest.mark.solver
@pytest.mark.parametrize("backend,plugin", [("gurobi", "gurobi_direct"), ("scip", "scip")])
def test_real_backends_find_known_lexicographic_optimum(backend, plugin):
    """Dos clientes y circuito mínimo de 3 kWh, idéntico para ambos backends."""
    if not pyo.SolverFactory(plugin).available(exception_flag=False):
        pytest.skip(f"{backend} no instalado")
    instance = ProblemInstance(
        nodes=[
            Node(node_id="base", node_type="base"),
            Node(node_id="a", node_type="visit"),
            Node(node_id="b", node_type="visit"),
        ],
        arcs=[
            Arc(from_node_id=i, to_node_id=j, energy_kwh=1)
            for i, j in [("base", "a"), ("a", "b"), ("b", "base")]
        ],
        parameters=ModelParameters(
            vehicle_count=1, movement_limit=4, battery_capacity_kwh=10, reserve_kwh=1
        ),
    )
    result = solve.solve_instance(instance, SolverConfig(solver=backend, time_limit_seconds=10))
    if result.status == "unavailable":
        pytest.skip(result.message)
    assert result.status == "optimal", result.model_dump()
    assert result.used_solver == backend
    assert result.fallback_reason is None
    assert result.lexicographic_optimal
    assert set(result.solution.served_visit_ids) == {"a", "b"}
    assert result.solution.net_energy_kwh == pytest.approx(3)
    assert result.phases[0].best_bound == pytest.approx(2)
    assert result.phases[1].best_bound == pytest.approx(3)
    assert result.solver_version
