"""Preprocesamiento exacto por eliminación de intersecciones.

Conserva servicios y alternativas de batería/tiempo. Una intersección se
elimina componiendo cada entrada con cada salida; las alternativas dominadas
se pueden quitar. Si la eliminación produce demasiado trabajo, se conserva
la intersección. El presupuesto nunca trunca un catálogo de caminos ni limita
los recorridos: el pricing explora el grafo equivalente que quede.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import defaultdict
from dataclasses import dataclass
from math import isfinite, ulp
from pathlib import Path
from time import monotonic

from ev_routing.contracts import Arc, BatteryProfile, Operations, ProblemInstance
from ev_routing.operations import arc_energy, travel_seconds
from ev_routing.service_graph import (
    PathArchive,
    RoadPath,
    build_service_graph,
    check_service_context,
    fingerprint,
)

RESOURCE_REPRESENTATION = "resource_paths"
PREPROCESSOR_VERSION = 4


def compose_profiles(
    first: BatteryProfile, second: BatteryProfile, capacity: float,
) -> BatteryProfile | None:
    """Componer dominios y F2(F1(b)); no sumar únicamente energía neta."""
    if first.maximum_arrival_kwh < second.minimum_departure_kwh:
        return None
    lower = max(
        first.minimum_departure_kwh,
        second.minimum_departure_kwh + first.consumption_kwh,
    )
    if lower > capacity:
        return None
    return BatteryProfile(
        consumption_kwh=first.consumption_kwh + second.consumption_kwh,
        minimum_departure_kwh=lower,
        maximum_arrival_kwh=min(
            first.maximum_arrival_kwh - second.consumption_kwh,
            second.maximum_arrival_kwh,
        ),
    )


def profile_dominates(first: BatteryProfile, second: BatteryProfile, capacity: float) -> bool:
    """Dominancia para TODO el dominio del segundo perfil, sin tolerancia.

    La diferencia de dos funciones min(b-E,U) es monótona: sus pendientes
    difieren solo entre sus dos quiebres. Basta comprobar ambos extremos.
    """
    if first.minimum_departure_kwh > second.minimum_departure_kwh:
        return False
    return all(
        min(b - first.consumption_kwh, first.maximum_arrival_kwh)
        >= min(b - second.consumption_kwh, second.maximum_arrival_kwh)
        for b in (second.minimum_departure_kwh, capacity)
    )


@dataclass(frozen=True)
class _Connection:
    source: str
    target: str
    profile: BatteryProfile
    seconds: float | None
    nodes: tuple[str, ...]
    nominal_energy: float
    distance: float


def _contract(
    road: ProblemInstance, options: Operations, *, max_pair_expansions: int,
    preprocessing_seconds: float,
) -> tuple[ProblemInstance, PathArchive]:
    started = monotonic()
    capacity, reserve = road.parameters.battery_capacity_kwh, road.parameters.reserve_kwh
    services = {n.node_id for n in road.nodes if n.node_type != "junction"}
    live_nodes = {n.node_id for n in road.nodes}
    connections: dict[int, _Connection] = {}
    incoming, outgoing, pairs = defaultdict(set), defaultdict(set), defaultdict(set)
    heap, versions = [], defaultdict(int)
    next_id = dominated = infeasible = contracted = generated = 0
    roundoff_guard = 8 * ulp(capacity)
    roundoff_nodes: set[str] = set()
    # No plazo -> el tiempo no restringe ni forma parte del objetivo lexicográfico.
    constrain_time = options.max_route_seconds is not None
    identity = BatteryProfile(
        consumption_kwh=0, minimum_departure_kwh=reserve, maximum_arrival_kwh=capacity,
    )

    def remove(index):
        edge = connections.pop(index)
        outgoing[edge.source].remove(index)
        incoming[edge.target].remove(index)
        pairs[edge.source, edge.target].remove(index)

    def dominates(a, b):
        return (
            (not constrain_time or a.seconds <= b.seconds)
            and profile_dominates(a.profile, b.profile, capacity)
        )

    def insert(edge):
        nonlocal next_id, dominated
        if edge.source == edge.target and profile_dominates(identity, edge.profile, capacity):
            dominated += 1
            return
        alternatives = pairs[edge.source, edge.target]
        if any(dominates(connections[i], edge) for i in alternatives):
            dominated += 1
            return
        for index in list(alternatives):
            if dominates(edge, connections[index]):
                remove(index)
                dominated += 1
        index, next_id = next_id, next_id + 1
        connections[index] = edge
        outgoing[edge.source].add(index)
        incoming[edge.target].add(index)
        alternatives.add(index)

    def enqueue(node):
        if node in services or node not in live_nodes:
            return
        versions[node] += 1
        # Un ciclo regenerativo útil no se elimina: queda disponible al pricing.
        if pairs[node, node]:
            return
        work = len(incoming[node]) * len(outgoing[node])
        if work <= max_pair_expansions:
            heapq.heappush(heap, (work, node, versions[node]))

    for arc in road.arcs:
        energy = arc_energy(arc, options)
        lower = max(reserve, reserve + energy)
        if lower > capacity:
            infeasible += 1
            continue  # Ni siquiera una batería llena puede recorrer esta calle.
        insert(_Connection(
            arc.from_node_id, arc.to_node_id,
            BatteryProfile(
                consumption_kwh=energy, minimum_departure_kwh=lower,
                maximum_arrival_kwh=min(capacity, capacity - energy),
            ),
            travel_seconds(arc, options) if options.timing_enabled else arc.travel_time_seconds,
            (arc.from_node_id, arc.to_node_id), arc.energy_kwh, arc.distance_m,
        ))
    for node in sorted(live_nodes):
        enqueue(node)
    while heap and monotonic() - started < preprocessing_seconds:
        _, node, version = heapq.heappop(heap)
        if node not in live_nodes or versions[node] != version:
            continue
        before, after = sorted(incoming[node]), sorted(outgoing[node])
        neighbors = {
            connections[i].source for i in before
        } | {connections[i].target for i in after}
        # La sustitución se termina como unidad; no devolver medio nodo contraído.
        candidates = []
        ambiguous = False
        node_infeasible = 0
        for first_id in before:
            first = connections[first_id]
            for second_id in after:
                second = connections[second_id]
                # No decidir factibilidad en una frontera afectada por redondeo
                # de sumas/restas agregadas. Retener el nodo preserva sus
                # transiciones originales, sin relajar ni descartar etiquetas.
                if (
                    abs(first.profile.maximum_arrival_kwh - second.profile.minimum_departure_kwh)
                    <= roundoff_guard
                    or abs(max(
                        first.profile.minimum_departure_kwh,
                        second.profile.minimum_departure_kwh + first.profile.consumption_kwh,
                    ) - capacity) <= roundoff_guard
                ):
                    ambiguous = True
                    break
                profile = compose_profiles(first.profile, second.profile, capacity)
                seconds = (
                    first.seconds + second.seconds
                    if first.seconds is not None and second.seconds is not None else None
                )
                if profile is None or (
                    constrain_time and seconds > options.max_route_seconds
                ):
                    node_infeasible += 1
                    continue
                candidates.append(_Connection(
                    first.source, second.target, profile, seconds,
                    first.nodes + second.nodes[1:],
                    first.nominal_energy + second.nominal_energy,
                    first.distance + second.distance,
                ))
            if ambiguous:
                break
        if ambiguous:
            roundoff_nodes.add(node)
            continue
        for index in set(before) | set(after):
            remove(index)
        live_nodes.remove(node)
        roundoff_nodes.discard(node)
        contracted += 1
        infeasible += node_infeasible
        generated += len(candidates)
        for edge in candidates:
            insert(edge)
        for neighbor in sorted(neighbors):
            enqueue(neighbor)
    arcs, paths = [], []
    for index, edge in sorted(connections.items()):
        arc_id = f"path_{index}"
        arcs.append(Arc(
            from_node_id=edge.source, to_node_id=edge.target, arc_id=arc_id,
            battery_profile=edge.profile, energy_kwh=edge.nominal_energy,
            distance_m=edge.distance,
            travel_time_seconds=edge.seconds,
            source_id="resource_path",
        ))
        paths.append(RoadPath(
            from_node_id=edge.source, to_node_id=edge.target,
            arc_id=arc_id, node_ids=list(edge.nodes),
        ))
    source_hash = fingerprint(road)
    compact = ProblemInstance(
        schema_version="1.1", name=f"{road.name}-resource-paths",
        nodes=[n for n in road.nodes if n.node_id in live_nodes], arcs=arcs,
        parameters=road.parameters, operations=options,
        compatible_chargers=road.compatible_chargers,
        provenance={
            "representation": {
                "kind": RESOURCE_REPRESENTATION, "preprocessor_version": PREPROCESSOR_VERSION,
                "road_instance_sha256": source_hash,
                "original_node_count": len(road.nodes), "original_arc_count": len(road.arcs),
                "original_road_movement_limit": road.parameters.movement_limit,
                "movement_unit": "resource_path", "movement_limit_used": None,
                "shortest_path_algorithm": "profile_vertex_elimination",
                "road_optimum_preserved": True,
                "optimality_scope": (
                    "Conserva el óptimo vial sin H para este escenario: perfiles exactos, "
                    "dominancia y todas las intersecciones no eliminadas. "
                    "La optimalidad todavía requiere completar el pricing y ambas fases."
                ),
                "contracted_junctions": contracted,
                "retained_junctions": len(live_nodes - services),
                "roundoff_retained_junctions": len(roundoff_nodes & live_nodes),
                "dominated_connections": dominated, "infeasible_connections": infeasible,
                "generated_connections": generated, "max_pair_expansions": max_pair_expansions,
                "preprocessing_budget_seconds": preprocessing_seconds,
                "budget_reached": bool(heap), "construction_seconds": monotonic() - started,
                "assumptions": [
                    "Tiempos constantes, espera sin consumo, recargas parciales.",
                    "El perfil aplica el margen una vez a cada descarga vial.",
                    "Solo se eliminan intersecciones sin actividades; servicios conservados.",
                    "Los ciclos regenerativos útiles permanecen disponibles.",
                    "El presupuesto conserva nodos, nunca descarta alternativas pendientes.",
                ],
            },
            "source_provenance": road.provenance,
        },
    )
    return compact, PathArchive(
        road_instance_sha256=source_hash, service_instance_sha256=fingerprint(compact), paths=paths,
    )


def prepare_service_graph(
    road: ProblemInstance, *, operations: Operations | None = None,
    max_pair_expansions: int = 64, preprocessing_seconds: float = 10,
    cache_directory: str | Path | None = None,
) -> tuple[ProblemInstance, PathArchive]:
    """Dijkstra certificado cuando basta; eliminación exacta en los demás casos.

    Los límites solo eligen dónde parar de comprimir. No fijan k caminos, H,
    etiquetas, SoC ni un error de aproximación.
    """
    if isinstance(max_pair_expansions, bool) or not isinstance(max_pair_expansions, int) or max_pair_expansions < 0:
        raise ValueError("max_pair_expansions debe ser un entero no negativo")
    if not isfinite(preprocessing_seconds) or preprocessing_seconds < 0:
        raise ValueError("preprocessing_seconds debe ser finito y no negativo")
    if road.provenance.get("representation", {}).get("kind") in {
        RESOURCE_REPRESENTATION, "service_paths_nonnegative",
    }:
        raise ValueError("La entrada debe ser la red vial original")
    options = operations if operations is not None else road.operations
    same_scenario = options == road.operations
    scenario = road if same_scenario else ProblemInstance.model_validate({**dict(road), "operations": options})

    def key_for(source_hash):
        request = json.dumps({
            "version": PREPROCESSOR_VERSION, "road": source_hash,
            "operations": options.model_dump(mode="json"),
            "max_pair_expansions": max_pair_expansions, "preprocessing_seconds": preprocessing_seconds,
        }, sort_keys=True).encode()
        return hashlib.sha256(request).hexdigest()

    # Sin caché, el constructor ya calcula la huella vial: reutilizarla evita
    # serializar repetidamente redes de cientos de miles de arcos.
    source_hash = fingerprint(road) if cache_directory is not None else None
    cache_key = key_for(source_hash) if source_hash is not None else None
    cache_file = Path(cache_directory) / f"{cache_key}.json" if cache_directory is not None else None
    if cache_file is not None and cache_file.exists():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        compact = ProblemInstance.model_validate(saved["instance"])
        archive = PathArchive.model_validate(saved["archive"])
        check_service_context(compact, road, archive)
        if compact.operations != options:
            raise ValueError("El escenario de la caché no coincide")
        compact.provenance["preprocessing_cache"] = {"key": cache_key, "hit": True}
        archive.service_instance_sha256 = fingerprint(compact)
        return compact, archive
    if all(a.energy_kwh >= 0 for a in road.arcs) and options.max_route_seconds is None:
        compact, archive = build_service_graph(scenario, road.parameters.movement_limit)
        source_hash = source_hash or (
            archive.road_instance_sha256 if same_scenario else fingerprint(road)
        )
        archive.road_instance_sha256 = source_hash
        compact.provenance["source_provenance"] = road.provenance
        compact.provenance["representation"].update({
            "road_instance_sha256": source_hash,
            "road_optimum_preserved": True,
            "optimality_scope": (
                "Conserva el óptimo vial sin H bajo consumos no negativos, constantes "
                "y sin plazo: reducción por mínima energía verificada."
            ),
        })
    else:
        compact, archive = _contract(
            road, options, max_pair_expansions=max_pair_expansions,
            preprocessing_seconds=preprocessing_seconds,
        )
        source_hash = archive.road_instance_sha256
    cache_key = cache_key or key_for(source_hash)
    compact.provenance["preprocessing_cache"] = {"key": cache_key, "hit": False}
    archive.service_instance_sha256 = fingerprint(compact)
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        # Un solo archivo vincula ambos snapshots. replace evita una caché parcial.
        from uuid import uuid4

        temporary = cache_file.with_suffix(f".{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({
                "instance": compact.model_dump(mode="json"),
                "archive": archive.model_dump(mode="json"),
            }, allow_nan=False, separators=(",", ":")), encoding="utf-8")
            temporary.replace(cache_file)
        finally:
            temporary.unlink(missing_ok=True)
    return compact, archive
