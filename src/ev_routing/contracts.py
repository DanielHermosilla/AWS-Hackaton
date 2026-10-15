"""Contratos compartidos por datos, Pyomo, solver, validador y CLI.

Las unidades forman parte del nombre de cada campo. Estos objetos son datos
validados, no modelos de optimización. Se serializan directamente a JSON.
"""

from __future__ import annotations

from math import isfinite, ulp
from typing import Annotated, Any, Literal

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


class BatteryProfile(Contract):
    """Camino sin actividades: F(b)=min(b-consumption, maximum_arrival).

    El dominio es [minimum_departure, B]. Incluye el margen aplicado calle
    por calle, los déficits intermedios y la regeneración desperdiciada.
    """

    consumption_kwh: float
    minimum_departure_kwh: float = Field(ge=0)
    maximum_arrival_kwh: float = Field(ge=0)


class Arc(Contract):
    """Calle elemental o camino identificado con perfil explícito de batería.

    Sin battery_profile no puede ocultar cambios de signo. Los perfiles solo
    se admiten en resource_paths 1.1, con calles archivadas para su auditoría.
    """

    from_node_id: str
    to_node_id: str
    energy_kwh: float
    distance_m: float = Field(default=0.0, ge=0)
    travel_time_seconds: float | None = Field(default=None, ge=0)
    geometry: list[tuple[float, float]] = Field(default_factory=list)
    source_id: str | None = None
    arc_id: str | None = Field(default=None, min_length=1)
    battery_profile: BatteryProfile | None = None


Nonnegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]


class TimeWindow(Contract):
    """Recepción completa entre apertura y cierre, segundos desde el inicio."""

    open_seconds: float = Field(ge=0)
    close_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> TimeWindow:
        if self.close_seconds < self.open_seconds:
            raise ValueError("close_seconds debe ser >= open_seconds")
        return self


