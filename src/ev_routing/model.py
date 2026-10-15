"""Traducción directa de las ecuaciones (1)–(16) de ``modelamiento.pdf``.

El índice de posición cuenta tramos viales; no representa tiempo. El módulo
construye y lee el modelo, pero no elige un solver ni certifica una solución.
"""

from __future__ import annotations

from math import isfinite
from numbers import Integral

import pyomo.environ as pyo

from ev_routing.contracts import ProblemInstance, RouteStep, Solution, VehicleRoute
from ev_routing.operations import arc_energy, schedule_solution, travel_seconds


def build_model(instance: ProblemInstance) -> pyo.ConcreteModel:
    """Construir la fase de entregas del MILP sin recortar la red recibida."""
    parameters = instance.parameters
    depot = instance.depot_id
    horizon = parameters.movement_limit
    energies = {
        (arc.from_node_id, arc.to_node_id): arc_energy(arc, instance.operations)
        for arc in instance.arcs
    }
    # El único arco añadido es la permanencia artificial en el depósito.
    energies[depot, depot] = 0.0
    outgoing = {node.node_id: [] for node in instance.nodes}
    incoming = {node.node_id: [] for node in instance.nodes}
    for origin, destination in energies:
        outgoing[origin].append(destination)
        incoming[destination].append(origin)

    model = pyo.ConcreteModel(name=instance.name)
    model.depot_id = depot
    # Conjuntos del PDF: nodos, arcos, clientes, estaciones y vehículos.
    model.V = pyo.Set(initialize=[node.node_id for node in instance.nodes], ordered=True)
    model.A = pyo.Set(dimen=2, initialize=list(energies), ordered=True)
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
    model.e = pyo.Param(model.A, initialize=energies, within=pyo.Reals)
    model.M = pyo.Param(
        initialize=parameters.battery_capacity_kwh + max(map(abs, energies.values())),
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
    _add_operations(model, instance)
    return model


def _add_operations(model: pyo.ConcreteModel, instance: ProblemInstance) -> None:
    """(17)–(24) del PDF: construir solo los bloques habilitados."""
    ops = instance.operations
    if ops.final_reserve_soc is not None:
        model.eq18_final_reserve = pyo.Constraint(
            model.K, rule=lambda m, k: m.b[k, m.H] >= ops.final_reserve_soc * m.B
        )
    if not ops.timing_enabled:
        return
    times = {
        (a.from_node_id, a.to_node_id): travel_seconds(a, ops) for a in instance.arcs
    }
    times[instance.depot_id, instance.depot_id] = 0.0
    model.travel_seconds = pyo.Param(model.A, initialize=times)
    model.service_duration = pyo.Expression(
        model.K, model.R_moves,
        rule=lambda m, k, r: sum(ops.service_duration(i) * m.a[i, k, r] for i in m.C),
    )
    model.travel_duration = pyo.Expression(
        model.K, model.R_moves,
        rule=lambda m, k, r: sum(m.travel_seconds[i, j] * m.x[i, j, k, r] for i, j in m.A),
    )
    if ops.include_charging_time:
        model.charging_pairs = pyo.Set(
            dimen=2, initialize=[(f, k) for k in model.K for f in model.F_compatible[k]]
        )
        model.station_charge = pyo.Var(
            model.charging_pairs, model.R_moves, domain=pyo.NonNegativeReals,
        )
        # (19) Localizar la recarga: no multiplicar q por la binaria z.
        model.eq19_station_charge_bound = pyo.Constraint(
            model.charging_pairs, model.R_moves,
            rule=lambda m, f, k, r: m.station_charge[f, k, r] <= m.B * m.z[f, k, r],
        )
        model.eq19_station_charge_sum = pyo.Constraint(
            model.K, model.R_moves,
            rule=lambda m, k, r: m.q[k, r] == sum(
                m.station_charge[f, k, r] for f in m.F_compatible[k]
            ),
        )
    model.charging_duration = pyo.Expression(
        model.K, model.R_moves,
        rule=lambda m, k, r: sum(
            3600 * m.station_charge[f, k, r] / (ops.charging_efficiency * ops.charging_power(f))
            for f in m.F_compatible[k]
        ) if ops.include_charging_time else 0,
    )
    if not ops.use_customer_time_windows:
        # (21) Sin ventanas no hacen falta relojes ni binarias adicionales.
        model.route_duration = pyo.Expression(
            model.K, rule=lambda m, k: sum(
                m.travel_duration[k, r] + m.service_duration[k, r] + m.charging_duration[k, r]
                for r in m.R_moves
            ),
        )
        if ops.max_route_seconds is not None:
            model.eq21_duration_limit = pyo.Constraint(
                model.K, rule=lambda m, k: m.route_duration[k] <= ops.max_route_seconds,
            )
        return
    horizon = ops.max_route_seconds  # El contrato exige una cota temporal finita.
    model.arrival_time = pyo.Var(model.K, model.R, bounds=(0, horizon))
    model.activity_start = pyo.Var(model.K, model.R_moves, bounds=(0, horizon))
    model.eq22_initial_time = pyo.Constraint(
        model.K, rule=lambda m, k: m.arrival_time[k, 0] == 0,
    )
    model.eq22_wait = pyo.Constraint(
        model.K, model.R_moves,
        rule=lambda m, k, r: m.activity_start[k, r] >= m.arrival_time[k, r],
    )
    model.eq22_clock = pyo.Constraint(
        model.K, model.R_moves,
        rule=lambda m, k, r: m.arrival_time[k, r + 1] == (
            m.activity_start[k, r] + m.service_duration[k, r]
            + m.charging_duration[k, r] + m.travel_duration[k, r]
        ),
    )
    model.window_customers = pyo.Set(initialize=list(ops.customer_time_windows), within=model.C)
    # (23) M de apertura = L_i; M de cierre = max(0,T-U_i).
    model.eq23_window_open = pyo.Constraint(
        model.window_customers, model.K, model.R_moves,
        rule=lambda m, i, k, r: m.activity_start[k, r]
        >= ops.customer_time_windows[i].open_seconds * m.a[i, k, r],
    )
    model.eq23_window_close = pyo.Constraint(
        model.window_customers, model.K, model.R_moves,
        rule=lambda m, i, k, r: m.activity_start[k, r] + ops.service_duration(i) * m.a[i, k, r]
        <= ops.customer_time_windows[i].close_seconds
        + max(0, horizon - ops.customer_time_windows[i].close_seconds) * (1 - m.a[i, k, r]),
    )
    model.route_duration = pyo.Expression(
        model.K, rule=lambda m, k: m.arrival_time[k, m.H],
    )


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
    solution = Solution(
        routes=routes,
        served_visit_ids=served,
        unserved_visit_ids=[customer for customer in instance.customer_ids if customer not in served],
        net_energy_kwh=_number(model.E_total),
    )
    # La espera sobrante no mejora los objetivos. Se publica el calendario más
    # temprano de las mismas rutas/recargas; su factibilidad se audita aparte.
    return schedule_solution(instance, solution)
