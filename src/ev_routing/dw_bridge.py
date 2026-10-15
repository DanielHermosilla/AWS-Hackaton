"""Traducción lineal auditada de Pyomo a GCG; ninguna ecuación se sustituye.

La descomposición ``vehicle`` convexifica el bloque completo de cada vehículo.
``vehicle_routing`` deja batería y tiempos en el maestro y convexifica sus
caminatas. Ambas conservan todas las filas y la integralidad original; tienen
relajaciones distintas, pero el mismo problema entero y el mismo H.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pyomo.environ as pyo
from pyomo.repn import generate_standard_repn

from ev_routing.contracts import ProblemInstance

DECOMPOSITIONS = ("vehicle", "vehicle_routing")
_VEHICLE_VARIABLES = {
    "z", "x", "a", "q", "b", "b_departure", "u", "gamma", "E",
    "station_charge", "arrival_time", "activity_start",
}
_ROUTING_ROWS = {
    "eq01_location", "eq02_start", "eq02_return", "eq03_departure",
    "eq04_arrival", "eq05_service_location",
}


@dataclass
class LinearBridge:
    source: Any
    native: Any
    variables: dict[int, Any]
    rows: list[tuple[Any, str, str | None]]
    profile: dict[str, Any]

    def decompose(self, choice: str, vehicles: list[str]) -> dict[str, Any]:
        if choice not in DECOMPOSITIONS:
            raise ValueError(f"Descomposición no implementada: {choice}")
        master, blocks = [], {k: [] for k in vehicles}
        for row, component, owner in self.rows:
            local = owner is not None and (
                choice == "vehicle" or component in _ROUTING_ROWS
            )
            (blocks[owner] if local else master).append(row)
        if any(not rows for rows in blocks.values()):
            raise ValueError("Descomposición con un bloque vacío")
        if len(master) + sum(map(len, blocks.values())) != len(self.rows):
            raise ValueError("La partición no conserva todas las restricciones")
        decomposition = self.native.addDecompositionFromConss(master, *blocks.values())
        return {
            "name": choice,
            "master_rows": len(master),
            "block_rows": [len(rows) for rows in blocks.values()],
            "blocks": len(blocks),
            "all_rows_assigned_once": True,
            "same_original_integrality": True,
            "decomposition_id": decomposition.getID(),
        }

    def load_solution(self, solution: Any) -> None:
        for variable in self.source.component_data_objects(pyo.Var, active=True):
            variable.set_value(
                self.native.getSolVal(solution, self.variables[id(variable)]),
                skip_validation=True,
            )

    def submit_start(self) -> bool:
        values = list(self.source.component_data_objects(pyo.Var, active=True))
        if any(variable.value is None for variable in values):
            raise ValueError("El arranque no tiene todos los valores Pyomo")
        solution = self.native.createSol()
        for variable in values:
            self.native.setSolVal(solution, self.variables[id(variable)], float(variable.value))
        return bool(self.native.addSol(solution, free=True))


def translate_model(source: Any, instance: ProblemInstance) -> LinearBridge:
    """Conservar coeficientes, constantes, cotas, dominios y sentido del objetivo."""
    from pygcgopt import Model, quicksum

    native = Model("electric-routing-dw")
    native.hideOutput()
    variables, owners, numbers = {}, {}, {}
    matrix: dict[str, Any] = {"variables": [], "rows": []}
    for number, variable in enumerate(source.component_data_objects(pyo.Var, active=True)):
        component = variable.parent_component().local_name
        owner = None
        if component in _VEHICLE_VARIABLES:
            owner = variable.index()[-2]
            if owner not in instance.vehicle_ids:
                raise ValueError(f"Propietario no reconocido: {variable.name}")
        elif component not in {"y", "E_total"}:
            raise ValueError(f"Variable sin clasificación DW: {component}")
        kind = "B" if variable.is_binary() else "I" if variable.is_integer() else "C"
        lower = float(pyo.value(variable.lb)) if variable.lb is not None else None
        upper = float(pyo.value(variable.ub)) if variable.ub is not None else None
        if variable.fixed:
            lower = upper = float(pyo.value(variable))
        variables[id(variable)] = native.addVar(
            name=f"v{number}", vtype=kind,
            lb=lower if lower is not None else -native.infinity(),
            ub=upper if upper is not None else native.infinity(),
        )
        owners[id(variable)] = owner
        numbers[id(variable)] = number
        matrix["variables"].append([kind, lower, upper])

    def linear(expression):
        repn = generate_standard_repn(expression, compute_values=True)
        if not repn.is_linear():
            raise ValueError("La integración DW admite únicamente la formulación lineal")
        terms = [(id(v), float(c)) for v, c in zip(repn.linear_vars, repn.linear_coefs)]
        constant = float(repn.constant or 0)
        return repn, terms, constant

    rows = []
    for constraint in source.component_data_objects(pyo.Constraint, active=True):
        _, terms, constant = linear(constraint.body)
        owner_set = {owners[key] for key, _ in terms}
        owner = next(iter(owner_set)) if len(owner_set) == 1 and None not in owner_set else None
        expression = quicksum(coef * variables[key] for key, coef in terms)
        lower = float(pyo.value(constraint.lower)) - constant if constraint.has_lb() else None
        upper = float(pyo.value(constraint.upper)) - constant if constraint.has_ub() else None
        specs = [("eq", lower)] if constraint.equality else (
            ([("ge", lower)] if lower is not None else [])
            + ([("le", upper)] if upper is not None else [])
        )
        for sense, rhs in specs:
            relation = expression == rhs if sense == "eq" else (
                expression >= rhs if sense == "ge" else expression <= rhs
            )
            row = native.addCons(relation, name=f"r{len(rows)}")
            rows.append((row, constraint.parent_component().local_name, owner))
            matrix["rows"].append([
                sense, rhs, [[numbers[key], coefficient] for key, coefficient in terms],
            ])
    objectives = list(source.component_data_objects(pyo.Objective, active=True))
    if len(objectives) != 1:
        raise ValueError("Debe existir exactamente un objetivo activo")
    _, terms, constant = linear(objectives[0].expr)
    sense = "maximize" if objectives[0].sense == pyo.maximize else "minimize"
    native.setObjective(
        quicksum(coef * variables[key] for key, coef in terms) + constant, sense=sense,
    )
    matrix["objective"] = [sense, constant, [[numbers[key], c] for key, c in terms]]
    digest = hashlib.sha256(
        json.dumps(matrix, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    profile = {
        "matrix_sha256": digest,
        "variables": len(variables),
        "binary_variables": sum(v[0] == "B" for v in matrix["variables"]),
        "rows": len(rows),
        "nonzeros": sum(len(row[2]) for row in matrix["rows"]),
        "objective_sense": sense,
        "vehicles": len(instance.vehicle_ids),
        "customers": len(instance.customer_ids),
        "chargers": len(instance.charger_ids),
        "nodes": len(instance.nodes),
        "arcs": len(instance.arcs),
        "movement_limit": instance.parameters.movement_limit,
        "regeneration": any(arc.energy_kwh < 0 for arc in instance.arcs),
        "timing_enabled": instance.operations.timing_enabled,
        "time_windows": instance.operations.use_customer_time_windows,
        "available_decompositions": list(DECOMPOSITIONS),
    }
    return LinearBridge(source, native, variables, rows, profile)
