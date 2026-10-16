"""Redes eléctricas sintéticas reproducibles con testigo separado del solver.

El testigo acredita factibilidad de todas las entregas; no optimalidad energética.
Las ventanas se construyen sobre su calendario y se comprueban después con el
validador independiente. Ninguna ruta ni orden del testigo entra a la instancia.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from random import Random

from ev_routing.contracts import (
    Arc,
    ModelParameters,
    Node,
    Operations,
    ProblemInstance,
    RouteStep,
    Solution,
    TimeWindow,
    VehicleRoute,
)
from ev_routing.operations import schedule_solution
from ev_routing.validation import validate_solution

GENERATOR_VERSION = 2
FAMILIES = ("loose", "clustered", "crossed", "dispatch")


@dataclass
class SyntheticCase:
    road: ProblemInstance
    witness: Solution
    description: dict


def _witness(instance: ProblemInstance, walks: list[list[str]]) -> Solution:
    """Elegir cargas parciales para recorridos conocidos, sin resolver un MILP."""
    arcs = {(a.from_node_id, a.to_node_id): a for a in instance.arcs}
    customers, chargers = set(instance.customer_ids), set(instance.charger_ids)
    params, routes, served = instance.parameters, [], set()
    for vehicle, walk in zip(instance.vehicle_ids, walks, strict=True):
        battery, steps, energy = params.initial_energy_kwh, [], 0.0
        for position, node in enumerate(walk):
            charge = 0.0
            if node in chargers:
                required = 0.0
                for a, b in zip(walk[position:], walk[position + 1:]):
                    required += arcs[a, b].energy_kwh
                    if b in chargers:
                        break
                charge = max(0.0, params.reserve_kwh + required + .2 - battery)
                if battery + charge > params.battery_capacity_kwh + 1e-9:
                    raise ValueError("El generador produjo un bloque que no cabe en la batería.")
            delivered = [node] if node in customers and node not in served else []
            served.update(delivered)
            following = walk[position + 1] if position + 1 < len(walk) else None
            arc = arcs[node, following] if following else None
            steps.append(RouteStep(
                position=position, node_id=node, battery_arrival_kwh=battery,
                charged_to_battery_kwh=charge, battery_departure_kwh=battery + charge,
                delivered_visit_ids=delivered, next_node_id=following,
                predicted_arc_energy_kwh=arc.energy_kwh if arc else None,
                effective_arc_energy_kwh=arc.energy_kwh if arc else None,
            ))
            if arc:
                battery += charge - arc.energy_kwh
                energy += arc.energy_kwh
        routes.append(VehicleRoute(vehicle_id=vehicle, steps=steps, net_energy_kwh=energy))
    return schedule_solution(instance, Solution(
        routes=routes, served_visit_ids=sorted(served),
        unserved_visit_ids=sorted(customers - served),
        net_energy_kwh=sum(r.net_energy_kwh for r in routes),
    ))


def make_case(customers: int, seed: int, family: str = "clustered") -> SyntheticCase:
    if customers < 4 or customers > 200 or seed < 0 or family not in FAMILIES:
        raise ValueError("Use 4..200 clientes, semilla no negativa y una familia admitida.")
    rng = Random(seed)
    depot = "depot"
    nodes = [Node(node_id=depot, node_type="base")]
    arcs, coordinates, corridors = [], {depot: (0.0, 0.0)}, {}
    centers = [(-8.0, 7.0), (8.0, 7.0), (-8.0, -7.0), (8.0, -7.0)]
    if family == "dispatch":
        # Caso dirigido a planificación global: cuatro sectores separados por
        # un corredor caro, dos oleadas temporales y potencias heterogéneas.
        # No es demanda real ni un test representativo de todas las instancias.
        stretch = rng.uniform(9.0, 11.0)
        centers = [(-stretch, 3), (stretch, 3), (-stretch, -3), (stretch, -3)]
    ids = [f"customer_{i:03d}" for i in range(customers)]
    rng.shuffle(ids)  # Los IDs no codifican el orden testigo ni las zonas.
    groups = [ids[z::4] for z in range(4)]
    stations = [[f"station_{z}_{i}" for i in range(2)] for z in range(4)]
    powers = {}
    for zone, center in enumerate(centers):
        for index, station in enumerate(stations[zone]):
            coordinates[station] = (center[0] + index * .8, center[1])
            nodes.append(Node(node_id=station, node_type="charger", connector_types=["CHAdeMO"]))
            powers[station] = 12.0 if index else 24.0
            if family == "dispatch":
                powers[station] = 7.0 if index else 36.0
        for customer in groups[zone]:
            coordinates[customer] = (center[0] + rng.uniform(-1, 1),
                                     center[1] + rng.uniform(-1, 1))
            nodes.append(Node(node_id=customer, node_type="visit"))
        members = stations[zone] + groups[zone]
        for a in members:
            for b in members:
                if a == b:
                    continue
                length = hypot(coordinates[a][0] - coordinates[b][0],
                               coordinates[a][1] - coordinates[b][1])
                # Todos los consumos son positivos y propios de cada arco.
                arcs.append(Arc(
                    from_node_id=a, to_node_id=b, distance_m=length * 1000,
                    energy_kwh=.08 + length * rng.uniform(.11, .19),
                    travel_time_seconds=25 + length * rng.uniform(80, 120),
                ))
    gates = [depot, *(pair[0] for pair in stations)]
    for a in gates:
        for b in gates:
            if a == b:
                continue
            length = hypot(coordinates[a][0] - coordinates[b][0],
                           coordinates[a][1] - coordinates[b][1])
            for fast in (False, True):
                junction = f"junction_{len(corridors):03d}"
                nodes.append(Node(node_id=junction, node_type="junction"))
                energy = length * (.66 if fast else .60)
                seconds = length * (35 if fast else 65)
                for u, v in [(a, junction), (junction, b)]:
                    arcs.append(Arc(
                        from_node_id=u, to_node_id=v, distance_m=length * 500,
                        energy_kwh=energy / 2, travel_time_seconds=seconds / 2,
                    ))
                corridors[a, b, fast] = junction
    parameters = ModelParameters(vehicle_count=2, battery_capacity_kwh=24,
                                 reserve_kwh=2.4, initial_soc=.6)
    operations = Operations(service_seconds=45, include_charging_time=True,
                            charging_power_kw_by_station=powers)
    road = ProblemInstance(
        name=f"synthetic-{family}-n{customers}-seed{seed}", nodes=nodes, arcs=arcs,
        parameters=parameters, operations=operations,
        provenance={
            "source": "synthetic", "generator_version": GENERATOR_VERSION,
            "assumptions": [
                "Grafo, tiempos, consumos por calle y potencias sintéticos; no son mediciones.",
                "Dos vehículos homogéneos; sin colas, ocupación de estaciones ni paquetes.",
            ],
        },
    )
    walks = []
    for zones in (((0, 2), (1, 3)) if family == "dispatch" else ((0, 1), (2, 3))):
        walk, current = [depot], depot
        visits = [(z, groups[z]) for z in zones]
        if family == "crossed":
            visits = [(z, groups[z][part::2]) for part in (0, 1) for z in zones]
        for zone, order in visits:
            if not order:
                continue
            gate, exit_station = stations[zone]
            if current != gate:
                walk += [corridors[current, gate, True], gate]
            # Un orden geométrico sencillo, no una solución optimizada.
            order = sorted(order, key=lambda i: coordinates[i][0])
            walk += [*order, exit_station, gate]
            current = gate
        walk += [corridors[current, depot, True], depot]
        walks.append(walk)
    witness = _witness(road, walks)
    horizon = max(r.duration_seconds for r in witness.routes) * 1.3 + 600
    windows = {}
    for route in witness.routes:
        for step in route.steps:
            for customer in step.delivered_visit_ids:
                tight = family != "loose" and rng.random() < (
                    .75 if family == "dispatch" else .5 if family == "crossed" else .3
                )
                slack = rng.uniform(240, 480) if tight else horizon
                windows[customer] = TimeWindow(
                    open_seconds=max(0, step.service_start_seconds - slack),
                    close_seconds=min(horizon, step.departure_seconds + slack),
                )
    road.operations = Operations(
        **{**operations.model_dump(), "max_route_seconds": horizon,
           "use_customer_time_windows": True, "customer_time_windows": windows},
    )
    # Ordenar y barajar servicios/arcos evita exponer el orden de construcción.
    rng.shuffle(road.nodes)
    rng.shuffle(road.arcs)
    road = ProblemInstance.model_validate(road.model_dump())
    witness = schedule_solution(road, witness)
    report = validate_solution(road, witness, enforce_movement_limit=False)
    if not report.feasible or len(witness.served_visit_ids) != customers:
        raise ValueError(f"Testigo sintético inválido: {report.violations}")
    return SyntheticCase(
        road, witness,
        {"family": family, "customers": customers, "instance_seed": seed,
         "generator_version": GENERATOR_VERSION, "vehicles": 2, "chargers": 8,
         "road_nodes": len(road.nodes), "road_arcs": len(road.arcs),
         "witness_feasible": True, "witness_deliveries": customers,
         "witness_charging_stops": sum(s.charged_to_battery_kwh > 1e-8
                                       for r in witness.routes for s in r.steps),
         "witness_energy_optimality_proven": False,
         "witness_given_to_solver_or_llm": False},
    )
