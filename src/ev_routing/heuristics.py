"""Elección rápida y certificada de H para la variante entre servicios.

La heurística solo construye un testigo; no demuestra que esa ruta sea óptima.
Si atiende todos los clientes con energía total U <= b_ini - reserva, cualquier
solución que mejore U puede hacerse sin recargar. La desigualdad triangular
permite quitar paradas sin entrega: existe un óptimo con H = |C| + 1.

Solo se aplica al modelo actual: caminos de energía no negativa, batería
homogénea, sin jornada, ventanas, paquetes ni obligación de usar toda la flota.
No modifica el modelo vial del PDF ni transforma regeneración en consumo cero.
"""

from __future__ import annotations

from math import isfinite
from time import perf_counter
from typing import Literal

import networkx as nx
import numpy as np
from pydantic import Field

from ev_routing.contracts import (
    Contract,
    ProblemInstance,
    RouteStep,
    Solution,
    VehicleRoute,
)
from ev_routing.operations import arc_energy, schedule_solution
from ev_routing.service_graph import REPRESENTATION
from ev_routing.validation import validate_solution


class HorizonAnalysis(Contract):
    status: Literal["certified_minimal", "certified_sufficient", "not_certified"] = "not_certified"
    recommended_horizon: int | None = None
    minimum_horizon: int | None = None
    structural_upper_bound: int | None = None
    reason: str = ""
    method: str = "networkx_greedy_multistart"
    movement_unit: str = "service_leg"
    metric_verified: bool = False
    usable_initial_energy_kwh: float
    tour: list[str] = Field(default_factory=list)
    tour_energy_kwh: float | None = None
    minimum_depot_shortcut_saving_kwh: float | None = None
    starts_tried: int = 0
    max_starts: int
    budget_seconds: float
    runtime_seconds: float = 0.0


class InitialSolution(Contract):
    """Archivo de arranque vinculado al snapshot exacto, incluido su H."""

    schema_version: Literal["1.0"] = "1.0"
    instance_sha256: str
    solution: Solution | None = None


