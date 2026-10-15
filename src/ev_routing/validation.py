"""Comprobación física de un resultado, independiente de Pyomo y del solver.

El checker vuelve a recorrer los arcos originales. No confía en el objetivo,
la saturación auxiliar gamma ni el estado de terminación reportados por Pyomo.
"""

from __future__ import annotations

from math import isclose, isfinite

from ev_routing.contracts import ProblemInstance, Solution, ValidationReport


def validate_solution(
    instance: ProblemInstance, solution: Solution, *, tolerance: float = 1e-5
) -> ValidationReport:
    """Reproducir (1)–(15) del PDF desde las rutas y las energías originales.

    ``tolerance`` solo absorbe ruido numérico de resolución. No se usa como
    reserva adicional, tolerancia de optimalidad ni permiso para omitir tramos.
    Se devuelven todas las violaciones detectadas para facilitar diagnósticos.
    """
    if not isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance debe ser finita y positiva")
    checks = dict.fromkeys(
        ["fleet", "topology", "deliveries", "battery", "charging", "energy"], True
    )
    violations: list[str] = []

    def fail(category: str, message: str) -> None:
        checks[category] = False
        violations.append(message)

    def equal(left: float, right: float) -> bool:
        return isclose(left, right, rel_tol=1e-8, abs_tol=tolerance)

    params = instance.parameters
    capacity = params.battery_capacity_kwh
    reserve = params.reserve_kwh
    initial = params.initial_energy_kwh
    depot = instance.depot_id
    node_ids = {node.node_id for node in instance.nodes}
    customers = set(instance.customer_ids)
    arc_energy = {(a.from_node_id, a.to_node_id): a.energy_kwh for a in instance.arcs}
    arc_energy[depot, depot] = 0.0  # Arco ficticio de permanencia del PDF.
    seen_deliveries: list[str] = []
    effective_total = 0.0
    vehicle_ids = [route.vehicle_id for route in solution.routes]
    if sorted(vehicle_ids) != sorted(instance.vehicle_ids):
        fail("fleet", "La flota debe contener una ruta por vehículo, sin duplicados")

    for route in solution.routes:
        label = route.vehicle_id
        if label not in instance.vehicle_ids:
            fail("fleet", f"Vehículo desconocido: {label}")
            continue
        steps = route.steps
        compatible = set(instance.chargers_for(label))
        if len(steps) != params.movement_limit + 1:
            fail("topology", f"{label}: se requieren H+1 posiciones")
        if not steps:
            fail("topology", f"{label}: ruta vacía")
            continue
        if steps[0].node_id != depot or steps[-1].node_id != depot:
            fail("topology", f"{label}: salida y retorno deben ser el depósito")
        if not equal(steps[0].battery_arrival_kwh, initial):
            fail("battery", f"{label}: SoC inicial incorrecto")

        route_energy = 0.0
        route_charge = 0.0
        for index, step in enumerate(steps):
            prefix = f"{label}, posición {index}"
            if step.position != index:
                fail("topology", f"{prefix}: índice de posición incorrecto")
            if step.node_id not in node_ids:
                fail("topology", f"{prefix}: nodo desconocido {step.node_id}")
            arrival = step.battery_arrival_kwh
            departure = step.battery_departure_kwh
            charge = step.charged_to_battery_kwh
            for state in (arrival, departure):
                if not reserve - tolerance <= state <= capacity + tolerance:
                    fail("battery", f"{prefix}: batería fuera de capacidad/reserva")
            if charge < -tolerance:
                fail("charging", f"{prefix}: recarga negativa")
            if charge > tolerance and step.node_id not in compatible:
                fail("charging", f"{prefix}: recarga en nodo no compatible")
            if index == 0 and abs(charge) > tolerance:
                fail("charging", f"{prefix}: no se permite recarga inicial")
            if not equal(departure, arrival + charge):
                fail("charging", f"{prefix}: balance de recarga incorrecto")
            route_charge += charge

            for customer in step.delivered_visit_ids:
                if customer not in customers or customer != step.node_id:
                    fail("deliveries", f"{prefix}: entrega fuera de su cliente {customer}")
                if index == len(steps) - 1:
                    fail("deliveries", f"{prefix}: entrega en posición terminal")
                seen_deliveries.append(customer)

            if index == len(steps) - 1:
                # q y arcos solo existen en R^-; no inventar una salida terminal.
                if abs(charge) > tolerance or step.next_node_id is not None:
                    fail("topology", f"{prefix}: posición terminal con salida/recarga")
                if step.predicted_arc_energy_kwh is not None:
                    fail("energy", f"{prefix}: energía de arco en posición terminal")
                if step.effective_arc_energy_kwh is not None:
                    fail("energy", f"{prefix}: consumo en posición terminal")
                continue

            following = steps[index + 1]
            if step.next_node_id != following.node_id:
                fail("topology", f"{prefix}: next_node_id no coincide con la ruta")
            pair = (step.node_id, following.node_id)
            if pair not in arc_energy:
                fail("topology", f"{prefix}: arco no permitido {pair}")
                continue
            predicted = arc_energy[pair]
            # La recuperación que excede B se pierde: nunca aumenta la batería
            # sobre su capacidad ni reduce artificialmente el consumo informado.
            expected_arrival = min(capacity, departure - predicted)
            if not equal(following.battery_arrival_kwh, expected_arrival):
                fail("battery", f"{prefix}: transición física de batería incorrecta")
            if expected_arrival < reserve - tolerance:
                fail("battery", f"{prefix}: el tramo agota la reserva")
            if step.predicted_arc_energy_kwh is None or not equal(
                step.predicted_arc_energy_kwh, predicted
            ):
                fail("energy", f"{prefix}: energía predicha no coincide con el arco")
            effective = departure - following.battery_arrival_kwh
            if step.effective_arc_energy_kwh is None or not equal(
                step.effective_arc_energy_kwh, effective
            ):
                fail("energy", f"{prefix}: consumo efectivo reportado incorrecto")
            route_energy += effective

        if not equal(route.net_energy_kwh, route_energy):
            fail("energy", f"{label}: energía de ruta incorrecta")
        if not equal(route_energy, initial + route_charge - steps[-1].battery_arrival_kwh):
            fail("energy", f"{label}: balance energético global incorrecto")
        effective_total += route_energy

    if len(seen_deliveries) != len(set(seen_deliveries)):
        fail("deliveries", "Una entrega se contabilizó más de una vez")
    if sorted(solution.served_visit_ids) != sorted(seen_deliveries):
        fail("deliveries", "served_visit_ids no coincide con las entregas realizadas")
    if sorted(solution.unserved_visit_ids) != sorted(customers - set(seen_deliveries)):
        fail("deliveries", "unserved_visit_ids no coincide con los clientes pendientes")
    if not equal(solution.net_energy_kwh, effective_total):
        fail("energy", "El consumo total reportado no coincide con las rutas")
    return ValidationReport(feasible=not violations, violations=violations, checks=checks)
