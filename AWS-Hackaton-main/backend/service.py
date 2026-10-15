"""Núcleo de servicio del backend de ruteo EV.

Lógica agnóstica a la interfaz: la usan por igual el handler Lambda, un servidor
local, Streamlit o cualquier UI futura. No importa boto3 ni Streamlit aquí, para
mantenerlo liviano y testeable.

Contrato de entrada/salida (estable, versionado): ver API_CONTRACT.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ev_routing.contracts import FleetConfig, Node, Network, ProblemInstance, RunResult, SolverConfig
from ev_routing.inputs import build_heuristic_network, rows_to_nodes
from ev_routing.pipeline import run as run_pipeline

API_VERSION = "1.0"


class SolveRequestError(ValueError):
    """Error de validación de la petición (datos de entrada inválidos)."""


def _nodes_from_payload(nodes_payload: List[Dict[str, Any]]) -> List[Node]:
    """Convierte una lista de dicts de nodos en objetos Node validados.

    Reutiliza `rows_to_nodes` vía DataFrame para aplicar la misma validación que
    la carga por CSV (coordenadas, tipos, duplicados).
    """
    import pandas as pd

    if not nodes_payload:
        raise SolveRequestError("La petición no incluye nodos.")
    try:
        df = pd.DataFrame(nodes_payload)
        return rows_to_nodes(df)
    except Exception as e:  # noqa: BLE001
        raise SolveRequestError(f"Nodos inválidos: {e}") from e


def build_instance(payload: Dict[str, Any]) -> ProblemInstance:
    """Construye una ProblemInstance a partir del payload JSON de la API.

    Estructura esperada (todos los campos de 'fleet' y 'solver' son opcionales):
        {
          "nodes": [ {node_id, node_type, latitude, longitude, ...}, ... ],
          "movement_limit": 6,
          "fleet": {num_vehicles, battery_capacity_kwh, reserve_kwh, initial_soc},
        }
    """
    nodes = _nodes_from_payload(payload.get("nodes", []))

    fleet_in = payload.get("fleet", {}) or {}
    fleet = FleetConfig(
        num_vehicles=int(fleet_in.get("num_vehicles", 2)),
        battery_capacity_kwh=float(fleet_in.get("battery_capacity_kwh", 24.0)),
        reserve_kwh=float(fleet_in.get("reserve_kwh", 2.4)),
        initial_soc=float(fleet_in.get("initial_soc", 0.6)),
    )

    movement_limit = int(payload.get("movement_limit", 6))

    # La red puede venir dada; si no, se construye la heurística (como en inputs.py).
    network_in = payload.get("network")
    if network_in:
        network = Network.model_validate(network_in)
    else:
        network = build_heuristic_network(nodes)

    return ProblemInstance(
        nodes=nodes,
        fleet=fleet,
        network=network,
        movement_limit=movement_limit,
        provenance={"source": "api", "api_version": API_VERSION},
    )


def solve(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Resuelve una instancia y devuelve un dict JSON-serializable.

    Punto de entrada único del backend. Cualquier frontend llama a esto
    (directamente en local, o vía Lambda/API Gateway en la nube).
    """
    instance = build_instance(payload)

    solver_in = payload.get("solver", {}) or {}
    solver_cfg = SolverConfig(
        time_limit_seconds=float(solver_in.get("time_limit_seconds", 120.0)),
        mip_gap=solver_in.get("mip_gap"),
    )

    result: RunResult = run_pipeline(instance, solver_cfg)
    return {
        "api_version": API_VERSION,
        "result": result.model_dump(),
    }


def health() -> Dict[str, Any]:
    """Estado del servicio, útil para health checks de API Gateway/ALB."""
    return {"status": "ok", "api_version": API_VERSION}