def analyze_horizon(
    instance: ProblemInstance, *, max_starts: int = 32, time_limit_seconds: float = 0.5
) -> HorizonAnalysis:
    """Buscar un H pequeño con prueba; si no alcanza, informar sin adivinar.

    El presupuesto es blando: se comprueba entre verificaciones vectorizadas
    y entre recorridos de NetworkX. No hay búsqueda local, MILP, AWS ni lectura
    de resultados previos. Se detiene al encontrar un testigo suficiente.
    """
    if isinstance(max_starts, bool) or not isinstance(max_starts, int) or max_starts < 1:
        raise ValueError("max_starts debe ser un entero positivo")
    if not isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds debe ser finito y positivo")
    started = perf_counter()
    deadline = started + time_limit_seconds
    usable = instance.parameters.initial_energy_kwh - instance.parameters.reserve_kwh
    analysis = HorizonAnalysis(
        usable_initial_energy_kwh=usable, max_starts=max_starts,
        budget_seconds=time_limit_seconds,
    )

    def finish(reason: str) -> HorizonAnalysis:
        analysis.reason = reason
        analysis.runtime_seconds = perf_counter() - started
        return analysis

    if instance.provenance.get("representation", {}).get("kind") != REPRESENTATION:
        return finish("Solo se certifica H en la variante de caminos entre servicios.")
    if any(node.node_type == "junction" for node in instance.nodes):
        return finish("La instancia contiene intersecciones; H no cuenta solo servicios.")
    if any(arc.energy_kwh < 0 for arc in instance.arcs):
        return finish("No se puede aplicar esta prueba a energías negativas o regeneración.")
    ops = instance.operations
    if (
        ops.max_route_seconds is not None or ops.use_customer_time_windows
        or (
            ops.final_reserve_soc is not None
            and ops.final_reserve_soc * instance.parameters.battery_capacity_kwh
            > instance.parameters.reserve_kwh
        )
    ):
        return finish(
            "Jornada, ventanas o reserva final adicional invalidan la prueba actual de H. "
            "Elegir un H explícito para esta variante; no se afirma una cota estructural."
        )

    # Comprobar la propiedad usada por la prueba, sin confiar solo en una etiqueta
    # de procedencia. Incluir cargadores y pares inalcanzables: un atajo ausente
    # o más caro que pasar por un tercer servicio invalida la reducción.
    ids = {node.node_id: index for index, node in enumerate(instance.nodes)}
    energy = np.full((len(ids), len(ids)), np.inf)
    np.fill_diagonal(energy, 0.0)
    for arc in instance.arcs:
        energy[ids[arc.from_node_id], ids[arc.to_node_id]] = arc_energy(arc, ops)
    for middle in range(len(ids)):
        if perf_counter() >= deadline:
            return finish("Se agotó el presupuesto antes de verificar la matriz de energía.")
        via = energy[:, middle, None] + energy[middle, None, :]
        # Comparación conservadora sin ampliar tolerancias del problema.
        if np.any(energy > via):
            return finish("La matriz no cumple la desigualdad triangular dirigida.")
    analysis.metric_verified = True
    customers = sorted(instance.customer_ids)
    n = len(customers)
    compatible_count = max(len(instance.chargers_for(k)) for k in instance.vehicle_ids)
    # Entre dos entregas no hace falta repetir una estación compatible: quitar
    # ese ciclo y ajustar la carga en su primera visita no aumenta consumo.
    analysis.structural_upper_bound = (n + 1) * (compatible_count + 1)
    if n == 0:
        analysis.recommended_horizon = analysis.minimum_horizon = 1
        analysis.status = "certified_minimal"
        analysis.tour = [instance.depot_id, instance.depot_id]
        analysis.tour_energy_kwh = 0.0
        return finish("Sin clientes, dejar la flota inactiva es óptimo con H=1.")

    if compatible_count == 0:
        # Puede atenderse solo parte de la demanda. Sin recarga posible, quitar
        # visitas sin entrega conserva al menos un óptimo de ambos objetivos.
        analysis.recommended_horizon = n + 1
        analysis.status = "certified_sufficient"

    service_ids = [instance.depot_id, *customers]
    graph = nx.DiGraph()
    graph.add_nodes_from(service_ids)
    graph.add_weighted_edges_from(
        (a.from_node_id, a.to_node_id, arc_energy(a, ops))
        for a in instance.arcs if a.from_node_id in graph and a.to_node_id in graph
    )
    if len(graph.edges) != len(service_ids) * (len(service_ids) - 1):
        return finish(
            "Hay clientes sin conexión dirigida; no se construyó una ruta completa."
            if compatible_count else "Sin estaciones compatibles, H=|C|+1 basta incluso con clientes aislados."
        )
    for source in service_ids[:max_starts]:
        if perf_counter() >= deadline:
            break
        tour = nx.approximation.greedy_tsp(graph, source=source, weight="weight")
        value = sum(graph[i][j]["weight"] for i, j in zip(tour, tour[1:]))
        analysis.starts_tried += 1
        if analysis.tour_energy_kwh is None or value < analysis.tour_energy_kwh:
            # Rotar un ciclo no cambia su costo ni su factibilidad sin recarga.
            cycle = tour[:-1]
            index = cycle.index(instance.depot_id)
            analysis.tour = cycle[index:] + cycle[:index] + [instance.depot_id]
            # Sumar en el orden que usará el validador, también cerca de reserva.
            analysis.tour_energy_kwh = sum(
                graph[i][j]["weight"] for i, j in zip(analysis.tour, analysis.tour[1:])
            )
        if analysis.tour_energy_kwh <= usable:
            analysis.recommended_horizon = n + 1
            analysis.status = "certified_sufficient"
            if n > 1:
                base = ids[instance.depot_id]
                analysis.minimum_depot_shortcut_saving_kwh = min(
                    float(energy[ids[i], base] + energy[base, ids[j]] - energy[ids[i], ids[j]])
                    for i in customers for j in customers if i != j
                )
            # Si unir dos rutas siempre ahorra energía, un óptimo utiliza una
            # sola ruta con entregas. Su consumo conjunto cabe en la batería
            # inicial gracias a U <= usable. Por tanto también H >= |C| + 1.
            if (
                instance.parameters.vehicle_count == 1 or n == 1
                or analysis.minimum_depot_shortcut_saving_kwh > 0
            ):
                analysis.minimum_horizon = n + 1
                analysis.status = "certified_minimal"
            return finish(
                "Ruta completa con U <= batería inicial menos reserva; existe un óptimo sin "
                "recargas ni paradas sin entrega. El certificado es de H, no de la energía de la ruta."
            )
    if compatible_count == 0:
        return finish("Sin estaciones compatibles, H=|C|+1 basta aunque el testigo completo no sea factible.")
    return finish(
        "La búsqueda acotada no obtuvo U <= batería inicial menos reserva. No se certifica un H "
        "pequeño; la cota estructural se informa sin lanzar automáticamente un MILP grande."
    )