class Operations(Contract):
    """Extensiones opcionales; defaults neutros reproducen el modelo base."""

    service_seconds: float = Field(default=0, ge=0)
    service_seconds_by_customer: dict[str, Nonnegative] = Field(default_factory=dict)
    max_route_seconds: float | None = Field(default=None, gt=0)
    # Solo se usa cuando un arco no trae su propio tiempo. Nunca inferir del
    # límite legal una velocidad real de conducción ni una congestión observada.
    assumed_speed_kph: float | None = Field(default=None, gt=0)
    include_charging_time: bool = False
    charging_power_kw: float | None = Field(default=None, gt=0)
    charging_power_kw_by_station: dict[str, Positive] = Field(default_factory=dict)
    charging_efficiency: float = Field(default=1, gt=0, le=1)
    final_reserve_soc: float | None = Field(default=None, ge=0, le=1)
    energy_margin_fraction: float = Field(default=0, ge=0)
    disabled_charger_ids: list[str] = Field(default_factory=list)
    use_customer_time_windows: bool = False
    customer_time_windows: dict[str, TimeWindow] = Field(default_factory=dict)

    @model_validator(mode="after")
    def dependencies(self) -> Operations:
        if self.use_customer_time_windows:
            if not self.customer_time_windows:
                raise ValueError("Las ventanas activadas requieren customer_time_windows")
            if self.max_route_seconds is None:
                raise ValueError("Las ventanas requieren max_route_seconds para acotar los relojes")
        if len(set(self.disabled_charger_ids)) != len(self.disabled_charger_ids):
            raise ValueError("disabled_charger_ids contiene IDs duplicados")
        return self

    @property
    def timing_enabled(self) -> bool:
        return (
            self.max_route_seconds is not None or self.use_customer_time_windows
            or self.include_charging_time or self.service_seconds > 0
            or any(self.service_seconds_by_customer.values())
        )

    def service_duration(self, customer: str) -> float:
        return self.service_seconds_by_customer.get(customer, self.service_seconds)

    def charging_power(self, station: str) -> float | None:
        return self.charging_power_kw_by_station.get(station, self.charging_power_kw)


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
    """Instancia completa: red elemental o caminos con perfiles y escenario."""

    schema_version: Literal["1.0", "1.1"] = "1.0"
    name: str = "instance"
    nodes: list[Node]
    arcs: list[Arc]
    parameters: ModelParameters = Field(default_factory=ModelParameters)
    operations: Operations = Field(default_factory=Operations)
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
        arc_ids: set[str] = set()
        profiles = self.provenance.get("representation", {}).get("kind") == "resource_paths"
        if profiles and self.schema_version != "1.1":
            raise ValueError("resource_paths requiere schema_version 1.1")
        for arc in self.arcs:
            pair = (arc.from_node_id, arc.to_node_id)
            if not set(pair) <= known:
                raise ValueError(f"arco referencia nodos inexistentes: {pair}")
            if profiles:
                if arc.arc_id is None or arc.arc_id in arc_ids or arc.battery_profile is None:
                    raise ValueError("Cada camino requiere arc_id único y battery_profile")
                arc_ids.add(arc.arc_id)
                profile, params = arc.battery_profile, self.parameters
                if not (
                    params.reserve_kwh <= profile.minimum_departure_kwh <= params.battery_capacity_kwh
                    # Un techo calculado como 24-21.6 puede redondear unas ulp
                    # bajo 2.4. Solo tolerar representación; no alterar valores
                    # ni usar esta holgura en la dominancia o en el pricing.
                    and params.reserve_kwh - 8 * ulp(params.battery_capacity_kwh)
                    <= profile.maximum_arrival_kwh <= params.battery_capacity_kwh
                ):
                    raise ValueError("Perfil de batería fuera de capacidad/reserva")
            elif arc.battery_profile is not None or arc.arc_id is not None:
                raise ValueError("Los perfiles y arc_id requieren la representación resource_paths")
            if pair in pairs and not profiles:
                raise ValueError(f"arco duplicado: {pair}; subdividir arcos paralelos")
            if pair[0] == pair[1] and not profiles:
                raise ValueError("no incluir autoarcos: el modelo añade (base, base)")
            pairs.add(pair)
        if self.compatible_chargers is not None:
            if set(self.compatible_chargers) != set(self.vehicle_ids):
                raise ValueError("compatible_chargers debe incluir todos los vehículos")
            chargers = set(self.charger_ids)
            for compatible in self.compatible_chargers.values():
                if not set(compatible) <= chargers:
                    raise ValueError("estación compatible inexistente o de tipo incorrecto")
        ops = self.operations
        for requested, known, label in (
            (ops.disabled_charger_ids, self.charger_ids, "disabled_charger_ids"),
            (ops.charging_power_kw_by_station, self.charger_ids, "charging_power_kw_by_station"),
            (ops.service_seconds_by_customer, self.customer_ids, "service_seconds_by_customer"),
            (ops.customer_time_windows, self.customer_ids, "customer_time_windows"),
        ):
            if set(requested) - set(known):
                raise ValueError(f"{label}: IDs desconocidos {sorted(set(requested) - set(known))}")
        if ops.timing_enabled:
            if ops.assumed_speed_kph is None and any(
                arc.travel_time_seconds is None for arc in self.arcs
            ):
                raise ValueError("Faltan travel_time_seconds; proporcionar assumed_speed_kph explícita")
            if not ops.include_charging_time and any(
                self.chargers_for(k) for k in self.vehicle_ids
            ):
                raise ValueError(
                    "El escenario temporal requiere include_charging_time mientras permita recargas"
                )
        if ops.include_charging_time:
            for station in {f for k in self.vehicle_ids for f in self.chargers_for(k)}:
                power = ops.charging_power(station)
                if power is None:
                    raise ValueError(f"Falta potencia efectiva configurada para {station}")
                reported = next(n.max_power_kw for n in self.nodes if n.node_id == station)
                if reported is not None and power > reported:
                    raise ValueError(f"{station}: potencia configurada supera max_power_kw reportado")
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
            return [
                f for f in self.compatible_chargers[vehicle_id]
                if f not in self.operations.disabled_charger_ids
            ]
        connectors = set(self.parameters.vehicle_connector_types)
        return [
            node.node_id
            for node in self.nodes
            if node.node_type == "charger" and connectors.intersection(node.connector_types)
            and node.node_id not in self.operations.disabled_charger_ids
        ]


class SolverConfig(Contract):
    """Recursos de resolución, independientes de los parámetros físicos."""

    solver: Literal["auto", "gurobi", "scip", "gcg", "scip-routes"] = "scip-routes"
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
    warm_start: Literal["not_requested", "submitted", "unsupported"] = "not_requested"
    incumbent_source: Literal["solver", "provided_incumbent"] | None = None


class RouteStep(Contract):
    """Una posición r del PDF, incluida la posición terminal sin salida."""

    position: int = Field(ge=0)
    node_id: str
    battery_arrival_kwh: float
    charged_to_battery_kwh: float = 0.0
    battery_departure_kwh: float
    delivered_visit_ids: list[str] = Field(default_factory=list)
    next_node_id: str | None = None
    arc_id: str | None = None
    predicted_arc_energy_kwh: float | None = None
    effective_arc_energy_kwh: float | None = None
    arrival_seconds: float | None = Field(default=None, ge=0)
    service_start_seconds: float | None = Field(default=None, ge=0)
    departure_seconds: float | None = Field(default=None, ge=0)
    service_duration_seconds: float | None = Field(default=None, ge=0)
    charging_duration_seconds: float | None = Field(default=None, ge=0)
    travel_time_seconds: float | None = Field(default=None, ge=0)


class VehicleRoute(Contract):
    """Recorrido completo, conservando posiciones para auditar el modelo."""

    vehicle_id: str
    steps: list[RouteStep]
    net_energy_kwh: float
    duration_seconds: float | None = Field(default=None, ge=0)


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
    solution_source: Literal["solver", "initial_solution", "heuristic"] | None = None
    search: dict[str, Any] | None = None


def finite_or_none(value: Any) -> float | None:
    """Convertir cotas infinitas/no disponibles del solver a null JSON."""
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        return None
    return numeric if isfinite(numeric) else None
