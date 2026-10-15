"""Enumeradores independientes para fixtures diminutas de rutas eléctricas.

No importa Pyomo ni traduce sus restricciones. Explora caminatas, niveles de
recarga y subconjuntos atendidos usando aritmética racional exacta. No pretende
resolver las instancias reales.
"""

from __future__ import annotations

from fractions import Fraction

from ev_routing.contracts import ProblemInstance


def integer_walk_oracle(instance: ProblemInstance) -> tuple[int, int]:
    """Resolver exactamente fixtures enteras, aunque el MILP permita carga continua.

    Fijar una caminata y cada rama de saturación produce un poliedro en las
    baterías de llegada/salida. Al eliminar q, sólo quedan diferencias
    b_salida >= b_llegada (o igualdad fuera de cargadores), transiciones
    b_siguiente = b_salida - e y cotas/fijaciones enteras. Esta matriz de
    diferencias es totalmente unimodular; hay un vértice óptimo entero para
    el objetivo lineal de energía. La unión finita de caminatas/ramas conserva
    al menos un óptimo entero. No se afirma que TODAS las cargas óptimas sean
    enteras, ni se redondea una instancia no entera para hacerla compatible.
    """
    params = instance.parameters
    raw_values = [
        params.battery_capacity_kwh,
        params.reserve_kwh,
        params.initial_energy_kwh,
        *(arc.energy_kwh for arc in instance.arcs),
    ]
    if not all(value == int(value) for value in raw_values):
        raise ValueError("el oráculo exige una fixture de energías enteras")
    served, energy = _exact_walk_oracle(instance, allow_charging=True)
    assert energy.denominator == 1
    return served, int(energy)


def no_charge_walk_oracle(instance: ProblemInstance) -> tuple[int, Fraction]:
    """Enumerar caminos con energías fraccionarias, sin decisiones de recarga.

    Rechaza estaciones habilitadas: ignorar una recarga posible cambiaría el
    problema. Fraction preserva exactamente los decimales de estas fixtures.
    """
    if any(instance.chargers_for(vehicle) for vehicle in instance.vehicle_ids):
        raise ValueError("el oráculo sin recarga exige F_k vacío para todos")
    return _exact_walk_oracle(instance, allow_charging=False)


def _exact_walk_oracle(
    instance: ProblemInstance, *, allow_charging: bool
) -> tuple[int, Fraction]:
    """Explorar estados físicos, sin usar variables ni restricciones de Pyomo.

    Se conserva el conjunto de clientes encontrados, no una decisión de entrega:
    en la versión base atender no consume energía, tiempo ni capacidad adicional.
    La unión entre vehículos da el máximo servicio posible para esas caminatas;
    cada cliente de esa unión puede asignarse a exactamente una de sus visitas.
    Esto preserva ambos óptimos, sin afirmar que pasar obligue a entregar.
    """
    params = instance.parameters
    capacity = Fraction(str(params.battery_capacity_kwh))
    reserve = Fraction(str(params.reserve_kwh))
    initial = Fraction(str(params.initial_energy_kwh))
    depot = instance.depot_id
    customers = set(instance.customer_ids)
    adjacency = {node.node_id: [] for node in instance.nodes}
    for arc in instance.arcs:
        adjacency[arc.from_node_id].append(
            (arc.to_node_id, Fraction(str(arc.energy_kwh)))
        )
    adjacency[depot].append((depot, Fraction(0)))
    fleet_options: dict[frozenset[str], Fraction] = {frozenset(): Fraction(0)}

    for vehicle in instance.vehicle_ids:
        chargers = set(instance.chargers_for(vehicle))
        # Estado de la caminata: nodo, batería, clientes encontrados.
        states: dict[tuple[str, Fraction, frozenset[str]], Fraction] = {
            (depot, initial, frozenset()): Fraction(0)
        }
        for _ in range(params.movement_limit):
            successors: dict[tuple[str, Fraction, frozenset[str]], Fraction] = {}
            for (node, battery, served), total in states.items():
                seen = served | ({node} if node in customers else set())
                if allow_charging and node in chargers:
                    # integer_walk_oracle ya comprobó la hipótesis de integralidad.
                    assert battery.denominator == capacity.denominator == 1
                    departures = map(Fraction, range(int(battery), int(capacity) + 1))
                else:
                    departures = [battery]
                for departure in departures:
                    for destination, demand in adjacency[node]:
                        arrival = min(capacity, departure - demand)
                        if arrival < reserve:
                            continue
                        next_state = (destination, arrival, frozenset(seen))
                        energy = total + departure - arrival
                        if next_state not in successors or energy < successors[next_state]:
                            successors[next_state] = energy
            states = successors
        route_options: dict[frozenset[str], Fraction] = {}
        for (node, _, served), energy in states.items():
            if node == depot and (served not in route_options or energy < route_options[served]):
                route_options[served] = energy

        combined: dict[frozenset[str], Fraction] = {}
        for previous, previous_energy in fleet_options.items():
            for current, current_energy in route_options.items():
                union = previous | current
                energy = previous_energy + current_energy
                if union not in combined or energy < combined[union]:
                    combined[union] = energy
        fleet_options = combined

    maximum = max(map(len, fleet_options))
    minimum_energy = min(
        energy for served, energy in fleet_options.items() if len(served) == maximum
    )
    return maximum, minimum_energy
