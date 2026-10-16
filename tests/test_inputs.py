import csv
import json

import pytest

from ev_routing.contracts import Arc, ModelParameters, Node, ProblemInstance
from ev_routing.inputs import ROUTING_COLUMNS, load_instance, load_routing_nodes, save_instance


def write_nodes(tmp_path, changes=None, *, bom=True):
    rows = [
        dict(node_id="BASE", node_type="base", latitude=42.0, longitude=-83.0),
        dict(node_id="V01", node_type="visit", latitude=42.0, longitude=-83.0),
        dict(
            node_id="C5", node_type="charger", latitude=42.01, longitude=-83.01,
            total_ports=2, dc_fast_ports=1, level2_ports=1,
            connector_types=" CCS ; CHAdeMO; CHAdeMO ", max_power_kw=50,
        ),
    ]
    if changes:
        changes(rows)
    path = tmp_path / "nodes.csv"
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROUTING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("bom", [True, False])
def test_csv_preserves_ids_colocated_visits_and_optional_metadata(tmp_path, bom):
    nodes = load_routing_nodes(write_nodes(tmp_path, bom=bom))
    assert [node.node_id for node in nodes] == ["BASE", "V01", "C5"]
    assert nodes[0].latitude == nodes[1].latitude
    assert nodes[0].max_power_kw is None
    assert nodes[2].connector_types == ["CCS", "CHAdeMO"]


@pytest.mark.parametrize(
    ("index", "field", "value", "message"),
    [
        (1, "node_id", "BASE", "duplicado"),
        (1, "node_id", "  ", "vacío"),
        (1, "latitude", 91, "latitude"),
        (1, "longitude", -181, "longitude"),
        (1, "latitude", "nan", "finite"),
        (1, "longitude", "", "latitude"),
        (1, "node_type", "store", "node_type"),
        (2, "total_ports", 8, "inconsistentes"),
        (2, "total_ports", 1.5, "integer"),
        (2, "max_power_kw", 0, "max_power_kw"),
        (2, "connector_types", "", "conector"),
        (2, "dc_fast_ports", "", "puertos"),
        (0, "node_type", "visit", "exactamente"),
        (1, "node_type", "base", "exactamente"),
    ],
)
def test_csv_rejects_actionable_invalid_inputs(tmp_path, index, field, value, message):
    path = write_nodes(tmp_path, lambda rows: rows[index].update({field: value}))
    with pytest.raises(ValueError, match=message):
        load_routing_nodes(path)


@pytest.mark.parametrize(
    "content",
    [
        "node_id,node_type,latitude,longitude\nB,base,42,-83\n",
        ",".join(ROUTING_COLUMNS) + ",node_id\n",
        ",".join(ROUTING_COLUMNS) + "\nB,base,42,-83\n",
    ],
)
def test_csv_rejects_missing_duplicate_headers_or_ragged_rows(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_routing_nodes(path)


def test_json_roundtrip_preserves_signed_arcs_parameters_and_provenance(tmp_path):
    instance = ProblemInstance(
        nodes=[Node(node_id="B", node_type="base"), Node(node_id="X", node_type="visit")],
        arcs=[
            Arc(from_node_id="B", to_node_id="X", energy_kwh=-0.1),
            Arc(from_node_id="X", to_node_id="B", energy_kwh=0.2),
        ],
        parameters=ModelParameters(movement_limit=8),
        provenance={"assumptions": ["synthetic graph"]},
    )
    path = tmp_path / "nested" / "instance.json"
    save_instance(instance, path)
    assert load_instance(path) == instance
    raw = json.loads(path.read_text())
    raw["arcs"][0]["to_node_id"] = "missing"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="inexistentes"):
        load_instance(path)


def test_json_rejects_nonfinite_energy(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        '{"nodes":[{"node_id":"B","node_type":"base"},{"node_id":"V","node_type":"visit"}],'
        '"arcs":[{"from_node_id":"B","to_node_id":"V","energy_kwh":NaN}]}'
    )
    with pytest.raises(ValueError, match="finite|finito"):
        load_instance(path)
