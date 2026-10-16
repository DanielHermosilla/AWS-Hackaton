"""The web credential session reaches the same native solver used by the CLI."""

from ev_routing.contracts import Node, ProblemInstance, SolverConfig, SolveResult
from ev_routing.pipeline import run_instance
from ev_routing.search_policy import SearchConfig


def test_pipeline_passes_provider_to_native_route_solver_without_serializing_it(monkeypatch):
    from ev_routing import route_solver

    supplied = []
    provider = lambda request: {"policy": {}}  # noqa: E731

    def solve(instance, config, search_config, *, initial_solution=None, policy_provider=None):
        supplied.append(policy_provider)
        return SolveResult(requested_solver="scip-routes", status="no_solution")

    monkeypatch.setattr(route_solver, "solve_routes", solve)
    instance = ProblemInstance(nodes=[Node(node_id="base", node_type="base")], arcs=[])
    result = run_instance(
        instance, SolverConfig(solver="scip-routes"), search_config=SearchConfig(),
        policy_provider=provider,
    )
    assert supplied == [provider]
    assert "policy_provider" not in result
