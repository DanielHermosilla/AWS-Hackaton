"""Contratos compartidos por datos, Pyomo, solver, validador y CLI.

Las unidades forman parte del nombre de cada campo. Estos objetos son datos
validados, no modelos de optimización. Se serializan directamente a JSON.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    """Rechaza campos desconocidos y números no finitos antes de modelar."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Node(Contract):
    """Nodo de servicio o intersección de la red vial dirigida."""

    node_id: str = Field(min_length=1)
    node_type: Literal["base", "visit", "charger", "junction"]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str = ""
    network: str = ""
    total_ports: int | None = Field(default=None, ge=0)
    dc_fast_ports: int | None = Field(default=None, ge=0)
    level2_ports: int | None = Field(default=None, ge=0)
    connector_types: list[str] = Field(default_factory=list)
    max_power_kw: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def coordinates_are_paired(self) -> Node:
        """No aceptar una ubicación de la que solo se conoce una coordenada."""
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude y longitude deben estar presentes juntas")
        return self


class Arc(Contract):
    """Tramo elemental; energía negativa significa regeneración potencial.

    No puede ocultar una descarga seguida de regeneración: esos cambios de
    signo se representan mediante tramos separados, como exige el PDF.
    """

    from_node_id: str
    to_node_id: str
    energy_kwh: float
    distance_m: float = Field(default=0.0, ge=0)
    geometry: list[tuple[float, float]] = Field(default_factory=list)
    source_id: str | None = None


class ModelParameters(Contract):
    """Parámetros físicos y H del PDF; H no es un horizonte temporal."""

    vehicle_count: int = Field(default=2, ge=1)
    battery_capacity_kwh: float = Field(default=24.0, gt=0)
    reserve_kwh: float = Field(default=2.4, gt=0)
    initial_soc: float = Field(default=0.6, gt=0, le=1)
    movement_limit: int = Field(default=20, ge=1)
    vehicle_connector_types: list[str] = Field(default_factory=lambda: ["J1772", "CHAdeMO"])

    @model_validator(mode="after")
    def reserve_is_available_initially(self) -> ModelParameters:
        """Una reserva mayor a la energía inicial hace inválido el escenario."""
        if self.reserve_kwh > self.initial_energy_kwh:
            raise ValueError("reserve_kwh supera la energía inicial")
        return self

    @property
    def initial_energy_kwh(self) -> float:
        return self.initial_soc * self.battery_capacity_kwh


class ProblemInstance(Contract):
    """Instancia completa: nodos, arcos elementales y parámetros del escenario."""

    schema_version: Literal["1.0"] = "1.0"
    name: str = "instance"
    nodes: list[Node]
    arcs: list[Arc]
    parameters: ModelParameters = Field(default_factory=ModelParameters)
    # Si se especifica, este diccionario reemplaza la inferencia por conectores.
    # Es útil para flotas diferentes y fixtures cuya compatibilidad es conocida.
    compatible_chargers: dict[str, list[str]] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def graph_is_consistent(self) -> ProblemInstance:
        """Validar la estructura antes de crear miles de variables binarias."""
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("node_id duplicado")
        if sum(node.node_type == "base" for node in self.nodes) != 1:
            raise ValueError("se requiere exactamente un nodo base")
        known = set(ids)
        pairs: set[tuple[str, str]] = set()
        for arc in self.arcs:
            pair = (arc.from_node_id, arc.to_node_id)
            if not set(pair) <= known:
                raise ValueError(f"arco referencia nodos inexistentes: {pair}")
            if pair in pairs:
                raise ValueError(f"arco duplicado: {pair}; subdividir arcos paralelos")
            if pair[0] == pair[1]:
                raise ValueError("no incluir autoarcos: el modelo añade (base, base)")
            pairs.add(pair)
        if self.compatible_chargers is not None:
            if set(self.compatible_chargers) != set(self.vehicle_ids):
                raise ValueError("compatible_chargers debe incluir todos los vehículos")
            chargers = set(self.charger_ids)
            for compatible in self.compatible_chargers.values():
                if not set(compatible) <= chargers:
                    raise ValueError("estación compatible inexistente o de tipo incorrecto")
        return self

    @property
    def depot_id(self) -> str:
        return next(node.node_id for node in self.nodes if node.node_type == "base")

    @property
    def customer_ids(self) -> list[str]:
        return [node.node_id for node in self.nodes if node.node_type == "visit"]

    @property
    def charger_ids(self) -> list[str]:
        return [node.node_id for node in self.nodes if node.node_type == "charger"]

    @property
    def vehicle_ids(self) -> list[str]:
        return [f"vehicle_{i + 1}" for i in range(self.parameters.vehicle_count)]

    def chargers_for(self, vehicle_id: str) -> list[str]:
        """La ausencia de información de conector no implica compatibilidad."""
        if vehicle_id not in self.vehicle_ids:
            raise ValueError(f"vehículo desconocido: {vehicle_id}")
        if self.compatible_chargers is not None:
            return self.compatible_chargers[vehicle_id]
        connectors = set(self.parameters.vehicle_connector_types)
        return [
            node.node_id
            for node in self.nodes
            if node.node_type == "charger" and connectors.intersection(node.connector_types)
        ]


