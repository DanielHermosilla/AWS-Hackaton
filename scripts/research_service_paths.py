"""Contraejemplos reproducibles para docs/investigacion-caminos-recursos.md.

No cambia el preprocesador ni el solver. Usa únicamente instancias sintéticas,
el oráculo actual y una reproducción independiente de la batería por calle.
"""

from __future__ import annotations

import json
from itertools import accumulate, product
from math import isclose
from time import monotonic

from ev_routing.contracts import Arc, ModelParameters, Node, Operations, ProblemInstance, TimeWindow
from ev_routing.route_resources import RouteOracle, assemble_solution
from ev_routing.service_graph import build_service_graph
from ev_routing.validation import validate_solution


def replay(
    energies: tuple[float, ...], initial: float, capacity: float = 10, reserve: float = 1,
) -> dict:
    """Reproducir todos los estados; conservar incluso un déficit transitorio."""
    states = [initial]
    for energy in energies:
        states.append(min(capacity, states[-1] - energy))
    return {
        "nominal_energy_kwh": sum(energies),
        "battery_states_kwh": states,
        "effective_energy_kwh": initial - states[-1],
        "feasible": all(reserve <= battery <= capacity for battery in states),
    }


def profile(
    energies: tuple[float, ...], initial: float, capacity: float = 10, reserve: float = 1,
) -> tuple[bool, float]:
    """Perfil exacto derivado en el informe para un camino fijo sin recargas."""
    prefix = [0.0, *accumulate(energies)]
    low, drawdown = 0.0, 0.0
    for value in prefix:
        low = min(low, value)
        drawdown = max(drawdown, value - low)
    feasible = (
        reserve <= initial <= capacity
        and initial >= reserve + max(prefix)
        and drawdown <= capacity - reserve
    )
    final = min(initial - prefix[-1], capacity - prefix[-1] + min(prefix))
    return feasible, final


def make_window_instance() -> ProblemInstance:
    return ProblemInstance(
        name="research-energy-versus-window",
        nodes=[
            Node(node_id="base", node_type="base"),
            Node(node_id="junction", node_type="junction"),
            Node(node_id="customer", node_type="visit"),
        ],
        arcs=[
            Arc(from_node_id=a, to_node_id=b, energy_kwh=energy, travel_time_seconds=time)
            for a, b, energy, time in [
                ("base", "junction", 0.5, 600),
                ("junction", "customer", 0.5, 600),
                ("base", "customer", 2.0, 600),
                ("customer", "base", 1.0, 300),
            ]
        ],
        parameters=ModelParameters(
            vehicle_count=1, battery_capacity_kwh=10, reserve_kwh=1, movement_limit=4,
        ),
        operations=Operations(
            service_seconds=60,
            max_route_seconds=3600,
            use_customer_time_windows=True,
            customer_time_windows={
                "customer": TimeWindow(open_seconds=0, close_seconds=900),
            },
        ),
    )


def solve_tiny(instance: ProblemInstance) -> dict:
    """Agotar el oráculo existente; no invocar SCIP, AWS ni un nuevo solver."""
    oracle = RouteOracle(instance, instance.vehicle_ids[0])
    oracle.exhaust(monotonic() + 10)
    if not oracle.complete:
        raise RuntimeError("El oráculo no terminó: este ensayo no acredita el óptimo.")
    mask, route = min(
        oracle.routes.items(),
        key=lambda item: (-item[0].bit_count(), item[1].net_energy_kwh),
    )
    solution = assemble_solution(instance, [route])
    validation = validate_solution(instance, solution, enforce_movement_limit=False)
    if not validation.feasible:
        raise AssertionError(validation.violations)
    return {
        "oracle_complete": oracle.complete,
        "deliveries": mask.bit_count(),
        "net_energy_kwh": solution.net_energy_kwh,
        "duration_seconds": solution.routes[0].duration_seconds,
        "walk": [step.node_id for step in solution.routes[0].steps],
        "independently_validated": validation.feasible,
    }


def main() -> None:
    road = make_window_instance()
    compact, archive = build_service_graph(road, service_movements=4)
    selected = next(
        path for path in archive.paths
        if path.from_node_id == "base" and path.to_node_id == "customer"
    )
    road_result, compact_result = solve_tiny(road), solve_tiny(compact)
    assert road_result["deliveries"] == 1 and compact_result["deliveries"] == 0
    assert road_result["net_energy_kwh"] == 3
    assert road_result["duration_seconds"] == 960

    negative = road.model_copy(deep=True)
    negative.arcs[1].energy_kwh = -0.25
    try:
        build_service_graph(negative, service_movements=4)
    except ValueError as exc:
        negative_message = str(exc)
        assert "negativa" in negative_message
    else:
        raise AssertionError("Se esperaba el rechazo explícito de energías negativas.")

    hidden_deficit = replay((6, -5), initial=6)
    aggregate_final = 6 - hidden_deficit["nominal_energy_kwh"]
    assert aggregate_final == 5 and not hidden_deficit["feasible"]
    regen_first, descent_last = replay((-6, 4), 6), replay((4, -6), 6)
    assert regen_first["feasible"] and descent_last["feasible"]
    assert regen_first["nominal_energy_kwh"] == descent_last["nominal_energy_kwh"] == -2
    assert regen_first["battery_states_kwh"][-1] == 6
    assert descent_last["battery_states_kwh"][-1] == 8

    # Todas las secuencias de hasta 5 calles de este alfabeto y 19 SoC.
    # Una enumeración finita contrasta la fórmula, no reemplaza su demostración.
    profile_checks = 0
    for length in range(1, 6):
        for energies in product((-6.0, -2.0, 0.0, 2.0, 6.0), repeat=length):
            for initial in (1 + index * 0.5 for index in range(19)):
                expected = replay(energies, initial)
                feasible, final = profile(energies, initial)
                assert feasible == expected["feasible"], (energies, initial)
                assert isclose(final, expected["battery_states_kwh"][-1]), (energies, initial)
                profile_checks += 1

    # Minimizar energía + alpha * tiempo nunca selecciona B:
    # B <= A exige alpha <= 3/5; B <= C exige alpha >= 1.
    candidates = {"A": (5, 9), "B": (10, 6), "C": (15, 1)}
    constrained = min(
        (name for name, (time, _) in candidates.items() if time <= 10),
        key=lambda name: candidates[name][1],
    )
    assert constrained == "B"
    assert 3 / 5 < 1
    print(json.dumps({
        "negative_energy_guard": negative_message,
        "hidden_deficit": {
            **hidden_deficit,
            "misleading_aggregate_final_kwh": aggregate_final,
        },
        "saturation": {"regeneration_first": regen_first, "regeneration_last": descent_last},
        "time_window": {
            "selected_energy_path": selected.node_ids,
            "selected_path_seconds": 1200,
            "alternative_path_seconds": 600,
            "close_seconds": 900,
            "service_seconds": 60,
            "road": road_result,
            "compact": compact_result,
        },
        "fixed_path_profile": {"checked_states": profile_checks, "all_matched": True},
        "unsupported_pareto_path": {
            "candidates_time_energy": candidates,
            "deadline": 10,
            "optimal_feasible_path": constrained,
            "alpha_upper_bound_to_beat_A": 3 / 5,
            "alpha_lower_bound_to_beat_C": 1,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
