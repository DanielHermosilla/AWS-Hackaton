import networkx as nx
import pytest
from shapely.geometry import LineString

from ev_routing.contracts import ModelParameters, Node
from ev_routing.network import (
    build_instance_from_graph,
    build_osm_instance,
    load_road_graph,
    save_road_graph,
)


def road_graph():
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=-83.0, y=42.0)
    graph.add_node(2, x=-82.999, y=42.0)
    graph.add_node(3, x=-82.998, y=42.0)
    graph.add_edge(1, 2, length=100.0, osmid=1)
    graph.add_edge(2, 3, length=110.0, osmid=2)
    graph.add_edge(3, 1, length=200.0, osmid=3)
    return graph


def services():
    return [
        Node(node_id="B", node_type="base", latitude=42.0, longitude=-83.0),
        Node(node_id="V", node_type="visit", latitude=42.0, longitude=-82.999),
        Node(node_id="V2", node_type="visit", latitude=42.0, longitude=-82.999),
    ]


def build(graph=None, nodes=None, **kwargs):
    return build_instance_from_graph(
        graph if graph is not None else road_graph(),
        nodes if nodes is not None else services(),
        ModelParameters(movement_limit=30), 0.2, **kwargs
    )


def test_preserves_directed_streets_without_creating_all_pairs_shortcuts():
    instance = build()
    road_arcs = [arc for arc in instance.arcs if not arc.source_id.startswith("assumed_access:")]
    assert len(road_arcs) == 3
    assert {(a.from_node_id, a.to_node_id) for a in road_arcs} == {
        ("osm:1", "osm:2"), ("osm:2", "osm:3"), ("osm:3", "osm:1")
    }
    assert sum(a.distance_m for a in road_arcs) == 410
    assert sum(a.energy_kwh for a in road_arcs) == pytest.approx(0.082)
    assert not any(a.from_node_id == "V" and a.to_node_id == "V2" for a in instance.arcs)
    assert instance.customer_ids == ["V", "V2"]
    assert instance.provenance["network"]["round_trip_unreachable_service_ids"] == []


def test_parallel_edges_remain_independent_options_and_total_lengths_preserved():
    graph = road_graph()
    graph.add_edge(1, 2, length=150.0, osmid=4, geometry=LineString([(-83, 42), (-82.9995, 42.0002), (-82.999, 42)]))
    instance = build(graph)
    road = [arc for arc in instance.arcs if arc.source_id.startswith("osm:1:2:")]
    assert len(road) == 4
    assert sum(arc.distance_m for arc in road) == 250
    directed = nx.DiGraph((a.from_node_id, a.to_node_id) for a in road)
    paths = list(nx.all_simple_paths(directed, "osm:1", "osm:2"))
    assert len(paths) == 2 and all(len(path) == 3 for path in paths)
    assert instance.provenance["network"]["subdivided_road_arc_count"] == 2


def test_road_self_loop_preserved_by_subdivision_and_reversed_geometry_oriented():
    graph = road_graph()
    graph.add_edge(1, 1, length=20, osmid=9, geometry=LineString([(-83, 42), (-83.0001, 42), (-83, 42)]))
    graph[1][2][0]["geometry"] = LineString([(-82.999, 42), (-83, 42)])
    instance = build(graph)
    assert not any(a.from_node_id == a.to_node_id for a in instance.arcs)
    loop = [a for a in instance.arcs if "way=9" in a.source_id]
    assert len(loop) == 2 and sum(a.distance_m for a in loop) == 20
    outgoing = next(a for a in instance.arcs if a.from_node_id == "osm:1" and a.to_node_id == "osm:2")
    assert outgoing.geometry[0] == (42, -83)


def test_access_connector_distance_is_bounded_and_recorded():
    nodes = services()
    nodes[1] = nodes[1].model_copy(update={"latitude": 42.0001})
    instance = build(nodes=nodes, max_snap_distance_m=20)
    snap = instance.provenance["network"]["service_access"][1]
    assert 11 < snap["access_distance_m"] < 12
    access = [a for a in instance.arcs if a.source_id == "assumed_access:V"]
    assert len(access) == 2
    assert sum(a.distance_m for a in access) == pytest.approx(2 * snap["access_distance_m"])
    with pytest.raises(ValueError, match="V: acceso"):
        build(nodes=nodes, max_snap_distance_m=5)