class SolverConfig(Contract):
    """Recursos de resolución, independientes de los parámetros físicos."""

    solver: Literal["auto", "gurobi", "scip"] = "auto"
    time_limit_seconds: float = Field(default=60.0, gt=0)
    relative_gap: float = Field(default=0.0, ge=0, le=1)
    threads: int = Field(default=1, ge=1)
    seed: int = Field(default=0, ge=0, le=2_000_000_000)
    tee: bool = False


class PhaseResult(Contract):
    """Certificado y estado de UNA fase; no mezclar gaps de objetivos distintos."""

    name: Literal["deliveries", "energy"]
    sense: Literal["maximize", "minimize"]
    status: str
    termination_condition: str
    has_solution: bool
    proven_optimal: bool
    incumbent: float | None = None
    best_bound: float | None = None
    absolute_gap: float | None = None
    relative_gap: float | None = None
    runtime_seconds: float = Field(default=0.0, ge=0)
    message: str = ""


class RouteStep(Contract):
    """Una posición r del PDF, incluida la posición terminal sin salida."""

    position: int = Field(ge=0)
    node_id: str
    battery_arrival_kwh: float
    charged_to_battery_kwh: float = 0.0
    battery_departure_kwh: float
    delivered_visit_ids: list[str] = Field(default_factory=list)
    next_node_id: str | None = None
    predicted_arc_energy_kwh: float | None = None
    effective_arc_energy_kwh: float | None = None


class VehicleRoute(Contract):
    """Recorrido completo, conservando posiciones para auditar el modelo."""

    vehicle_id: str
    steps: list[RouteStep]
    net_energy_kwh: float


class Solution(Contract):
    """Incumbente extraído del solver; aún necesita validación independiente."""

    routes: list[VehicleRoute]
    served_visit_ids: list[str]
    unserved_visit_ids: list[str]
    net_energy_kwh: float


class ValidationReport(Contract):
    feasible: bool
    violations: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)


class SolveResult(Contract):
    """Resultado de resolución reutilizable sin CLI, archivos o UI."""

    requested_solver: str
    used_solver: str | None = None
    solver_version: str | None = None
    fallback_reason: str | None = None
    phases: list[PhaseResult] = Field(default_factory=list)
    solution: Solution | None = None
    lexicographic_optimal: bool = False
    status: str
    runtime_seconds: float = Field(default=0.0, ge=0)
    message: str = ""


def finite_or_none(value: Any) -> float | None:
    """Convertir cotas infinitas/no disponibles del solver a null JSON."""
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        return None
    return numeric if isfinite(numeric) else None
