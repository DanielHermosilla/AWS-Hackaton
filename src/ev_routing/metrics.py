"""KPIs auditables; los impactos sin referencia se dejan explícitamente vacíos."""

from __future__ import annotations

from typing import Any

from ev_routing.contracts import ProblemInstance, Solution, ValidationReport


def compute_metrics(
    instance: ProblemInstance,
    solution: Solution | None,
    validation: ValidationReport | None,
) -> dict[str, Any]:
    """Contar entregas factibles y separar batería, red eléctrica e impactos."""
    valid = solution is not None and validation is not None and validation.feasible
    result: dict[str, Any] = {
        "feasible": bool(valid),
        "total_deliveries": len(instance.customer_ids),
        "served_deliveries": None,
        "net_battery_energy_kwh": None,
        "charged_to_battery_kwh": None,
        "distance_km": None,
        "charging_stops": None,
        "minimum_battery_kwh": None,
        "grid_energy_kwh": None,
        "operational_duration_seconds": None,
        "time_saved_seconds": None,
        "co2e_saved_kg": None,
        "unavailable_reasons": {
            "grid_energy_kwh": "El PDF no modela pérdidas ni energía del enchufe.",
            "operational_duration_seconds": "H cuenta movimientos; no modela tiempo.",
            "time_saved_seconds": "No se proporcionó una referencia comparable.",
            "co2e_saved_kg": "Faltan referencia y factores de emisión documentados.",
        },
    }
    if not valid:
        return result
    assert solution is not None
    distances = {(a.from_node_id, a.to_node_id): a.distance_m for a in instance.arcs}
    distances[instance.depot_id, instance.depot_id] = 0.0
    steps = [step for route in solution.routes for step in route.steps]
    result.update(
        served_deliveries=len(solution.served_visit_ids),
        net_battery_energy_kwh=solution.net_energy_kwh,
        charged_to_battery_kwh=sum(step.charged_to_battery_kwh for step in steps),
        distance_km=sum(
            distances[step.node_id, step.next_node_id]
            for step in steps
            if step.next_node_id is not None
        )
        / 1000,
        charging_stops=sum(step.charged_to_battery_kwh > 1e-5 for step in steps),
        minimum_battery_kwh=min(step.battery_arrival_kwh for step in steps),
    )
    return result
