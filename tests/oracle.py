"""Enumerador independiente para fixtures diminutas con energías enteras.

No importa Pyomo ni traduce sus restricciones. Explora caminatas, niveles de
recarga y subconjuntos atendidos; no pretende resolver las instancias reales.
"""

from __future__ import annotations

from ev_routing.contracts import ProblemInstance


def integer_walk_oracle(instance: ProblemInstance) -> tuple[int, int]:
    """Devolver (máximo de entregas, mínimo de kWh) por enumeración exhaustiva.

    En estas fixtures B, reserva, energía inicial y consumos son enteros. Para
    una caminata fijada, las funciones de batería son lineales por tramos con
    quiebres enteros; existe una carga óptima en los niveles enteros explorados.
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
    capacity = int(params.battery_capacity_kwh)
    reserve = int(params.reserve_kwh)
    initial = int(params.initial_energy_kwh)
    depot = instance.depot_id
    customers = set(instance.customer_ids)
    adjacency = {node.node_id: [] for node in instance.nodes}
    for arc in instance.arcs:
        adjacency[arc.from_node_id].append((arc.to_node_id, int(arc.energy_kwh)))
    adjacency[depot].append((depot, 0))
    fleet_options: dict[frozenset[str], int] = {frozenset(): 0}

    for vehicle in instance.vehicle_ids:
        chargers = set(instance.chargers_for(vehicle))
        # Estado de la caminata: nodo, batería, clientes encontrados.
        states: dict[tuple[str, int, frozenset[str]], int] = {
            (depot, initial, frozenset()): 0
        }
        for _ in range(params.movement_limit):
            successors: dict[tuple[str, int, frozenset[str]], int] = {}
            for (node, battery, served), total in states.items():
                seen = served | ({node} if node in customers else set())
                departures = range(battery, capacity + 1) if node in chargers else [battery]
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
        route_options: dict[frozenset[str], int] = {}
        for (node, _, served), energy in states.items():
            if node == depot and (served not in route_options or energy < route_options[served]):
                route_options[served] = energy

        combined: dict[frozenset[str], int] = {}
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
