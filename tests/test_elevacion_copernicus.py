"""Pruebas de la fuente de elevación Copernicus DEM 30 m (src/evrp/elevacion/copernicus.py).

Niveles:
- Helpers de teselado (puros, sin red ni dependencias geo).
- Muestreo del raster con un dataset *fake* estilo rasterio (sin rasterio real).
- Degradación segura si falta ``rasterio`` (monkeypatch del import).
- Caché por firma de grafo.
- @pytest.mark.datos: tesela real N42/W084 descargada en .cache (requiere rasterio
  y acceso a S3; se salta si no están).
"""
import builtins
import importlib.util

import networkx as nx
import pytest

from evrp.elevacion import FuenteElevacion
from evrp.elevacion.copernicus import (
    FuenteCopernicus,
    _nombre_tesela,
    _teselas_para_bbox,
)

TIENE_RASTERIO = importlib.util.find_spec("rasterio") is not None


def _grafo(coords):
    """MultiDiGraph estilo osmnx: nodos con x (lon), y (lat)."""
    G = nx.MultiDiGraph()
    for nid, (lat, lon) in coords.items():
        G.add_node(nid, x=lon, y=lat)
    return G


# ---- interfaz ---------------------------------------------------------------
def test_implementa_interfaz():
    assert issubclass(FuenteCopernicus, FuenteElevacion)
    assert FuenteCopernicus.nombre == "copernicus"


# ---- teselado ---------------------------------------------------------------
def test_nombre_tesela_ann_arbor():
    # Ann Arbor: lat ~42.3 N, lon ~-83.7 -> tesela SO (42, -84).
    assert _nombre_tesela(42, -84) == "Copernicus_DSM_COG_10_N42_00_W084_00_DEM"


def test_nombre_tesela_cuadrantes():
    assert _nombre_tesela(0, 6) == "Copernicus_DSM_COG_10_N00_00_E006_00_DEM"
    assert _nombre_tesela(-34, -59) == "Copernicus_DSM_COG_10_S34_00_W059_00_DEM"


def test_teselas_para_bbox_mapa_empaquetado():
    # bbox del mapa empaquetado: lat 42.17-42.38, lon -83.95..-83.55 -> una tesela.
    ts = _teselas_para_bbox(42.17, 42.38, -83.95, -83.55)
    assert ts == [(42, -84)]


def test_teselas_para_bbox_cruza_meridianos():
    # Una caja que cruza dos grados en lon y lat pide 4 teselas.
    ts = set(_teselas_para_bbox(42.9, 43.1, -84.1, -83.9))
    assert ts == {(42, -85), (42, -84), (43, -85), (43, -84)}


# ---- muestreo del raster con un dataset fake --------------------------------
class _AffineInv:
    """Inversa de un affine simple: (col, fila) = inv * (x, y)."""

    def __init__(self, x0, y0, px, py):
        self.x0, self.y0, self.px, self.py = x0, y0, px, py

    def __mul__(self, xy):
        import numpy as np

        x, y = xy
        col = (np.asarray(x) - self.x0) / self.px
        fila = (np.asarray(y) - self.y0) / self.py
        return col, fila


class _Affine:
    def __init__(self, x0, y0, px, py):
        self.x0, self.y0, self.px, self.py = x0, y0, px, py

    def __invert__(self):
        return _AffineInv(self.x0, self.y0, self.px, self.py)


class _DSFake:
    """Mínimo dataset estilo rasterio: read(1), transform, nodata, shape."""

    def __init__(self, arr, x0, y0, px, py, nodata=None):
        self._arr = arr
        self.transform = _Affine(x0, y0, px, py)
        self.nodata = nodata
        self.shape = arr.shape

    def read(self, _b):
        return self._arr


