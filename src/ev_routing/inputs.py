"""Entradas CSV y JSON, sin completar silenciosamente datos físicos ausentes."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ev_routing.contracts import Node, ProblemInstance

ROUTING_COLUMNS = (
    "node_id",
    "node_type",
    "latitude",
    "longitude",
    "address",
    "network",
    "total_ports",
    "dc_fast_ports",
    "level2_ports",
    "connector_types",
    "max_power_kw",
)


def validate_routing_nodes(nodes: list[Node]) -> None:
    """Validar ubicaciones de servicio tanto desde CSV como desde formularios."""
    if not nodes:
        raise ValueError("La entrada no contiene nodos de servicio")
    seen: set[str] = set()
    for node in nodes:
        if not node.node_id.strip():
            raise ValueError("node_id no puede estar vacío")
        if node.node_id in seen:
            raise ValueError(f"node_id duplicado: {node.node_id}")
        seen.add(node.node_id)
        if node.node_type not in {"base", "visit", "charger"}:
            raise ValueError(f"Tipo de servicio inválido: {node.node_type}")
        if node.latitude is None or node.longitude is None:
            raise ValueError(f"Faltan coordenadas para {node.node_id}")
        ports = (node.total_ports, node.dc_fast_ports, node.level2_ports)
        if all(value is not None for value in ports) and ports[0] != ports[1] + ports[2]:
            raise ValueError(f"Puertos inconsistentes en {node.node_id}: total != DC + nivel 2")
        if node.node_type == "charger":
            if any(value is None for value in ports):
                raise ValueError(f"Faltan cantidades de puertos en cargador {node.node_id}")
            if not node.connector_types or node.max_power_kw is None:
                raise ValueError(f"Falta conector o potencia en cargador {node.node_id}")
    if sum(node.node_type == "base" for node in nodes) != 1:
        raise ValueError("Se requiere exactamente un nodo base")


def load_routing_nodes(path: str | Path) -> list[Node]:
    """Leer el contrato CSV de la hackatón (UTF-8, con o sin BOM).

    Se preservan los identificadores y las ubicaciones coincidentes: dos clientes
    en el mismo lugar siguen siendo dos entregas diferentes.
    """
    nodes: list[Node] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ValueError("El CSV contiene columnas duplicadas")
        missing = set(ROUTING_COLUMNS) - set(headers)
        unexpected = set(headers) - set(ROUTING_COLUMNS)
        if missing or unexpected:
            raise ValueError(
                f"Esquema CSV inválido; faltan={sorted(missing)}, sobran={sorted(unexpected)}"
            )
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Fila {line}: cantidad incorrecta de campos")
            values: dict = dict(row)
            values["node_type"] = row["node_type"].strip()
            values["connector_types"] = list(
                dict.fromkeys(part.strip() for part in row["connector_types"].split(";") if part.strip())
            )
            for column in (
                "latitude",
                "longitude",
                "total_ports",
                "dc_fast_ports",
                "level2_ports",
                "max_power_kw",
            ):
                values[column] = row[column].strip() or None
            try:
                nodes.append(Node.model_validate(values))
            except ValueError as exc:
                raise ValueError(f"Fila {line}, nodo {row['node_id']!r}: {exc}") from exc
    validate_routing_nodes(nodes)
    return nodes


def load_instance(path: str | Path) -> ProblemInstance:
    """Cargar una instancia completa con sus arcos y parámetros, sin inferencias."""
    return ProblemInstance.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))


def save_instance(instance: ProblemInstance, path: str | Path) -> None:
    """Exportar exactamente el contrato compartido (incluida su procedencia)."""
    # Revalidar también objetos modificados después de su construcción.
    instance = ProblemInstance.model_validate(instance.model_dump())
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(instance.model_dump(mode="json"), ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
