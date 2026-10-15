from typing import Dict, List, Optional

from .contracts import Arc, Network, Node, NodeType

# Re-export for convenience
RoadNetwork = Network


def build_network_from_arcs(nodes: List[Node], arcs: List[Arc], provenance: str = "provided") -> Network:
    node_ids = [n.node_id for n in nodes]
    return Network(nodes=node_ids, arcs=arcs, directed=True, provenance=provenance)


def validate_network(instance_nodes: List[str], network: Network) -> List[str]:
    return network.validate_against_nodes(instance_nodes)


def charger_compatibility(nodes: List[Node], vehicle_connector: Optional[str] = None) -> Dict[str, List[str]]:
    """Return chargers that expose at least one port (all compatible by default)."""
    chargers = [n.node_id for n in nodes if n.node_type == NodeType.CHARGER]
    return {"default": chargers}
