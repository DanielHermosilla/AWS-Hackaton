"""Esqueleto del futuro tuning; deliberadamente fuera del flujo de resolución.

Integración futura, siguiendo LLM4MIP:
1. Resumir estructura del MISMO modelo Pyomo con ``build_tuning_request``.
2. Enviar únicamente ese perfil a un modelo autorizado de AWS Bedrock.
3. Validar JSON y opciones admitidas por la versión del solver.
4. Comparar contra el baseline con igual modelo, presupuesto y recursos.

No cambiar B, reserva, H, objetivos ni tolerancias para aparentar una mejora.
No ejecutar código, comandos o ecuaciones devueltos por el LLM.
"""

from __future__ import annotations

from typing import Any

import pyomo.environ as pyo

from ev_routing.contracts import SolverConfig


def build_tuning_request(model: pyo.ConcreteModel, config: SolverConfig) -> dict[str, Any]:
    """Crear un perfil local sin direcciones, históricos, credenciales o red."""
    variables = list(model.component_data_objects(pyo.Var, active=True))
    return {
        "schema_version": "1.0",
        "problem_family": "electric_vehicle_routing",
        "variable_count": len(variables),
        "binary_variable_count": sum(var.is_binary() for var in variables),
        "constraint_count": sum(
            1 for _ in model.component_data_objects(pyo.Constraint, active=True)
        ),
        "solver_config": config.model_dump(),
        "allowed_parameters": {},  # Futura allowlist específica de solver/versión.
        "status": "disabled",
    }


def propose_tuning(request: dict[str, Any]) -> dict[str, Any]:
    """Punto futuro de llamada a Bedrock; hoy nunca devuelve un tuning ficticio."""
    raise NotImplementedError(
        "LLM desactivado en modelamiento: no se realizan llamadas a AWS. "
        "Implementar aquí la propuesta JSON y su validación en una tarea posterior."
    )