def test_muestreo_vecino_y_bilineal():
    import numpy as np

    # Raster 2x2: esquinas (lon0,lat0) arriba-izq, px=1 lon, py=-1 lat (y decrece hacia abajo).
    # valores: [[0,100],[200,300]]  (fila 0 = lat alto)
    arr = np.array([[0.0, 100.0], [200.0, 300.0]], dtype="float32")
    ds = _DSFake(arr, x0=0.0, y0=1.0, px=1.0, py=-1.0)
    # Punto en el centro (col 0.5, fila 0.5): lon=0.5, lat=0.5.
    nlat = np.array([0.5]); nlon = np.array([0.5])
    vals_b, mask_b = FuenteCopernicus._muestrear_raster(ds, nlat, nlon, bilineal=True)
    assert mask_b[0]
    assert vals_b[0] == pytest.approx((0 + 100 + 200 + 300) / 4)  # 150
    vals_v, mask_v = FuenteCopernicus._muestrear_raster(ds, nlat, nlon, bilineal=False)
    assert mask_v[0]
    # round(0.5)=0 en numpy (banker's) -> pixel (fila0,col0)=0
    assert vals_v[0] in (0.0, 100.0, 200.0, 300.0)


def test_muestreo_fuera_de_raster():
    import numpy as np

    arr = np.array([[10.0, 20.0], [30.0, 40.0]], dtype="float32")
    ds = _DSFake(arr, x0=0.0, y0=1.0, px=1.0, py=-1.0)
    nlat = np.array([0.5, 50.0]); nlon = np.array([0.5, 50.0])  # 2º punto fuera
    vals, mask = FuenteCopernicus._muestrear_raster(ds, nlat, nlon, bilineal=True)
    assert mask[0] and not mask[1]


def test_muestreo_respeta_nodata():
    import numpy as np

    arr = np.array([[-9999.0, 100.0], [200.0, 300.0]], dtype="float32")
    ds = _DSFake(arr, x0=0.0, y0=1.0, px=1.0, py=-1.0, nodata=-9999.0)
    nlat = np.array([1.0]); nlon = np.array([0.0])  # cae en el nodata (fila0,col0)
    vals, mask = FuenteCopernicus._muestrear_raster(ds, nlat, nlon, bilineal=False)
    assert not mask[0]


# ---- degradación segura sin rasterio ---------------------------------------
def test_sin_rasterio_degrada_a_plano(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(nombre, *a, **k):
        if nombre == "rasterio" or nombre.startswith("rasterio."):
            raise ImportError("rasterio simulado ausente")
        return real_import(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    G = _grafo({1: (42.3, -83.7), 2: (42.31, -83.71)})
    f = FuenteCopernicus(cache_tiles=tmp_path / "t", cache_dir=tmp_path / "c",
                         permitir_descarga=False)
    alturas, meta = f.elevar(G)
    assert set(alturas) == {1, 2}
    assert all(v == 0.0 for v in alturas.values())
    assert meta["cobertura_directa"] == 0.0
    assert "aviso" in meta and "rasterio" in meta["aviso"]
    # La tesela elegida es la de Ann Arbor aunque no se pueda leer.
    assert "Copernicus_DSM_COG_10_N42_00_W084_00_DEM" in meta["teselas"]


def test_grafo_vacio():
    f = FuenteCopernicus()
    alturas, meta = f.elevar(nx.MultiDiGraph())
    assert alturas == {}
    assert meta["nodos"] == 0


# ---- con datos reales (tesela N42/W084) -------------------------------------
@pytest.mark.datos
@pytest.mark.skipif(not TIENE_RASTERIO, reason="requiere rasterio (uv run --with rasterio)")
def test_tesela_real_ann_arbor(tmp_path):
    import gzip
    import shutil
    from pathlib import Path

    import osmnx as ox

    raiz = Path(__file__).resolve().parents[1]
    gz = raiz / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
    plano = tmp_path / "g.graphml"
    with gzip.open(gz, "rb") as a, open(plano, "wb") as b:
        shutil.copyfileobj(a, b)
    G = ox.load_graphml(plano)
    cache_tiles = raiz / ".cache" / "elevacion" / "copernicus"
    f = FuenteCopernicus(cache_tiles=cache_tiles, cache_dir=tmp_path / "c",
                         permitir_descarga=True)
    alturas, meta = f.elevar(G)
    assert len(alturas) == G.number_of_nodes()
    assert meta["cobertura_directa"] == pytest.approx(1.0, abs=0.001)  # DEM denso
    # Ann Arbor: altitudes plausibles ~230-330 m.
    assert 200 <= meta["altura_min_m"] <= 260
    assert 300 <= meta["altura_max_m"] <= 360
