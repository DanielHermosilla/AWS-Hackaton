"""Pruebas de la fuente de elevación eVED (src/evrp/elevacion/eved.py).

- Interfaz y degradación segura con grafos sintéticos (sin datos → suite normal).
- Agregación por mediana, radio, interpolación IDW/vecino.
- Caché por firma de grafo.
- Marcadas con @pytest.mark.datos: cobertura y rango real con data/eVED_EV.csv.
"""
import csv
from pathlib import Path

import networkx as nx
import pytest

from evrp.elevacion import FuenteElevacion
from evrp.elevacion.eved import FuenteEved

RAIZ = Path(__file__).resolve().parents[1]
CSV_EV = RAIZ / "data" / "eVED_EV.csv"


def _grafo(coords):
    """MultiDiGraph estilo osmnx: nodos con x (lon), y (lat)."""
    G = nx.MultiDiGraph()
    for nid, (lat, lon) in coords.items():
        G.add_node(nid, x=lon, y=lat)
    return G


def _csv_puntos(ruta, filas):
    """Escribe un CSV mínimo con las columnas que usa FuenteEved."""
    cols = ["Matched Latitude[deg]", "Matched Longitude[deg]", "Elevation Smoothed[m]"]
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for lat, lon, h in filas:
            w.writerow([lat, lon, h])


def test_implementa_interfaz():
    assert issubclass(FuenteEved, FuenteElevacion)
    assert FuenteEved.nombre == "eved"


def test_sin_puntos_degrada_a_plano(tmp_path):
    csvv = tmp_path / "vacio.csv"
    _csv_puntos(csvv, [])
    G = _grafo({1: (42.0, -83.0), 2: (42.001, -83.001)})
    f = FuenteEved(csvv, cache_dir=tmp_path / "c")
    alturas, meta = f.elevar(G)
    assert set(alturas) == {1, 2}
    assert all(v == 0.0 for v in alturas.values())
    assert meta["cobertura_directa"] == 0.0
    assert "aviso" in meta


def test_mediana_por_nodo_y_radio(tmp_path):
    # Dos puntos sobre el nodo 1 (medianos 10 y 30 -> mediana 20) y uno lejos (fuera de radio).
    csvv = tmp_path / "p.csv"
    _csv_puntos(csvv, [
        (42.0000, -83.0000, 10.0),
        (42.0000, -83.0000, 30.0),
        (42.5000, -83.5000, 999.0),   # a decenas de km: fuera del radio
    ])
    G = _grafo({1: (42.0, -83.0), 2: (42.001, -83.001)})
    f = FuenteEved(csvv, radio_m=50.0, interpolacion="vecino", cache_dir=tmp_path / "c")
    alturas, meta = f.elevar(G)
    assert alturas[1] == pytest.approx(20.0)   # mediana de {10,30}
    assert meta["directos"] == 1               # solo el nodo 1 tiene dato directo
    assert alturas[2] == pytest.approx(20.0)   # interpolado (vecino) desde el nodo 1
    assert meta["interpolados"] == 1


def test_idw_pondera_por_distancia(tmp_path):
    # Nodo 2 equidistante de dos observados (alturas 0 y 100) -> IDW ~ 50.
    csvv = tmp_path / "p.csv"
    _csv_puntos(csvv, [(42.0000, -83.0000, 0.0), (42.0020, -83.0000, 100.0)])
    G = _grafo({1: (42.0000, -83.0000), 3: (42.0020, -83.0000), 2: (42.0010, -83.0000)})
    f = FuenteEved(csvv, radio_m=30.0, interpolacion="idw", idw_k=2, cache_dir=tmp_path / "c")
    alturas, meta = f.elevar(G)
    assert meta["directos"] == 2
    assert alturas[2] == pytest.approx(50.0, abs=1.0)


def test_cache_por_firma(tmp_path):
    csvv = tmp_path / "p.csv"
    _csv_puntos(csvv, [(42.0, -83.0, 42.0)])
    G = _grafo({1: (42.0, -83.0), 2: (42.001, -83.001)})
    cache = tmp_path / "c"
    f = FuenteEved(csvv, radio_m=50.0, cache_dir=cache)
    a1, m1 = f.elevar(G)
    assert m1["desde_cache"] is False
    archivos = list(cache.glob("eved_*.npz"))
    assert len(archivos) == 1
    a2, m2 = f.elevar(G)
    assert m2["desde_cache"] is True
    assert a1 == a2


def test_aplicar_escribe_elevation(tmp_path):
    csvv = tmp_path / "p.csv"
    _csv_puntos(csvv, [(42.0, -83.0, 55.0)])
    G = _grafo({1: (42.0, -83.0)})
    FuenteEved(csvv, radio_m=50.0, cache_dir=tmp_path / "c").aplicar(G)
    assert G.nodes[1]["elevation"] == pytest.approx(55.0)


# ---- con datos reales -------------------------------------------------------
@pytest.mark.datos
@pytest.mark.skipif(not CSV_EV.exists(), reason="requiere data/eVED_EV.csv")
def test_cobertura_real_grafo_empaquetado(tmp_path):
    import gzip
    import shutil

    import osmnx as ox

    gz = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
    plano = tmp_path / "g.graphml"
    with gzip.open(gz, "rb") as a, open(plano, "wb") as b:
        shutil.copyfileobj(a, b)
    G = ox.load_graphml(plano)
    f = FuenteEved(CSV_EV, radio_m=120.0, interpolacion="idw", cache_dir=tmp_path / "c")
    alturas, meta = f.elevar(G)
    assert len(alturas) == G.number_of_nodes()
    assert meta["directos"] > 1000              # eVED cubre miles de nodos directamente
    assert meta["cobertura_directa"] > 0.1
    # Ann Arbor: altitudes plausibles ~230-330 m.
    assert 200 <= meta["altura_min_m"] <= 260
    assert 300 <= meta["altura_max_m"] <= 360
