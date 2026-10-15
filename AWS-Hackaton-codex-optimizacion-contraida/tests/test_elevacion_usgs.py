"""Pruebas de la fuente de elevación USGS 3DEP (src/evrp/elevacion/usgs.py).

- Interfaz y degradación segura (sin red / descarga deshabilitada → alturas 0).
- Lector GeoTIFF mínimo: strips y tiles, float32, little/big-endian.
- Muestreo bilineal y georreferenciado del _Raster.
- Caché .npz: no vuelve a descargar.
- @pytest.mark.red: cobertura y rango reales descargando el DEM 3DEP.
"""
from __future__ import annotations

import struct
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from evrp.elevacion import FuenteElevacion
from evrp.elevacion.usgs import FuenteUsgs, _leer_geotiff, _Raster

RAIZ = Path(__file__).resolve().parents[1]


def _grafo(coords):
    G = nx.MultiDiGraph()
    for nid, (lat, lon) in coords.items():
        G.add_node(nid, x=lon, y=lat)
    return G


def _geotiff_min(datos: np.ndarray, lon0, lat0, dlon, dlat, en="<", tiled=False):
    """Construye un GeoTIFF mínimo float32 1-banda (strips o 1 tile) para tests.

    datos: (alto, ancho) float32, fila 0 = norte. lon0/lat0 = centro pixel (0,0).
    """
    alto, ancho = datos.shape
    datos = datos.astype(np.float32)
    dt = np.dtype(np.float32).newbyteorder("<" if en == "<" else ">")

    tags = []  # (tag, tipo, count, inline_bytes|None, externo_bytes|None)

    def add_tag(tag, tipo, valores, fmt):
        count = len(valores)
        empaq = struct.pack(en + fmt * count, *valores)
        if len(empaq) <= 4:
            tags.append((tag, tipo, count, empaq + b"\x00" * (4 - len(empaq)), None))
        else:
            tags.append((tag, tipo, count, None, empaq))

    if tiled:
        tile_w = ((ancho + 15) // 16) * 16 or 16
        tile_h = ((alto + 15) // 16) * 16 or 16
        tile = np.zeros((tile_h, tile_w), dtype=np.float32)
        tile[:alto, :ancho] = datos
        datos_bytes = tile.astype(dt).tobytes()
    else:
        datos_bytes = datos.astype(dt).tobytes()

    add_tag(256, 3, [ancho], "H")
    add_tag(257, 3, [alto], "H")
    add_tag(258, 3, [32], "H")
    add_tag(259, 3, [1], "H")        # sin compresión
    add_tag(262, 3, [1], "H")
    add_tag(277, 3, [1], "H")
    if tiled:
        add_tag(322, 3, [tile_w], "H")
        add_tag(323, 3, [tile_h], "H")
        add_tag(324, 4, [0], "I")                 # TileOffsets (se rellena abajo)
        add_tag(325, 4, [len(datos_bytes)], "I")  # TileByteCounts
    else:
        add_tag(273, 4, [0], "I")                 # StripOffsets (se rellena abajo)
        add_tag(278, 3, [alto], "H")              # RowsPerStrip
        add_tag(279, 4, [len(datos_bytes)], "I")  # StripByteCounts
    add_tag(339, 3, [3], "H")                      # SampleFormat = float
    add_tag(33550, 12, [dlon, abs(dlat), 0.0], "d")           # ModelPixelScale
    add_tag(33922, 12, [0.0, 0.0, 0.0, lon0, lat0, 0.0], "d")  # ModelTiepoint

    tags.sort(key=lambda t: t[0])
    n = len(tags)
    off_ifd = 8
    off_externos = off_ifd + 2 + n * 12 + 4

    # Colocar valores externos (>4 bytes) tras el IFD, luego los píxeles.
    ext = bytearray()
    posiciones_ext = {}
    cursor = off_externos
    for (tag, tipo, count, inline, externo) in tags:
        if externo is not None:
            posiciones_ext[tag] = cursor
            ext += externo
            cursor += len(externo)
    off_pixeles = cursor

    cabecera = bytearray()
    cabecera += (b"II" if en == "<" else b"MM")
    cabecera += struct.pack(en + "H", 42)
    cabecera += struct.pack(en + "I", off_ifd)
    cabecera += struct.pack(en + "H", n)
    for (tag, tipo, count, inline, externo) in tags:
        if tag in (273, 324):                       # offset de los píxeles
            val = struct.pack(en + "I", off_pixeles)
        elif externo is not None:
            val = struct.pack(en + "I", posiciones_ext[tag])
        else:
            val = inline
        cabecera += struct.pack(en + "HHI", tag, tipo, count) + val
    cabecera += struct.pack(en + "I", 0)            # fin de IFDs
    return bytes(cabecera) + bytes(ext) + datos_bytes


# ---------------------------------------------------------------------------
def test_implementa_interfaz():
    assert issubclass(FuenteUsgs, FuenteElevacion)
    assert FuenteUsgs.nombre == "usgs"


@pytest.mark.parametrize("en", ["<", ">"])
@pytest.mark.parametrize("tiled", [False, True])
def test_leer_geotiff_strips_y_tiles(en, tiled):
    datos = np.arange(12, dtype=np.float32).reshape(3, 4) * 1.5  # 0..16.5
    blob = _geotiff_min(datos, lon0=-83.7, lat0=42.3, dlon=0.001, dlat=-0.001, en=en, tiled=tiled)
    ras = _leer_geotiff(blob)
    assert ras.datos.shape == (3, 4)
    assert np.allclose(ras.datos, datos)
    assert ras.lon0 == pytest.approx(-83.7)
    assert ras.lat0 == pytest.approx(42.3)
    assert ras.dlon == pytest.approx(0.001)
    assert ras.dlat == pytest.approx(-0.001)


def test_muestreo_bilineal_centro_y_fuera():
    # 2x2 con valores conocidos; centro => promedio.
    datos = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    ras = _Raster(datos, lon0=0.0, lat0=1.0, dlon=1.0, dlat=-1.0, nodata=-9999.0)
    # centro del cuadrado (lon=0.5, lat=0.5) => media de las 4 esquinas = 15
    val, dentro = ras.muestrear(np.array([0.5]), np.array([0.5]))
    assert bool(dentro[0]) and val[0] == pytest.approx(15.0)
    # nodo del vértice (0,1) => 0.0
    val, dentro = ras.muestrear(np.array([0.0]), np.array([1.0]))
    assert val[0] == pytest.approx(0.0)
    # fuera del raster
    _, dentro = ras.muestrear(np.array([5.0]), np.array([5.0]))
    assert not bool(dentro[0])


def test_nodata_marca_fuera():
    datos = np.array([[-9999.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    ras = _Raster(datos, lon0=0.0, lat0=1.0, dlon=1.0, dlat=-1.0, nodata=-9999.0)
    _, dentro = ras.muestrear(np.array([0.4]), np.array([0.6]))
    assert not bool(dentro[0])   # una esquina es nodata


def test_sin_red_degrada_a_plano(tmp_path):
    G = _grafo({1: (42.3, -83.7), 2: (42.31, -83.71)})
    f = FuenteUsgs(cache_dir=tmp_path / "c", permitir_descarga=False)
    alturas, meta = f.elevar(G)
    assert set(alturas) == {1, 2}
    assert all(v == 0.0 for v in alturas.values())
    assert meta["cobertura_directa"] == 0.0
    assert "aviso" in meta


def test_cache_npz_evita_descarga(tmp_path, monkeypatch):
    # Prepara una caché .npz a mano para el bbox del grafo y verifica que se usa.
    G = _grafo({1: (42.300, -83.700), 2: (42.302, -83.698)})
    f = FuenteUsgs(cache_dir=tmp_path / "c", margen_grados=0.01, permitir_descarga=False)
    nlat = np.array([42.300, 42.302]); nlon = np.array([-83.700, -83.698])
    m = f.margen_grados
    bbox = (round(float(nlon.min()) - m, 5), round(float(nlat.min()) - m, 5),
            round(float(nlon.max()) + m, 5), round(float(nlat.max()) + m, 5))
    ruta = f._ruta_cache(bbox)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # raster plano a 100 m que cubre el bbox con holgura.
    datos = np.full((50, 50), 100.0, dtype=np.float32)
    np.savez(ruta, datos=datos, lon0=bbox[0], lat0=bbox[3],
             dlon=(bbox[2] - bbox[0]) / 49.0, dlat=-(bbox[3] - bbox[1]) / 49.0,
             nodata=-9999.0)

    def _no_descargar(*a, **k):
        raise AssertionError("no debería descargar: hay caché")

    monkeypatch.setattr(f, "_descargar_mosaico", _no_descargar)
    alturas, meta = f.elevar(G)
    assert meta["desde_cache"] is True
    assert meta["cobertura_directa"] == 1.0
    assert all(v == pytest.approx(100.0) for v in alturas.values())


def test_aplicar_escribe_elevation(tmp_path):
    G = _grafo({1: (42.300, -83.700)})
    f = FuenteUsgs(cache_dir=tmp_path / "c", margen_grados=0.01, permitir_descarga=False)
    nlat = np.array([42.300]); nlon = np.array([-83.700]); m = f.margen_grados
    bbox = (round(float(nlon.min()) - m, 5), round(float(nlat.min()) - m, 5),
            round(float(nlon.max()) + m, 5), round(float(nlat.max()) + m, 5))
    ruta = f._ruta_cache(bbox); ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = np.full((40, 40), 55.0, dtype=np.float32)
    np.savez(ruta, datos=datos, lon0=bbox[0], lat0=bbox[3],
             dlon=(bbox[2] - bbox[0]) / 39.0, dlat=-(bbox[3] - bbox[1]) / 39.0, nodata=-9999.0)
    f.aplicar(G)
    assert G.nodes[1]["elevation"] == pytest.approx(55.0)


# ---- con red real -----------------------------------------------------------
@pytest.mark.red
def test_cobertura_real_descarga_dem(tmp_path):
    import gzip
    import shutil

    import osmnx as ox

    gz = RAIZ / "src" / "evrp" / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
    plano = tmp_path / "g.graphml"
    with gzip.open(gz, "rb") as a, open(plano, "wb") as b:
        shutil.copyfileobj(a, b)
    G = ox.load_graphml(plano)
    f = FuenteUsgs(cache_dir=tmp_path / "c")
    alturas, meta = f.elevar(G)
    assert len(alturas) == G.number_of_nodes()
    assert meta["cobertura_directa"] == 1.0            # DEM denso: cubre todo
    assert 200 <= meta["altura_min_m"] <= 240
    assert 300 <= meta["altura_max_m"] <= 340
    # segunda llamada: desde caché, sin red.
    _, meta2 = f.elevar(G)
    assert meta2["desde_cache"] is True
