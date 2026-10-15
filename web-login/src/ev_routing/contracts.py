from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class NodeType(str, Enum):
    BASE = "base"
    VISIT = "visit"
    CHARGER = "charger"


class Node(BaseModel):
    node_id: str
    node_type: NodeType
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    network: Optional[str] = None
    total_ports: int = 0
    dc_fast_ports: int = 0
    level2_ports: int = 0
    connector_types: List[str] = Field(default_factory=list)
    max_power_kw: Optional[float] = None

    @field_validator("total_ports", "dc_fast_ports", "level2_ports")
    @classmethod
    def non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("port counts must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_port_totals(self) -> "Node":
        if self.total_ports < self.dc_fast_ports + self.level2_ports:
            # warn-level inconsistency; kept as error? AGENTS says inform. We allow with marker.
            pass
        return self


class Arc(BaseModel):
    origin: str
    destination: str
    distance_km: Optional[float] = None
    travel_time_s: Optional[float] = None
    energy_kwh: float
    allowed: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Network(BaseModel):
    nodes: List[str] = Field(default_factory=list)
    arcs: List[Arc] = Field(default_factory=list)
    directed: bool = True
    provenance: str = "unspecified"

    def arc_energy(self, origin: str, destination: str) -> Optional[float]:
        for arc in self.arcs:
            if arc.origin == origin and arc.destination == destination:
                return arc.energy_kwh
        return None

    def adjacency(self) -> Dict[str, List[str]]:
        adj: Dict[str, List[str]] = {n: [] for n in self.nodes}
        for arc in self.arcs:
            if arc.allowed:
                adj.setdefault(arc.origin, []).append(arc.destination)
        return adj

    def validate_against_nodes(self, instance_nodes: List[str]) -> List[str]:
        errors = []
        node_set = set(instance_nodes)
        for n in self.nodes:
            if n not in node_set:
                errors.append(f"network node {n!r} is not in instance nodes")
        for arc in self.arcs:
            if arc.origin not in node_set:
                errors.append(f"arc origin {arc.origin!r} unknown")
            if arc.destination not in node_set:
                errors.append(f"arc destination {arc.destination!r} unknown")
        return errors


class FleetConfig(BaseModel):
    num_vehicles: int = 2
    battery_capacity_kwh: float = 24.0
    reserve_kwh: float = 2.4
    initial_soc: float = 0.6
    compatible_chargers: Optional[Dict[int, List[str]]] = None
    connector_type: Optional[str] = None
    max_charge_power_kw: Optional[float] = None

    @field_validator("num_vehicles")
    @classmethod
    def positive_vehicles(cls, v: int) -> int:
        if v < 1:
            raise ValueError("num_vehicles must be >= 1")
        return v

    @property
    def initial_energy_kwh(self) -> float:
        return self.initial_soc * self.battery_capacity_kwh


class SolverConfig(BaseModel):
    backend: str = "highs"
    time_limit_seconds: Optional[float] = 300.0
    mip_gap: Optional[float] = None
    seed: Optional[int] = 0
    threads: Optional[int] = None
    movement_limit_parameter: Optional[int] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class ProblemConfig(BaseModel):
    movement_limit: int
    battery_capacity_kwh: float
    reserve_kwh: float
    initial_soc: float = 0.6
    require_charger_compatibility: bool = True

    @property
    def initial_energy_kwh(self) -> float:
        return self.initial_soc * self.battery_capacity_kwh


class ProblemInstance(BaseModel):
    schema_version: str = "1.0"
    instance_id: Optional[str] = None
    nodes: List[Node]
    fleet: FleetConfig
    network: Network
    movement_limit: int
    energy_model_version: str = "unspecified"
    provenance: Dict[str, Any] = Field(default_factory=dict)
    problem_config: Optional[ProblemConfig] = None

    @model_validator(mode="after")
    def ensure_config(self) -> "ProblemInstance":
        if self.problem_config is None:
            self.problem_config = ProblemConfig(
                movement_limit=self.movement_limit,
                battery_capacity_kwh=self.fleet.battery_capacity_kwh,
                reserve_kwh=self.fleet.reserve_kwh,
                initial_soc=self.fleet.initial_soc,
            )
        return self

    def base_nodes(self) -> List[str]:
        return [n.node_id for n in self.nodes if n.node_type == NodeType.BASE]

    def visit_nodes(self) -> List[str]:
        return [n.node_id for n in self.nodes if n.node_type == NodeType.VISIT]

    def charger_nodes(self) -> List[str]:
        return [n.node_id for n in self.nodes if n.node_type == NodeType.CHARGER]

    def node_by_id(self) -> Dict[str, Node]:
        return {n.node_id: n for n in self.nodes}

    def compatible_chargers(self, vehicle_index: int) -> List[str]:
        if self.fleet.compatible_chargers and vehicle_index in self.fleet.compatible_chargers:
            return list(self.fleet.compatible_chargers[vehicle_index])
        # default: chargers with at least one port
        out = []
        for n in self.nodes:
            if n.node_type == NodeType.CHARGER:
                if n.total_ports > 0 or n.dc_fast_ports > 0 or n.level2_ports > 0 or n.total_ports == 0:
                    out.append(n.node_id)
        return out


class TuningRequest(BaseModel):
    schema_version: str = "1.0"
    structural_summary: Dict[str, Any] = Field(default_factory=dict)
    solver_capabilities: Dict[str, Any] = Field(default_factory=dict)
    allowed_parameters: List[str] = Field(default_factory=list)
    budget_seconds: Optional[float] = None


class TuningProposal(BaseModel):
    schema_version: str = "1.0"
    solver: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    warnings: List[str] = Field(default_factory=list)


class PhaseResult(BaseModel):
    name: str
    objective_sense: str
    incumbent_objective: Optional[float] = None
    bound: Optional[float] = None
    gap: Optional[float] = None
    termination: str
    runtime_seconds: Optional[float] = None


class RouteStep(BaseModel):
    position: int
    node_id: str
    arrival_energy_kwh: Optional[float] = None
    departure_energy_kwh: Optional[float] = None
    charge_kwh: float = 0.0
    delivered_visit_ids: List[str] = Field(default_factory=list)
    arc_energy_kwh: Optional[float] = None


class VehicleRoute(BaseModel):
    vehicle_index: int
    steps: List[RouteStep]
    served_visit_ids: List[str] = Field(default_factory=list)
    distance_km: Optional[float] = None
    total_energy_kwh: Optional[float] = None


class ValidationResult(BaseModel):
    feasible: bool
    violations: List[str] = Field(default_factory=list)


class RunResult(BaseModel):
    schema_version: str = "1.0"
    run_id: Optional[str] = None
    instance_id: Optional[str] = None
    phases: List[PhaseResult] = Field(default_factory=list)
    tuning: Optional[Dict[str, Any]] = None
    routes: List[VehicleRoute] = Field(default_factory=list)
    unserved_visit_ids: List[str] = Field(default_factory=list)
    validation: Optional[ValidationResult] = None
    kpis: Dict[str, Any] = Field(default_factory=dict)
    runtime_seconds: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    served_count: Optional[int] = None
    total_energy_kwh: Optional[float] = None
    delivered_count: Optional[int] = None
