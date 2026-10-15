"""Clientes sintéticos reproducibles sobre calles existentes, sin alterar su energía."""

from __future__ import annotations

import random

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from ev_routing.contracts import ProblemInstance
from ev_routing.service_graph import REPRESENTATION, fingerprint


def simulate_customers(
    road: ProblemInstance, total_customers: int, *, seed: int = 0,
) -> ProblemInstance:
    """Conservar clientes y cargadores; convertir intersecciones en nuevas entregas.

    Muestreo uniforme sin reemplazo dentro del rectángulo de los clientes fuente,
    restringido al componente fuertemente conexo del depósito. Esto acredita
    conectividad vial, no suficiencia de batería ni una distribución real de demanda.
    """
    if isinstance(total_customers, bool) or not isinstance(total_customers, int):
        raise ValueError("El total de clientes debe ser un entero")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("La semilla de simulación debe ser un entero no negativo")
    if road.provenance.get("representation", {}).get("kind") == REPRESENTATION:
        raise ValueError("La simulación requiere la red vial original, no el grafo de servicios")
    customers = [node for node in road.nodes if node.node_type == "visit"]
    if total_customers <= len(customers):
        raise ValueError(
            f"--simulate-customers debe superar los {len(customers)} clientes de la red fuente"
        )
    if not customers or any(node.latitude is None for node in customers):
        raise ValueError("Se requieren clientes fuente con coordenadas para delimitar la simulación")
    south, north = min(n.latitude for n in customers), max(n.latitude for n in customers)
    west, east = min(n.longitude for n in customers), max(n.longitude for n in customers)
    indices = {node.node_id: index for index, node in enumerate(road.nodes)}
    graph = csr_matrix((
        [1] * len(road.arcs),
        ([indices[a.from_node_id] for a in road.arcs],
         [indices[a.to_node_id] for a in road.arcs]),
    ), shape=(len(indices), len(indices)))
    _, labels = connected_components(graph, directed=True, connection="strong")
    depot_component = labels[indices[road.depot_id]]
    occupied = {(node.latitude, node.longitude) for node in road.nodes
                if node.node_type != "junction"}
    candidates = []
    # Orden estable por ID: la misma semilla no depende del orden del JSON.
    for node in sorted(road.nodes, key=lambda item: item.node_id):
        if (
            node.node_type != "junction" or node.latitude is None
            or labels[indices[node.node_id]] != depot_component
            or not (south <= node.latitude <= north and west <= node.longitude <= east)
            or (node.latitude, node.longitude) in occupied
        ):
            continue
        candidates.append(node.node_id)
        occupied.add((node.latitude, node.longitude))
    extra = total_customers - len(customers)
    if extra > len(candidates):
        raise ValueError(
            f"Se necesitan {extra} ubicaciones nuevas, pero solo hay {len(candidates)} "
            "nodos viales elegibles dentro del área y conectados al depósito"
        )
    selected = sorted(random.Random(seed).sample(candidates, extra))
    selected_set = set(selected)
    simulation = {
        "kind": "additional_customers_on_existing_road_nodes",
        "seed": seed, "original_customer_count": len(customers),
        "total_customer_count": total_customers, "added_customer_ids": selected,
        "candidate_count": len(candidates), "source_instance_sha256": fingerprint(road),
        "sampling": "uniform_without_replacement_by_node_in_depot_strong_component",
        "bounding_box": {"south": south, "north": north, "west": west, "east": east},
        "assumptions": [
            "Clientes adicionales sintéticos en nodos viales, no domicilios observados.",
            "Muestreo uniforme por nodo elegible, no por superficie ni población.",
            "Conectividad de ida y vuelta no garantiza factibilidad energética.",
            "Nuevos clientes heredan el tiempo de servicio común, sin ventanas inventadas.",
            "Calles, energías, flota, batería y cargadores conservan los valores fuente.",
        ],
    }
    # Construir otra instancia; no mutar nodos ni parámetros compartidos con la fuente.
    return ProblemInstance(**{
        **dict(road), "name": f"{road.name}-simulated-{total_customers}c-seed{seed}",
        "nodes": [node.model_copy(update={"node_type": "visit"})
                  if node.node_id in selected_set else node for node in road.nodes],
        "provenance": {**road.provenance, "simulation": simulation},
    })
