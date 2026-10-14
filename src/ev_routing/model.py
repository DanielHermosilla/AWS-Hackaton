"""Traducción directa de las ecuaciones (1)–(16) de ``modelamiento.pdf``.

El índice de posición cuenta tramos viales; no representa tiempo. El módulo
construye y lee el modelo, pero no elige un solver ni certifica una solución.
"""

from __future__ import annotations

from math import isfinite
from numbers import Integral

import pyomo.environ as pyo

from ev_routing.contracts import ProblemInstance, RouteStep, Solution, VehicleRoute


def build_model(instance: ProblemInstance) -> pyo.ConcreteModel:
    """Construir la fase de entregas del MILP sin recortar la red recibida."""
    parameters = instance.parameters
    depot = instance.depot_id
    horizon = parameters.movement_limit
    arc_energy = {
        (arc.from_node_id, arc.to_node_id): arc.energy_kwh for arc in instance.arcs
    }
    # El único arco añadido es la permanencia artificial en el depósito.
    arc_energy[depot, depot] = 0.0
    outgoing = {node.node_id: [] for node in instance.nodes}
    incoming = {node.node_id: [] for node in instance.nodes}
    for origin, destination in arc_energy:
        outgoing[origin].append(destination)
        incoming[destination].append(origin)

    model = pyo.ConcreteModel(name=instance.name)
    model.depot_id = depot
    # Conjuntos del PDF: nodos, arcos, clientes, estaciones y vehículos.
    model.V = pyo.Set(initialize=[node.node_id for node in instance.nodes], ordered=True)
    model.A = pyo.Set(dimen=2, initialize=list(arc_energy), ordered=True)
    model.C = pyo.Set(initialize=instance.customer_ids, within=model.V, ordered=True)
    model.F = pyo.Set(initialize=instance.charger_ids, within=model.V, ordered=True)
    model.K = pyo.Set(initialize=instance.vehicle_ids, ordered=True)
    # R incluye la llegada terminal; R_moves contiene las posiciones con salida.
    model.R = pyo.RangeSet(0, horizon)
    model.R_moves = pyo.RangeSet(0, horizon - 1)
    model.F_compatible = pyo.Set(
        model.K,
        within=model.F,
        initialize={vehicle: instance.chargers_for(vehicle) for vehicle in model.K},
        ordered=True,
    )

    # Parámetros de energía en kWh y límite de movimientos, sin jornada añadida.
    model.H = pyo.Param(initialize=horizon, within=pyo.PositiveIntegers)
    model.B = pyo.Param(
        initialize=parameters.battery_capacity_kwh, within=pyo.PositiveReals
    )
    model.reserve = pyo.Param(initialize=parameters.reserve_kwh, within=pyo.PositiveReals)
    model.initial_energy = pyo.Param(
        initialize=parameters.initial_energy_kwh, within=pyo.PositiveReals
    )
    model.e = pyo.Param(model.A, initialize=arc_energy, within=pyo.Reals)
    model.M = pyo.Param(
        initialize=parameters.battery_capacity_kwh + max(map(abs, arc_energy.values())),
        within=pyo.PositiveReals,
    )
    battery_bounds = (parameters.reserve_kwh, parameters.battery_capacity_kwh)

    # Dominios del PDF: entregar, ocupar un nodo, recorrer un arco y prestar servicio.
    model.y = pyo.Var(model.C, domain=pyo.Binary)
    model.z = pyo.Var(model.V, model.K, model.R, domain=pyo.Binary)
    model.x = pyo.Var(model.A, model.K, model.R_moves, domain=pyo.Binary)
    model.a = pyo.Var(model.C, model.K, model.R_moves, domain=pyo.Binary)
    # q incorpora energía a batería; b y b_departure respetan reserva y capacidad.
    model.q = pyo.Var(model.K, model.R_moves, domain=pyo.NonNegativeReals)
    model.b = pyo.Var(model.K, model.R, domain=pyo.Reals, bounds=battery_bounds)
    model.b_departure = pyo.Var(
        model.K, model.R_moves, domain=pyo.Reals, bounds=battery_bounds
    )
    # u puede superar B; E y E_total admiten regeneración efectiva negativa.
    model.u = pyo.Var(model.K, model.R_moves, domain=pyo.Reals)
    model.gamma = pyo.Var(model.K, model.R_moves, domain=pyo.Binary)
    model.E = pyo.Var(model.K, model.R_moves, domain=pyo.Reals)
    model.E_total = pyo.Var(domain=pyo.Reals)

    # (1) Cada vehículo ocupa exactamente un nodo en cada posición.
    model.eq01_location = pyo.Constraint(
        model.K, model.R, rule=lambda m, k, r: sum(m.z[i, k, r] for i in m.V) == 1
    )
    # (2) Salida y llegada final en el depósito; no se prohíben retornos intermedios.
    model.eq02_start = pyo.Constraint(model.K, rule=lambda m, k: m.z[depot, k, 0] == 1)
    model.eq02_return = pyo.Constraint(
        model.K, rule=lambda m, k: m.z[depot, k, horizon] == 1
    )
    # (3) El arco elegido sale del nodo ocupado, aun si éste no tiene salidas.
    model.eq03_departure = pyo.Constraint(
        model.V,
        model.K,
        model.R_moves,
        rule=lambda m, i, k, r: sum(m.x[i, j, k, r] for j in outgoing[i]) == m.z[i, k, r],
    )
    # (4) El mismo arco llega al nodo ocupado en la posición siguiente.
    model.eq04_arrival = pyo.Constraint(
        model.V,
        model.K,
        model.R_moves,
        rule=lambda m, j, k, r: sum(m.x[i, j, k, r] for i in incoming[j])
        == m.z[j, k, r + 1],
    )
    # (5) Estar en un cliente permite entregar, pero no obliga a hacerlo.
    model.eq05_service_location = pyo.Constraint(
        model.C,
        model.K,
        model.R_moves,
        rule=lambda m, i, k, r: m.a[i, k, r] <= m.z[i, k, r],
    )
    # (6) y binaria cuenta una sola entrega entre todos los vehículos y posiciones.
    model.eq06_unique_delivery = pyo.Constraint(
        model.C,
        rule=lambda m, i: sum(m.a[i, k, r] for k in m.K for r in m.R_moves) == m.y[i],
    )
    # (7) Energía inicial del escenario; initial_soc=0.6 reproduce el caso oficial.
    model.eq07_initial_battery = pyo.Constraint(
        model.K, rule=lambda m, k: m.b[k, 0] == m.initial_energy
    )
    model.eq07_initial_charge = pyo.Constraint(model.K, rule=lambda m, k: m.q[k, 0] == 0)
    # (8) Energía de salida = energía de llegada + recarga efectiva, en kWh.
    model.eq08_charge_balance = pyo.Constraint(
        model.K,
        model.R_moves,
        rule=lambda m, k, r: m.b_departure[k, r] == m.b[k, r] + m.q[k, r],
    )
    # (9) q >= 0 está en su dominio; esta desigualdad impide exceder la capacidad.
    model.eq09_charge_capacity = pyo.Constraint(
        model.K, model.R_moves, rule=lambda m, k, r: m.q[k, r] <= m.B - m.b[k, r]
    )
    # (10) Sólo se carga en F_k; el depósito nunca pertenece a ese conjunto.
    model.eq10_compatible_charge = pyo.Constraint(
        model.K,
        model.R_moves,
        rule=lambda m, k, r: m.q[k, r]
        <= m.B * sum(m.z[f, k, r] for f in m.F_compatible[k]),
    )
    # (11) Batería previa a saturación tras recorrer el único arco seleccionado.
    model.eq11_unsaturated_battery = pyo.Constraint(
        model.K,
        model.R_moves,
        rule=lambda m, k, r: m.u[k, r]
        == m.b_departure[k, r] - sum(m.e[i, j] * m.x[i, j, k, r] for i, j in m.A),
    )
    # (12) La llegada no supera ni u ni B; conservar ambas ecuaciones del PDF.
    model.eq12_below_unsaturated = pyo.Constraint(
        model.K, model.R_moves, rule=lambda m, k, r: m.b[k, r + 1] <= m.u[k, r]
    )
    model.eq12_below_capacity = pyo.Constraint(
        model.K, model.R_moves, rule=lambda m, k, r: m.b[k, r + 1] <= m.B
    )
    # (13) gamma=0 fuerza llegada=u; gamma=1 fuerza llegada=B.
    model.eq13_uncapped_branch = pyo.Constraint(
        model.K,
        model.R_moves,
        rule=lambda m, k, r: m.b[k, r + 1] >= m.u[k, r] - m.M * m.gamma[k, r],
    )
    model.eq13_capped_branch = pyo.Constraint(
        model.K,
        model.R_moves,
        rule=lambda m, k, r: m.b[k, r + 1] >= m.B - m.M * (1 - m.gamma[k, r]),
    )
    # (14) Consumo efectivo: la regeneración descartada por saturación no se acredita.
    model.eq14_effective_energy = pyo.Constraint(
        model.K,
        model.R_moves,
        rule=lambda m, k, r: m.E[k, r] == m.b_departure[k, r] - m.b[k, r + 1],
    )
    # (15) Energía neta total de todos los movimientos y vehículos, en kWh.
    model.eq15_total_energy = pyo.Constraint(
        expr=model.E_total == sum(model.E[k, r] for k in model.K for r in model.R_moves)
    )
    # (16) Dos objetivos separados implementan la prioridad lexicográfica.
    model.served_count = pyo.Expression(expr=sum(model.y[i] for i in model.C))
    model.deliveries_objective = pyo.Objective(expr=model.served_count, sense=pyo.maximize)
    model.energy_objective = pyo.Objective(expr=model.E_total, sense=pyo.minimize)
    model.energy_objective.deactivate()
    # La igualdad sólo se activa después de resolver la primera fase.
    model.served_count_target = pyo.Param(
        initialize=0, within=pyo.NonNegativeIntegers, mutable=True
    )
    model.served_count_constraint = pyo.Constraint(
        expr=model.served_count == model.served_count_target
    )
    model.served_count_constraint.deactivate()
    return model


