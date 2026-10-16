"""Variante sobre ubicaciones de servicio con caminos viales precalculados.

No es la formulación del PDF sobre cada calle: H cuenta aquí traslados entre
servicios. Se conserva un camino mínimo de energía por par alcanzable. Solo
admite energías no negativas: así la batería decrece dentro de cada camino y
comprobar su extremo no oculta un déficit seguido de regeneración.

El archivo de caminos permite expandir el resultado y comprobarlo de nuevo
sobre las calles originales. No acredita optimalidad en el modelo vial original
ni cumplimiento de su H. No modifica ni sustituye ese modelo por defecto.
"""

from __future__ import annotations

import hashlib
from math import isclose
from numbers import Integral
from typing import Literal

import numpy as np
from pydantic import Field
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from ev_routing.contracts import (
    Arc,
    Contract,
    ProblemInstance,
    RouteStep,
    Solution,
    ValidationReport,
    VehicleRoute,
)
from ev_routing.operations import arc_energy, arc_key, schedule_solution, step_key, travel_seconds
from ev_routing.validation import validate_solution

REPRESENTATION = "service_paths_nonnegative"
SERVICE_REPRESENTATIONS = {REPRESENTATION, "resource_paths"}


class RoadPath(Contract):
    from_node_id: str
    to_node_id: str
    node_ids: list[str] = Field(min_length=2)
    arc_id: str | None = None


class PathArchive(Contract):
    """Vincula los caminos con dos snapshots concretos, sin depender de nombres."""

    schema_version: Literal["1.0"] = "1.0"
    road_instance_sha256: str
    service_instance_sha256: str
    paths: list[RoadPath]


def fingerprint(instance: ProblemInstance) -> str:
    """Huella reproducible de los valores normalizados del snapshot."""
    # Los campos opcionales nuevos no invalidan hashes de snapshots 1.0.
    legacy = all(a.arc_id is None and a.battery_profile is None for a in instance.arcs)
    # Un diccionario con un índice por arco hace cuadrática la exclusión en
    # Pydantic. __all__ mantiene el esquema original con costo lineal.
    excluded = {"arcs": {"__all__": {"arc_id", "battery_profile"}}} if legacy else None
    return hashlib.sha256(instance.model_dump_json(exclude=excluded).encode()).hexdigest()