def test_service_ids_cannot_collide_with_generated_junction_ids():
    nodes = services()
    nodes[1] = nodes[1].model_copy(update={"node_id": "osm:1"})
    instance = build(nodes=nodes)
    assert len({n.node_id for n in instance.nodes}) == len(instance.nodes)
    assert "osm:1" in instance.customer_ids


def test_unreachable_service_reported_without_inventing_a_reverse_street():
    graph = road_graph()
    graph.remove_edge(3, 1)
    instance = build(graph)
    assert instance.provenance["network"]["round_trip_unreachable_service_ids"] == ["V", "V2"]


@pytest.mark.parametrize("bad_rate", [0, -0.1, float("nan"), float("inf")])
def test_invalid_energy_rate_rejected(bad_rate):
    with pytest.raises(ValueError, match="energy_rate"):
        build_instance_from_graph(road_graph(), services(), ModelParameters(), bad_rate)


def test_undirected_projected_empty_and_missing_length_rejected():
    with pytest.raises(ValueError, match="dirigida"):
        build(nx.Graph(road_graph()))
    graph = road_graph()
    graph.graph["crs"] = "EPSG:3857"
    with pytest.raises(ValueError, match="EPSG"):
        build(graph)
    with pytest.raises(ValueError, match="vacía"):
        build(nx.MultiDiGraph(crs="EPSG:4326"))
    graph = road_graph()
    del graph[1][2][0]["length"]
    with pytest.raises(ValueError, match="longitud"):
        build(graph)


def test_default_never_downloads_missing_graph(tmp_path):
    with pytest.raises(FileNotFoundError, match="allow_download"):
        build_osm_instance(services(), ModelParameters(), 0.2, graphml_path=tmp_path / "absent.graphml")


def test_local_graphml_load_export_hash_and_provenance_without_network(tmp_path, monkeypatch):
    import osmnx as ox

    path = tmp_path / "road.graphml"
    ox.save_graphml(road_graph(), filepath=path)
    monkeypatch.setattr(ox, "graph_from_bbox", lambda *a, **k: pytest.fail("Unexpected download"))
    instance = build_osm_instance(
        services(), ModelParameters(movement_limit=40), 0.2, graphml_path=path,
        allow_download=True, bbox=(-84, 41, -82, 43)
    )
    assert instance.provenance["graphml_downloaded_this_run"] is False
    assert len(instance.provenance["graphml_sha256"]) == 64
    output = tmp_path / "instance.json"
    save_road_graph(instance, output)
    assert load_road_graph(output) == instance


def test_explicit_download_passes_drive_unsimplified_bbox_and_saves_cache(tmp_path, monkeypatch):
    import osmnx as ox

    calls = []

    def fake_download(bbox, **options):
        calls.append((bbox, options))
        return road_graph()

    monkeypatch.setattr(ox, "graph_from_bbox", fake_download)
    path = tmp_path / "cache" / "new.graphml"
    instance = build_osm_instance(
        services(), ModelParameters(), 0.2, graphml_path=path, allow_download=True,
        bbox=(-83.01, 41.99, -82.99, 42.01)
    )
    assert calls == [
        ((-83.01, 41.99, -82.99, 42.01), {"network_type": "drive", "simplify": False, "retain_all": True, "truncate_by_edge": True})
    ]
    assert path.exists()
    assert instance.provenance["graphml_downloaded_this_run"] is True
    assert instance.provenance["download_bbox"] == [-83.01, 41.99, -82.99, 42.01]


@pytest.mark.parametrize("bbox", [(-82, 41, -83, 43), (-85, 30, -84, 31)])
def test_download_rejects_invalid_or_noncovering_bbox_before_http(tmp_path, monkeypatch, bbox):
    import osmnx as ox

    monkeypatch.setattr(ox, "graph_from_bbox", lambda *a, **k: pytest.fail("Unexpected download"))
    with pytest.raises(ValueError, match="bbox"):
        build_osm_instance(
            services(), ModelParameters(), 0.2, graphml_path=tmp_path / "new.graphml",
            allow_download=True, bbox=bbox
        )
