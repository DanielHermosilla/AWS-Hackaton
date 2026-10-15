"""Coeficientes y calendario de las extensiones, sin depender de Pyomo.

Los arcos conservan su energía nominal. El margen se aplica exactamente una vez,
tanto al modelo como a la expansión vial y al certificado.
"""

from __future__ import annotations

from ev_routing.contracts import Arc, Operations, ProblemInstance, Solution


def arc_energy(arc: Arc, options: Operations) -> float:
    """Incrementar descargas; nunca aumentar el crédito de regeneración."""
    return arc.energy_kwh + options.energy_margin_fraction * max(arc.energy_kwh, 0.0)


def travel_seconds(arc: Arc, options: Operations) -> float:
    if arc.travel_time_seconds is not None:
        return arc.travel_time_seconds
    if options.assumed_speed_kph is None:
        raise ValueError("Falta tiempo de viaje y assumed_speed_kph")
    return 3.6 * arc.distance_m / options.assumed_speed_kph


def charge_seconds(charge_kwh: float, station: str, options: Operations) -> float:
    if not options.include_charging_time or charge_kwh <= 0:
        return 0.0
    power = options.charging_power(station)
    if power is None:
        raise ValueError(f"Falta potencia efectiva para {station}")
    return 3600 * charge_kwh / (options.charging_efficiency * power)


def schedule_solution(instance: ProblemInstance, solution: Solution) -> Solution:
    """Calendario más temprano para rutas fijas con ventanas de fin de servicio.

    No repara rutas ni certifica factibilidad: el validador reproduce los
    intervalos y decide si satisfacen las ventanas/jornada. No hay colas,
    horarios de cargadores ni tráfico dependiente de la hora.
    """
    if not instance.operations.timing_enabled:
        return solution
    result = solution.model_copy(deep=True)
    arcs = {(a.from_node_id, a.to_node_id): a for a in instance.arcs}
    ops = instance.operations
    for route in result.routes:
        arrival = 0.0
        for step in route.steps:
            service = sum(ops.service_duration(i) for i in step.delivered_visit_ids)
            start = arrival
            if ops.use_customer_time_windows:
                for customer in step.delivered_visit_ids:
                    window = ops.customer_time_windows.get(customer)
                    if window is not None:
                        start = max(start, window.open_seconds)
            charge = charge_seconds(step.charged_to_battery_kwh, step.node_id, ops)
            pair = (step.node_id, step.next_node_id)
            travel = (
                travel_seconds(arcs[pair], ops)
                if step.next_node_id is not None and pair != (instance.depot_id, instance.depot_id)
                else 0.0
            )
            step.arrival_seconds = arrival
            step.service_start_seconds = start
            step.service_duration_seconds = service
            step.charging_duration_seconds = charge
            step.departure_seconds = start + service + charge
            step.travel_time_seconds = travel if step.next_node_id is not None else None
            arrival = step.departure_seconds + travel
        route.duration_seconds = route.steps[-1].arrival_seconds
    return result