def build_service_graph(
    road: ProblemInstance, service_movements: int
) -> tuple[ProblemInstance, PathArchive]:
    """Conservar TODOS los servicios y un camino vial mínimo por par alcanzable.

    Adapta la matriz CSR y Dijkstra de ``src/evrp/caminos.py`` en la rama
    codex/optimizacion-contraida, commit 2bac3ead47576a96de8175f38626ba647232b24c.
    No importa su modelo ni su solver. Procesa un origen de servicio por vez
    para no almacenar una matriz servicios × nodos viales de predecesores.
    Solo reconstruye los caminos entre servicios, conservando calles de costo
    cero y nodos aislados. Ver docs/service-graph.md para el alcance.
    """
    if isinstance(service_movements, bool) or not isinstance(service_movements, Integral):
        raise ValueError("service_movements debe ser un entero positivo")
    if service_movements < 1:
        raise ValueError("service_movements debe ser positivo")
    if road.provenance.get("representation", {}).get("kind") in SERVICE_REPRESENTATIONS:
        raise ValueError("La entrada debe ser la red vial original, no otra reducción")
    if any(arc.energy_kwh < 0 for arc in road.arcs):
        raise ValueError("Esta variante no admite energía negativa ni perfiles de regeneración")
    services = [node for node in road.nodes if node.node_type != "junction"]
    node_ids = [node.node_id for node in road.nodes]
    node_indices = {node_id: index for index, node_id in enumerate(node_ids)}
    # El contrato ya exige un arco por par dirigido; CSR no debe sumar paralelos.
    # Construir desde coordenadas dispersas conserva los ceros explícitos como
    # calles válidas, a diferencia de una matriz densa donde cero significa ausencia.
    graph = csr_matrix(
        (
            np.array([arc.energy_kwh for arc in road.arcs], dtype=float),
            (
                np.array([node_indices[arc.from_node_id] for arc in road.arcs], dtype=int),
                np.array([node_indices[arc.to_node_id] for arc in road.arcs], dtype=int),
            ),
        ),
        shape=(len(node_ids), len(node_ids)),
    )
    road_arcs = {(a.from_node_id, a.to_node_id): a for a in road.arcs}
    arcs, paths = [], []
    for source in services:
        source_index = node_indices[source.node_id]
        distances, predecessors = dijkstra(
            graph, directed=True, indices=source_index, return_predecessors=True
        )
        for target in services:
            target_index = node_indices[target.node_id]
            if target_index == source_index or not np.isfinite(distances[target_index]):
                continue  # Mantener el nodo aislado, sin inventarle un arco.
            sequence_indices = [target_index]
            while sequence_indices[-1] != source_index:
                parent = int(predecessors[sequence_indices[-1]])
                if parent < 0 or len(sequence_indices) >= len(node_ids):
                    raise ValueError("No se pudo reconstruir el camino mínimo de energía")
                sequence_indices.append(parent)
            sequence = [node_ids[index] for index in reversed(sequence_indices)]
            segments = [road_arcs[pair] for pair in zip(sequence, sequence[1:])]
            energy = sum(arc.energy_kwh for arc in segments)
            if not isclose(energy, distances[target_index], rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("El camino reconstruido no conserva su energía mínima")
            arcs.append(
                Arc(
                    from_node_id=source.node_id,
                    to_node_id=target.node_id,
                    energy_kwh=energy,
                    distance_m=sum(arc.distance_m for arc in segments),
                    travel_time_seconds=(
                        sum(travel_seconds(arc, road.operations) for arc in segments)
                        if road.operations.timing_enabled
                        or all(arc.travel_time_seconds is not None for arc in segments) else None
                    ),
                    source_id=f"service_path_{len(paths)}",
                )
            )
            paths.append(
                RoadPath(
                    from_node_id=source.node_id,
                    to_node_id=target.node_id,
                    node_ids=sequence,
                )
            )
    source_hash = fingerprint(road)
    compact = ProblemInstance(
        name=f"{road.name}-service-paths",
        nodes=services,
        arcs=arcs,
        parameters=road.parameters.model_copy(update={"movement_limit": int(service_movements)}),
        operations=road.operations,
        compatible_chargers=road.compatible_chargers,
        provenance={
            "representation": {
                "kind": REPRESENTATION,
                "movement_unit": "service_leg",
                "road_instance_sha256": source_hash,
                "original_road_movement_limit": road.parameters.movement_limit,
                "original_node_count": len(road.nodes),
                "original_arc_count": len(road.arcs),
                "shortest_path_algorithm": "scipy.sparse.csgraph.dijkstra",
                "path_weight": "energy_kwh",
                "dijkstra_source_count": len(services),
                "unreachable_ordered_service_pairs": len(services) * (len(services) - 1) - len(arcs),
                "optimality_scope": (
                    "Solo caminos precalculados y límite de traslados entre servicios. "
                    "No es un certificado del modelo vial original ni de su H."
                ),
                "assumptions": [
                    "Consumos no negativos; no se representan perfiles de regeneración.",
                    "Tiempos explícitos se suman; las opciones operacionales se configuran aparte.",
                    "El camino mínimo de energía no necesariamente es el más rápido.",
                    "Pasar por un servicio dentro de un camino no implica atenderlo ni cargar.",
                ],
            },
            "source_provenance": road.provenance,
        },
    )
    return compact, PathArchive(
        road_instance_sha256=source_hash,
        service_instance_sha256=fingerprint(compact),
        paths=paths,
    )


def check_service_context(
    compact: ProblemInstance, road: ProblemInstance, archive: PathArchive
) -> None:
    """Evitar validar caminos contra un problema o una batería distintos."""
    kind = compact.provenance.get("representation", {}).get("kind")
    if kind not in SERVICE_REPRESENTATIONS:
        raise ValueError("La instancia no declara la variante de caminos entre servicios")
    if fingerprint(road) != archive.road_instance_sha256:
        raise ValueError(
            "La red vial no coincide con el archivo de caminos. "
            "Si actualizaste el código o la red, regenera los archivos derivados con "
            "'ev-routing service-graph', conservando H y las opciones operacionales. "
            "No basta con cambiar el hash del archivo."
        )
    if fingerprint(compact) != archive.service_instance_sha256:
        raise ValueError(
            "La instancia de servicios no coincide con el archivo de caminos. "
            "Regenera conjuntamente instancia, caminos y solución inicial con "
            "'ev-routing service-graph', conservando H y las opciones operacionales."
        )
    if compact.parameters.model_dump(exclude={"movement_limit"}) != road.parameters.model_dump(
        exclude={"movement_limit"}
    ):
        raise ValueError("La reducción cambió parámetros físicos de la flota")
    if kind == "resource_paths":
        kept = {n.node_id for n in compact.nodes}
        if compact.nodes != [n for n in road.nodes if n.node_id in kept] or any(
            n.node_id not in kept for n in road.nodes if n.node_type != "junction"
        ):
            raise ValueError("La reducción debe conservar los servicios y solo nodos originales")
    elif compact.nodes != [node for node in road.nodes if node.node_type != "junction"]:
        raise ValueError("La reducción debe conservar todas las ubicaciones de servicio")
    if compact.compatible_chargers != road.compatible_chargers:
        raise ValueError("La reducción cambió la compatibilidad de cargadores")
    if kind == REPRESENTATION and any(a.energy_kwh < 0 for a in road.arcs):
        raise ValueError("Esta variante requiere consumos viales no negativos")
    pairs = [(path.from_node_id, path.to_node_id, path.arc_id) for path in archive.paths]
    if len(pairs) != len(set(pairs)) or set(pairs) != {
        arc_key(arc) for arc in compact.arcs
    }:
        raise ValueError("Faltan caminos, sobran o están duplicados")
    if kind == "resource_paths":
        _check_resource_profiles(compact, road, archive)


def _check_resource_profiles(compact, road, archive):
    """Auditar perfiles por prefijos viales, sin reutilizar su composición."""
    road_arcs = {(a.from_node_id, a.to_node_id): a for a in road.arcs}
    paths = {(p.from_node_id, p.to_node_id, p.arc_id): p.node_ids for p in archive.paths}
    kept = {n.node_id for n in compact.nodes}
    capacity, reserve = compact.parameters.battery_capacity_kwh, compact.parameters.reserve_kwh
    for arc in compact.arcs:
        sequence = paths[arc_key(arc)]
        if sequence[0] != arc.from_node_id or sequence[-1] != arc.to_node_id:
            raise ValueError("Extremos incorrectos del camino con recursos")
        if any(node in kept for node in sequence[1:-1]):
            raise ValueError("Un camino no puede ocultar una parada o intersección conservada")
        try:
            segments = [road_arcs[pair] for pair in zip(sequence, sequence[1:])]
        except KeyError as error:
            raise ValueError("El camino usa una calle inexistente") from error
        prefix = low = high = drawdown = 0.0
        for segment in segments:
            prefix += arc_energy(segment, compact.operations)
            high, low = max(high, prefix), min(low, prefix)
            drawdown = max(drawdown, prefix - low)
        profile = arc.battery_profile
        expected = (
            prefix, reserve + high, capacity - prefix + low,
            sum(a.energy_kwh for a in segments), sum(a.distance_m for a in segments),
        )
        actual = (
            profile.consumption_kwh, profile.minimum_departure_kwh,
            profile.maximum_arrival_kwh, arc.energy_kwh, arc.distance_m,
        )
        if drawdown > capacity - reserve + 1e-8 or any(
            not isclose(a, b, rel_tol=1e-9, abs_tol=1e-8) for a, b in zip(actual, expected)
        ):
            raise ValueError("El perfil de batería no coincide con sus calles y escenario")
        if compact.operations.timing_enabled and not isclose(
            travel_seconds(arc, compact.operations),
            sum(travel_seconds(a, compact.operations) for a in segments),
            rel_tol=1e-9, abs_tol=1e-7,
        ):
            raise ValueError("El tiempo del camino no coincide")


def expand_and_validate(
    compact: ProblemInstance, road: ProblemInstance, archive: PathArchive, solution: Solution,
    *, without_h: bool = False,
) -> tuple[Solution, ValidationReport, dict[str, int]]:
    """Reproducir cada calle, entrega y recarga de una solución compacta.

    El comprobador físico utiliza el H necesario para alojar la expansión.
    Los conteos originales se devuelven aparte: no se confunde esta comprobación
    con satisfacer el límite de movimientos de la instancia vial de entrada.
    Los snapshots nunca se modifican.
    """
    check_service_context(compact, road, archive)
    arc_lookup = {(a.from_node_id, a.to_node_id): a for a in road.arcs}
    compact_arcs = {arc_key(a): a for a in compact.arcs}
    path_lookup = {(p.from_node_id, p.to_node_id, p.arc_id): p.node_ids for p in archive.paths}
    routes, counts = [], {}
    for route in solution.routes:
        steps = []
        battery = road.parameters.initial_energy_kwh
        for step in route.steps[:-1]:
            pair = (step.node_id, step.next_node_id)
            if pair == (road.depot_id, road.depot_id) and step.arc_id is None:
                continue  # Quitar relleno artificial antes de contar calles.
            sequence = path_lookup[step_key(step)]
            if sequence[0] != pair[0] or sequence[-1] != pair[1]:
                raise ValueError(f"Extremos incorrectos del camino {pair}")
            try:
                segments = [arc_lookup[p] for p in zip(sequence, sequence[1:])]
            except KeyError as exc:
                raise ValueError(f"El camino {pair} usa una calle inexistente") from exc
            aggregate = compact_arcs[step_key(step)]
            if not isclose(sum(a.energy_kwh for a in segments), aggregate.energy_kwh, abs_tol=1e-7):
                raise ValueError(f"La energía del camino {pair} no coincide")
            if not isclose(sum(a.distance_m for a in segments), aggregate.distance_m, abs_tol=1e-5):
                raise ValueError(f"La distancia del camino {pair} no coincide")
            if compact.operations.timing_enabled and not isclose(
                sum(travel_seconds(a, compact.operations) for a in segments),
                travel_seconds(aggregate, compact.operations),
                rel_tol=1e-8, abs_tol=1e-5,
            ):
                raise ValueError(f"El tiempo del camino {pair} no coincide")
            for index, arc in enumerate(segments):
                charge = step.charged_to_battery_kwh if index == 0 else 0.0
                departure = battery + charge
                energy = arc_energy(arc, compact.operations)
                arrival = min(road.parameters.battery_capacity_kwh, departure - energy)
                steps.append(
                    RouteStep(
                        position=len(steps),
                        node_id=arc.from_node_id,
                        battery_arrival_kwh=battery,
                        charged_to_battery_kwh=charge,
                        battery_departure_kwh=departure,
                        delivered_visit_ids=step.delivered_visit_ids if index == 0 else [],
                        next_node_id=arc.to_node_id,
                        predicted_arc_energy_kwh=energy,
                        effective_arc_energy_kwh=departure - arrival,
                    )
                )
                battery = arrival
        counts[route.vehicle_id] = len(steps)
        steps.append(
            RouteStep(
                position=len(steps), node_id=road.depot_id,
                battery_arrival_kwh=battery, battery_departure_kwh=battery,
            )
        )
        routes.append(VehicleRoute(
            vehicle_id=route.vehicle_id, steps=steps, net_energy_kwh=route.net_energy_kwh
        ))
    horizon = max(1, max(counts.values(), default=0))
    for route in ([] if without_h else routes):
        while len(route.steps) < horizon + 1:
            last = route.steps[-1]
            last.next_node_id = road.depot_id
            last.predicted_arc_energy_kwh = last.effective_arc_energy_kwh = 0.0
            route.steps.append(RouteStep(
                position=len(route.steps), node_id=road.depot_id,
                battery_arrival_kwh=last.battery_arrival_kwh,
                battery_departure_kwh=last.battery_arrival_kwh,
            ))
    expanded = solution.model_copy(update={"routes": routes})
    audit_road = road.model_copy(update={
        "parameters": road.parameters if without_h else road.parameters.model_copy(
            update={"movement_limit": horizon},
        ),
        "operations": compact.operations,
    })
    expanded = schedule_solution(audit_road, expanded)
    return expanded, validate_solution(
        audit_road, expanded, enforce_movement_limit=not without_h,
    ), counts