def activate_energy_phase(model: pyo.ConcreteModel, served_count: int) -> None:
    """Fijar el cumplimiento encontrado; esta operación no certifica su optimalidad."""
    if isinstance(served_count, bool) or not isinstance(served_count, Integral):
        raise ValueError("served_count debe ser un entero")
    if not 0 <= served_count <= len(model.C):
        raise ValueError("served_count está fuera del número de clientes")
    model.served_count_target.set_value(int(served_count))
    model.served_count_constraint.activate()
    model.deliveries_objective.deactivate()
    model.energy_objective.activate()


def _number(variable: pyo.Var) -> float:
    """No producir un JSON de solución a partir de valores ausentes o no finitos."""
    value = pyo.value(variable, exception=False)
    if value is None or not isfinite(float(value)):
        raise ValueError(f"sin valor finito de solución para {variable.name}")
    return float(value)


def _selected(variable: pyo.Var) -> bool:
    """Reconstruir binarias con la tolerancia habitual de un incumbente MIP."""
    value = _number(variable)
    if min(abs(value), abs(value - 1)) > 1e-5:
        raise ValueError(f"valor no binario para {variable.name}: {value}")
    return value > 0.5


def extract_solution(model: pyo.ConcreteModel, instance: ProblemInstance) -> Solution:
    """Extraer todas las posiciones; el validador independiente revisa su física."""
    served = [customer for customer in instance.customer_ids if _selected(model.y[customer])]
    routes = []
    for vehicle in instance.vehicle_ids:
        locations = []
        for position in model.R:
            occupied = [
                node for node in model.V if _selected(model.z[node, vehicle, position])
            ]
            if len(occupied) != 1:
                raise ValueError(f"ubicación no única de {vehicle} en posición {position}")
            locations.append(occupied[0])

        steps = []
        for position, node in enumerate(locations):
            arrival = _number(model.b[vehicle, position])
            if position in model.R_moves:
                selected_arcs = [
                    (origin, destination)
                    for origin, destination in model.A
                    if _selected(model.x[origin, destination, vehicle, position])
                ]
                expected_arc = (node, locations[position + 1])
                if selected_arcs != [expected_arc]:
                    raise ValueError(f"arco inconsistente de {vehicle} en posición {position}")
                steps.append(
                    RouteStep(
                        position=position,
                        node_id=node,
                        battery_arrival_kwh=arrival,
                        charged_to_battery_kwh=_number(model.q[vehicle, position]),
                        battery_departure_kwh=_number(model.b_departure[vehicle, position]),
                        delivered_visit_ids=[
                            customer
                            for customer in instance.customer_ids
                            if _selected(model.a[customer, vehicle, position])
                        ],
                        next_node_id=expected_arc[1],
                        predicted_arc_energy_kwh=float(pyo.value(model.e[expected_arc])),
                        effective_arc_energy_kwh=_number(model.E[vehicle, position]),
                    )
                )
            else:
                # La posición H es llegada terminal: no hay q, a ni arco de salida.
                steps.append(
                    RouteStep(
                        position=position,
                        node_id=node,
                        battery_arrival_kwh=arrival,
                        battery_departure_kwh=arrival,
                    )
                )
        routes.append(
            VehicleRoute(
                vehicle_id=vehicle,
                steps=steps,
                net_energy_kwh=sum(_number(model.E[vehicle, r]) for r in model.R_moves),
            )
        )
    return Solution(
        routes=routes,
        served_visit_ids=served,
        unserved_visit_ids=[customer for customer in instance.customer_ids if customer not in served],
        net_energy_kwh=_number(model.E_total),
    )