def build_initial_solution(instance: ProblemInstance, tour: list[str]) -> Solution | None:
    """Convertir un testigo sin recarga a H+1 posiciones y verificarlo."""
    h, depot = instance.parameters.movement_limit, instance.depot_id
    if (
        len(tour) < 2 or len(tour) - 1 > h or tour[0] != depot or tour[-1] != depot
        or sorted(tour[1:-1]) != sorted(instance.customer_ids)
    ):
        return None
    energies = {
        (a.from_node_id, a.to_node_id): arc_energy(a, instance.operations) for a in instance.arcs
    }
    energies[depot, depot] = 0.0
    routes = []
    for vehicle in instance.vehicle_ids:
        sequence = tour if vehicle == instance.vehicle_ids[0] else [depot, depot]
        sequence = [*sequence, *([depot] * (h + 1 - len(sequence)))]
        battery = instance.parameters.initial_energy_kwh
        steps = []
        total = 0.0
        for origin, target in zip(sequence, sequence[1:]):
            energy = energies.get((origin, target))
            if energy is None or energy < 0:
                return None
            steps.append(RouteStep(
                position=len(steps), node_id=origin, next_node_id=target,
                battery_arrival_kwh=battery, battery_departure_kwh=battery,
                delivered_visit_ids=[origin] if origin != depot else [],
                predicted_arc_energy_kwh=energy, effective_arc_energy_kwh=energy,
            ))
            battery -= energy
            total += energy
        steps.append(RouteStep(
            position=h, node_id=depot, battery_arrival_kwh=battery, battery_departure_kwh=battery,
        ))
        routes.append(VehicleRoute(vehicle_id=vehicle, steps=steps, net_energy_kwh=total))
    solution = Solution(
        routes=routes, served_visit_ids=instance.customer_ids, unserved_visit_ids=[],
        net_energy_kwh=sum(route.net_energy_kwh for route in routes),
    )
    solution = schedule_solution(instance, solution)
    return solution if validate_solution(instance, solution).feasible else None


def build_greedy_start(instance: ProblemInstance, *, time_limit_seconds: float = 0.5) -> Solution | None:
    """Incumbente sin recargas, posiblemente parcial; nunca certifica H.

    Insertar al final del recorrido del vehículo con menor incremento de energía,
    comprobando retorno, batería, ventanas y jornada tras cada propuesta.
    """
    started = perf_counter()
    h, depot = instance.parameters.movement_limit, instance.depot_id
    energies = {
        (a.from_node_id, a.to_node_id): arc_energy(a, instance.operations) for a in instance.arcs
    }
    energies[depot, depot] = 0.0
    if any(value < 0 for value in energies.values()):
        return None

    def candidate(sequences):
        routes = []
        for vehicle, sequence in zip(instance.vehicle_ids, sequences):
            padded = sequence + [depot] * (h + 1 - len(sequence))
            battery, steps, total = instance.parameters.initial_energy_kwh, [], 0.0
            for origin, target in zip(padded, padded[1:]):
                energy = energies.get((origin, target))
                if energy is None:
                    return None
                steps.append(RouteStep(
                    position=len(steps), node_id=origin, next_node_id=target,
                    battery_arrival_kwh=battery, battery_departure_kwh=battery,
                    delivered_visit_ids=[origin] if origin in instance.customer_ids else [],
                    predicted_arc_energy_kwh=energy, effective_arc_energy_kwh=energy,
                ))
                battery -= energy
                total += energy
            steps.append(RouteStep(
                position=h, node_id=depot, battery_arrival_kwh=battery,
                battery_departure_kwh=battery,
            ))
            routes.append(VehicleRoute(vehicle_id=vehicle, steps=steps, net_energy_kwh=total))
        served = [i for sequence in sequences for i in sequence if i != depot]
        solution = schedule_solution(instance, Solution(
            routes=routes, served_visit_ids=served,
            unserved_visit_ids=[i for i in instance.customer_ids if i not in served],
            net_energy_kwh=sum(route.net_energy_kwh for route in routes),
        ))
        return solution if validate_solution(instance, solution).feasible else None

    sequences = [[depot, depot] for _ in instance.vehicle_ids]
    incumbent = candidate(sequences)
    if incumbent is None:
        return None
    pending = sorted(instance.customer_ids)
    while pending and perf_counter() - started < time_limit_seconds:
        choices = []
        for k, sequence in enumerate(sequences):
            if len(sequence) >= h + 1:
                continue
            last = sequence[-2]
            for customer in pending:
                if (last, customer) in energies and (customer, depot) in energies:
                    choices.append((
                        energies[last, customer] + energies[customer, depot] - energies[last, depot],
                        k, customer,
                    ))
        for _, k, customer in sorted(choices):
            if perf_counter() - started >= time_limit_seconds:
                return incumbent
            proposed = [list(sequence) for sequence in sequences]
            proposed[k].insert(-1, customer)
            result = candidate(proposed)
            if result is not None:
                incumbent, sequences = result, proposed
                pending.remove(customer)
                break
        else:
            break
    return incumbent
