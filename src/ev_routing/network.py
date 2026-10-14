"""Red vial dirigida de OSM o GraphML local, con accesos de servicio explícitos.

No se construye una matriz de distancias rectas entre clientes. Los únicos
segmentos rectos añadidos son accesos cortos, identificados en procedencia, desde
cada ubicación de servicio hasta su intersección vial más cercana.
"""

from __future__ import annotations

import hashlib
import json
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path
from typing import Any

import networkx as nx
from pyproj import CRS

from ev_routing.contracts import Arc, ModelParameters, Node, ProblemInstance
from ev_routing.energy import file_sha256
from ev_routing.inputs import load_instance, save_instance, validate_routing_nodes


def haversine_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Distancia de acceso entre coordenadas (latitud, longitud), en metros."""
    lat1, lon1, lat2, lon2 = map(radians, (*first, *second))
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_009 * asin(min(1.0, sqrt(value)))


def _geometry(data: dict, start: Node, end: Node) -> list[tuple[float, float]]:
    """El contrato de geometría usa (latitud, longitud), no (x, y) de Shapely."""
    line = data.get("geometry")
    if line is None:
        return [(start.latitude, start.longitude), (end.latitude, end.longitude)]
    if not hasattr(line, "coords"):
        raise ValueError("La geometría vial debe ser un LineString, no texto sin decodificar")
    points = [(float(y), float(x)) for x, y, *_ in line.coords]
    if len(points) < 2:
        raise ValueError("Una geometría vial necesita al menos dos coordenadas")
    if any(not isfinite(lat) or not isfinite(lon) or abs(lat) > 90 or abs(lon) > 180 for lat, lon in points):
        raise ValueError("Geometría vial con coordenadas inválidas")
    origin = (start.latitude, start.longitude)
    if haversine_m(origin, points[-1]) < haversine_m(origin, points[0]):
        points.reverse()
    return points


def _split_geometry(
    points: list[tuple[float, float]],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    lengths = [haversine_m(a, b) for a, b in zip(points, points[1:])]
    half = sum(lengths) / 2
    walked = 0.0
    for index, length in enumerate(lengths):
        if walked + length >= half:
            fraction = (half - walked) / length if length else 0.0
            a, b = points[index], points[index + 1]
            middle = (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))
            return [*points[: index + 1], middle], [middle, *points[index + 1 :]]
        walked += length
    raise ValueError("No se pudo subdividir la geometría")


def build_instance_from_graph(
    graph: nx.DiGraph,
    nodes: list[Node],
    parameters: ModelParameters,
    energy_rate_kwh_per_km: float,
    *,
    max_snap_distance_m: float = 100.0,
    name: str = "instance",
    provenance: dict[str, Any] | None = None,
) -> ProblemInstance:
    """Conservar calles, sentidos y paralelos de una red EPSG:4326.

    Cada servicio recibe su propio nodo y dos arcos de acceso. Son un supuesto
    operacional explícito, limitado por max_snap_distance_m; no se ha acreditado
    acceso vehicular privado por el mero hecho de estar cerca de una calle.
    Los paralelos y autoarcos viales se subdividen para el contrato (i,j) del PDF.
    """
    validate_routing_nodes(nodes)
    if not graph.is_directed():
        raise ValueError("La red debe ser dirigida; no se inventan sentidos de circulación")
    if not graph.nodes:
        raise ValueError("La red vial está vacía")
    if not graph.graph.get("crs") or CRS.from_user_input(graph.graph["crs"]).to_epsg() != 4326:
        raise ValueError("La red debe estar en EPSG:4326; reproyectar antes de importarla")
    if not isfinite(energy_rate_kwh_per_km) or energy_rate_kwh_per_km <= 0:
        raise ValueError("energy_rate_kwh_per_km debe ser finito y positivo")
    if not isfinite(max_snap_distance_m) or max_snap_distance_m < 0:
        raise ValueError("max_snap_distance_m debe ser finito y no negativo")
    used = {node.node_id for node in nodes}

    def allocate(preferred: str) -> str:
        candidate, suffix = preferred, 1
        while candidate in used:
            candidate = f"{preferred}#{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    road_nodes: dict[Any, Node] = {}
    for key, data in sorted(graph.nodes(data=True), key=lambda pair: str(pair[0])):
        if "x" not in data or "y" not in data:
            raise ValueError(f"Intersección {key!r} sin coordenadas x/y")
        road_nodes[key] = Node(
            node_id=allocate(f"osm:{key}"),
            node_type="junction",
            latitude=data["y"],
            longitude=data["x"],
        )
    result_nodes = [*nodes, *road_nodes.values()]
    arcs: list[Arc] = []
    source_edges = (
        list(graph.edges(keys=True, data=True))
        if graph.is_multigraph()
        else [(u, v, 0, data) for u, v, data in graph.edges(data=True)]
    )
    multiplicity: dict[tuple, int] = {}
    for u, v, _, _ in source_edges:
        multiplicity[u, v] = multiplicity.get((u, v), 0) + 1
    subdivided_edges = 0
    fingerprint_edges = []
    for u, v, key, data in sorted(source_edges, key=lambda item: tuple(map(str, item[:3]))):
        length = float(data.get("length", float("nan")))
        if not isfinite(length) or length < 0:
            raise ValueError(f"Arco {(u, v, key)!r} sin longitud finita no negativa")
        start, end = road_nodes[u], road_nodes[v]
        points = _geometry(data, start, end)
        source_id = f"osm:{u}:{v}:{key}:way={data.get('osmid', '')}"
        fingerprint_edges.append([str(u), str(v), str(key), length, points, source_id])
        if u == v or multiplicity[u, v] > 1:
            first, second = _split_geometry(points)
            middle = Node(
                node_id=allocate(f"edge:{u}:{v}:{key}"),
                node_type="junction",
                latitude=first[-1][0],
                longitude=first[-1][1],
            )
            result_nodes.append(middle)
            subdivided_edges += 1
            parts = [(start, middle, first, length / 2), (middle, end, second, length / 2)]
        else:
            parts = [(start, end, points, length)]
        for first_node, second_node, geometry, distance in parts:
            arcs.append(
                Arc(
                    from_node_id=first_node.node_id,
                    to_node_id=second_node.node_id,
                    distance_m=distance,
                    energy_kwh=distance * energy_rate_kwh_per_km / 1000,
                    geometry=geometry,
                    source_id=source_id,
                )
            )
    snaps = []
    for service in nodes:
        position = (service.latitude, service.longitude)
        nearest, distance = min(
            (
                (junction, haversine_m(position, (junction.latitude, junction.longitude)))
                for junction in road_nodes.values()
            ),
            key=lambda pair: pair[1],
        )
        if distance > max_snap_distance_m:
            raise ValueError(
                f"{service.node_id}: acceso de {distance:.1f} m supera "
                f"max_snap_distance_m={max_snap_distance_m}; revisar cobertura/ubicación"
            )
        snaps.append(
            {
                "service_node_id": service.node_id,
                "junction_node_id": nearest.node_id,
                "access_distance_m": distance,
            }
        )
        for start, end in [(service, nearest), (nearest, service)]:
            arcs.append(
                Arc(
                    from_node_id=start.node_id,
                    to_node_id=end.node_id,
                    distance_m=distance,
                    energy_kwh=distance * energy_rate_kwh_per_km / 1000,
                    geometry=[(start.latitude, start.longitude), (end.latitude, end.longitude)],
                    source_id=f"assumed_access:{service.node_id}",
                )
            )
    directed = nx.DiGraph((arc.from_node_id, arc.to_node_id) for arc in arcs)
    depot = next(node.node_id for node in nodes if node.node_type == "base")
    round_trip_reachable = (nx.descendants(directed, depot) & nx.ancestors(directed, depot)) | {depot}
    details = {
        **(provenance or {}),
        "network": {
            "source": "directed_road_graph",
            "crs": "EPSG:4326",
            "road_graph_sha256": hashlib.sha256(
                json.dumps(
                    {
                        "nodes": [[str(key), node.latitude, node.longitude] for key, node in road_nodes.items()],
                        "edges": fingerprint_edges,
                    }, sort_keys=True, allow_nan=False
                ).encode()
            ).hexdigest(),
            "routing_nodes_sha256": hashlib.sha256(
                json.dumps([node.model_dump() for node in nodes], sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
            "original_road_node_count": len(road_nodes),
            "original_road_arc_count": len(source_edges),
            "source_graph_simplified": bool(graph.graph.get("simplified", False)),
            "subdivided_road_arc_count": subdivided_edges,
            "snapping": "nearest_junction_with_bidirectional_access_connectors",
            "max_snap_distance_m": max_snap_distance_m,
            "service_access": snaps,
            "round_trip_unreachable_service_ids": [
                node.node_id for node in nodes if node.node_id not in round_trip_reachable
            ],
        },
        "energy": {
            "model_type": "distance_only",
            "kwh_per_km": energy_rate_kwh_per_km,
            "regeneration_on_osm_arcs": False,
        },
        "assumptions": [
            "Los accesos rectos cortos son supuestos de acceso vehicular bidireccional, no calles OSM.",
            "No se agregan rutas entre servicios: se preservan los arcos dirigidos de la red.",
            "H cuenta calles, accesos y subdivisiones; una cota pequeña excluye recorridos.",
            "El estimador distancia-only es determinista y no representa perfiles de regeneración.",
            "La red representa el GraphML/descarga utilizado, sin verificar cierres viales actuales.",
        ],
    }
    return ProblemInstance(
        name=name, nodes=result_nodes, arcs=arcs, parameters=parameters, provenance=details
    )


def build_osm_instance(
    nodes: list[Node],
    parameters: ModelParameters,
    energy_rate_kwh_per_km: float,
    *,
    graphml_path: str | Path,
    allow_download: bool = False,
    bbox: tuple[float, float, float, float] | None = None,
    bbox_padding_m: float = 1500.0,
    max_snap_distance_m: float = 100.0,
    name: str = "instance",
) -> ProblemInstance:
    """Cargar GraphML o, solo con permiso explícito, descargar OSM para conducir.

    bbox usa (west, south, east, north), como OSMnx 2. El GraphML existente
    siempre se reutiliza; un bbox distinto no sobrescribe ni cambia esa caché.
    La descarga utiliza simplify=False para conservar los tramos viales.
    """
    validate_routing_nodes(nodes)
    path = Path(graphml_path)
    if not path.exists() and not allow_download:
        raise FileNotFoundError(
            f"No existe {path}; proporcionar GraphML local o activar allow_download explícitamente"
        )
    import osmnx as ox

    downloaded = False
    requested_bbox = bbox
    if path.exists():
        graph = ox.load_graphml(path)
    else:
        if bbox is None:
            if not isfinite(bbox_padding_m) or bbox_padding_m <= 0:
                raise ValueError("bbox_padding_m debe ser positivo y finito")
            latitudes = [node.latitude for node in nodes]
            longitudes = [node.longitude for node in nodes]
            latitude_pad = bbox_padding_m / 111_195
            longitude_pad = latitude_pad / max(0.01, cos(radians(sum(latitudes) / len(latitudes))))
            bbox = (
                min(longitudes) - longitude_pad, min(latitudes) - latitude_pad,
                max(longitudes) + longitude_pad, max(latitudes) + latitude_pad,
            )
        west, south, east, north = bbox
        if not all(isfinite(value) for value in bbox) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox debe ser (west,south,east,north) válido en EPSG:4326")
        if any(not (west <= node.longitude <= east and south <= node.latitude <= north) for node in nodes):
            raise ValueError("bbox no cubre todos los servicios")
        path.parent.mkdir(parents=True, exist_ok=True)
        original_cache_folder = ox.settings.cache_folder
        try:
            ox.settings.cache_folder = path.parent / "osm_http_cache"
            graph = ox.graph_from_bbox(
                bbox, network_type="drive", simplify=False, retain_all=True, truncate_by_edge=True
            )
        finally:
            ox.settings.cache_folder = original_cache_folder
        ox.save_graphml(graph, filepath=path)
        downloaded = True
    return build_instance_from_graph(
        graph, nodes, parameters, energy_rate_kwh_per_km,
        max_snap_distance_m=max_snap_distance_m, name=name,
        provenance={
            "graphml_path": str(path.resolve()),
            "graphml_sha256": file_sha256(path),
            "graphml_downloaded_this_run": downloaded,
            "download_bbox": list(bbox) if downloaded else None,
            "requested_bbox": list(requested_bbox) if requested_bbox is not None else None,
            "osm_attribution": "© OpenStreetMap contributors (ODbL)",
        },
    )


def load_road_graph(path: str | Path) -> ProblemInstance:
    """Los arcos firmados importados deben ser elementales; no se recalculan."""
    return load_instance(path)


def save_road_graph(instance: ProblemInstance, path: str | Path) -> None:
    save_instance(instance, path)
