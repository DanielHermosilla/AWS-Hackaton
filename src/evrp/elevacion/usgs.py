"""Fuente de elevación USGS 3DEP: DEM denso del National Map por bbox.

Idea
----
A diferencia de eVED (nube de puntos de telemetría concentrada en corredores),
USGS 3DEP es un **Modelo Digital de Elevación denso** (1/3 arc-second ≈ 10 m) que
cubre todo el bbox de forma regular. Se descarga el/los tile(s) GeoTIFF que cubren
el grafo desde el servicio público ``3DEPElevation/ImageServer/exportImage`` del
USGS National Map y se **muestrea** la altura de cada nodo OSM por interpolación
bilineal del raster.

Resultado: cobertura **directa del 100 %** (todo nodo cae dentro del DEM) frente al
~16 % de eVED, sin interpolación a kilómetros de distancia.

Sin dependencias pesadas
------------------------
El GeoTIFF se pide con ``pixelType=F32`` y sin compresión, de modo que se puede leer
con un lector TIFF mínimo basado solo en ``numpy`` (ya en el núcleo). No se necesita
``rasterio``/``GDAL``. El georreferenciado se obtiene de los tags GeoTIFF
``ModelPixelScaleTag`` + ``ModelTiepointTag`` (coordenadas en EPSG:4326).

Red y caché
-----------
Las descargas se guardan en ``.cache/elevacion/usgs/<firma>.tif`` (una por teselado
del bbox). Si el DEM ya está en caché no hay red. El bbox se amplía con un margen
para que la interpolación bilineal de los nodos del borde no quede fuera del raster.

Degradación segura
------------------
Si no hay red o el servicio falla y no hay caché, ``elevar`` devuelve alturas 0.0
para todos los nodos y lo reporta en ``meta['aviso']`` (equivalente al perfil plano),
igual que ``FuenteEved``. El motor nunca falla por esto.
"""
from __future__ import annotations

import hashlib
import logging
import struct
from pathlib import Path
from typing import Any

from . import FuenteElevacion

log = logging.getLogger(__name__)

# Servicio público de elevación del USGS National Map (3DEP, dinámico).
URL_3DEP = ("https://elevation.nationalmap.gov/arcgis/rest/services/"
            "3DEPElevation/ImageServer/exportImage")

# 1/3 arc-second en grados por pixel (≈10.3 m en estas latitudes).
GRADOS_POR_PX_13 = 1.0 / 10800.0

# Lado máximo (px) por petición del ImageServer. El servicio rechaza (HTTP 500)
# peticiones con demasiados píxeles; ~2000×2000 float32 (~16 MB) va holgado.
MAX_LADO_PX = 2000


class _Raster:
    """DEM regular en EPSG:4326 con muestreo bilineal.

    Atributos
    ---------
    datos : np.ndarray (alto, ancho) float32  — fila 0 = norte (lat máxima).
    lon0, lat0 : coordenada del centro del pixel (0,0) (esquina noroeste).
    dlon, dlat : tamaño de pixel en grados (dlat < 0: lat decrece hacia el sur).
    nodata : valor de sin-dato (o None).
    """

    def __init__(self, datos, lon0, lat0, dlon, dlat, nodata=None):
        self.datos = datos
        self.lon0 = lon0
        self.lat0 = lat0
        self.dlon = dlon
        self.dlat = dlat
        self.nodata = nodata

    @property
    def alto(self) -> int:
        return self.datos.shape[0]

    @property
    def ancho(self) -> int:
        return self.datos.shape[1]

    def muestrear(self, lon, lat):
        """Interpolación bilineal vectorizada. Devuelve (valores, dentro_bool)."""
        import numpy as np

        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        # Coordenada fraccional de pixel (col=x hacia este, fil=y hacia sur).
        fx = (lon - self.lon0) / self.dlon
        fy = (lat - self.lat0) / self.dlat
        x0 = np.floor(fx).astype(int)
        y0 = np.floor(fy).astype(int)
        tx = fx - x0
        ty = fy - y0
        dentro = (x0 >= 0) & (y0 >= 0) & (x0 < self.ancho - 1) & (y0 < self.alto - 1)
        xc0 = np.clip(x0, 0, self.ancho - 1)
        yc0 = np.clip(y0, 0, self.alto - 1)
        xc1 = np.clip(x0 + 1, 0, self.ancho - 1)
        yc1 = np.clip(y0 + 1, 0, self.alto - 1)
        d = self.datos
        v00 = d[yc0, xc0]; v10 = d[yc0, xc1]
        v01 = d[yc1, xc0]; v11 = d[yc1, xc1]
        val = (v00 * (1 - tx) * (1 - ty) + v10 * tx * (1 - ty)
               + v01 * (1 - tx) * ty + v11 * tx * ty)
        if self.nodata is not None:
            malo = (np.isclose(v00, self.nodata) | np.isclose(v10, self.nodata)
                    | np.isclose(v01, self.nodata) | np.isclose(v11, self.nodata))
            dentro = dentro & ~malo
        return val, dentro


class FuenteUsgs(FuenteElevacion):
    """Altura por nodo OSM desde el DEM USGS 3DEP (National Map ImageServer).

    Parámetros
    ----------
    cache_dir : str | Path | None
        Carpeta de caché del GeoTIFF descargado. ``None`` desactiva la caché en
        disco (siempre descarga).
    resolucion_grados : float
        Tamaño de pixel solicitado (grados). Por defecto 1/3 arc-second (~10 m).
    margen_grados : float
        Margen añadido al bbox del grafo para que los nodos del borde queden dentro
        del raster al interpolar.
    timeout_s : float
        Timeout por petición HTTP.
    permitir_descarga : bool
        Si ``False`` solo usa caché; si no hay caché degrada a plano (útil en tests).
    """

    nombre = "usgs"

    def __init__(self, cache_dir: str | Path | None = ".cache/elevacion/usgs",
                 resolucion_grados: float = GRADOS_POR_PX_13, margen_grados: float = 0.01,
                 timeout_s: float = 180.0, permitir_descarga: bool = True):
        if resolucion_grados <= 0:
            raise ValueError("resolucion_grados debe ser > 0")
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.resolucion_grados = float(resolucion_grados)
        self.margen_grados = float(margen_grados)
        self.timeout_s = float(timeout_s)
        self.permitir_descarga = bool(permitir_descarga)

    # ---- descarga + lectura del DEM ------------------------------------------
    def _firma_bbox(self, bbox) -> str:
        s = f"{bbox[0]:.5f},{bbox[1]:.5f},{bbox[2]:.5f},{bbox[3]:.5f}:{self.resolucion_grados:.8f}"
        return hashlib.sha256(s.encode()).hexdigest()[:16]

    def _ruta_cache(self, bbox) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"3dep_{self._firma_bbox(bbox)}.npz"

    def _descargar_tif(self, bbox, ancho_px, alto_px) -> bytes:
        import requests

        params = {
            "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "bboxSR": "4326", "imageSR": "4326",
            "format": "tiff", "pixelType": "F32", "f": "image",
            "size": f"{ancho_px},{alto_px}",
            "interpolation": "RSP_BilinearInterpolation",
            "noData": "-9999", "noDataInterpretation": "esriNoDataMatchAny",
        }
        r = requests.get(URL_3DEP, params=params, timeout=self.timeout_s)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or "tiff" not in ctype:
            raise RuntimeError(f"3DEP exportImage status={r.status_code} ctype={ctype} "
                               f"body={r.text[:200] if 'tiff' not in ctype else ''}")
        return r.content

    def _descargar_mosaico(self, bbox) -> tuple["_Raster", int]:
        """Descarga el bbox en una malla de tiles (≤MAX_LADO_PX cada uno) y los cose
        en un único raster alineado al grid global de píxeles. Devuelve (_Raster, bytes).
        """
        import numpy as np

        res = self.resolucion_grados
        ancho_tot = max(2, round((bbox[2] - bbox[0]) / res))
        alto_tot = max(2, round((bbox[3] - bbox[1]) / res))
        # Nº de tiles por eje para no superar el límite por petición.
        ncols = (ancho_tot + MAX_LADO_PX - 1) // MAX_LADO_PX
        nfilas = (alto_tot + MAX_LADO_PX - 1) // MAX_LADO_PX
        # Lado real del raster global (grados), coherente con el nº de píxeles.
        lon0 = bbox[0]; lat_norte = bbox[1] + alto_tot * res  # borde norte del grid
        mosaico = np.full((alto_tot, ancho_tot), -9999.0, dtype=np.float32)
        bytes_tot = 0
        for cj in range(ncols):
            x0 = cj * MAX_LADO_PX
            x1 = min(x0 + MAX_LADO_PX, ancho_tot)
            for fi in range(nfilas):
                y0 = fi * MAX_LADO_PX           # desde el norte
                y1 = min(y0 + MAX_LADO_PX, alto_tot)
                sub = (lon0 + x0 * res, lat_norte - y1 * res,
                       lon0 + x1 * res, lat_norte - y0 * res)
                w = x1 - x0; h = y1 - y0
                contenido = self._descargar_tif(sub, w, h)
                bytes_tot += len(contenido)
                ras = _leer_geotiff(contenido)
                sub_dat = ras.datos
                if sub_dat.shape != (h, w):   # el server respeta size; por si acaso
                    sub_dat = _reajustar(sub_dat, h, w)
                mosaico[y0:y1, x0:x1] = sub_dat
        raster = _Raster(mosaico, lon0, lat_norte, res, -res, nodata=-9999.0)
        return raster, bytes_tot

    def _obtener_dem(self, bbox) -> tuple["_Raster", dict]:
        """Devuelve (_Raster, info). Usa caché .npz del mosaico si existe."""
        import numpy as np

        ruta = self._ruta_cache(bbox)
        meta = {"desde_cache": False, "bytes_descargados": 0}
        if ruta is not None and ruta.exists():
            try:
                z = np.load(ruta, allow_pickle=False)
                raster = _Raster(z["datos"], float(z["lon0"]), float(z["lat0"]),
                                 float(z["dlon"]), float(z["dlat"]),
                                 nodata=float(z["nodata"]))
                meta["desde_cache"] = True
                meta["bytes_descargados"] = ruta.stat().st_size
                return raster, meta
            except Exception as exc:
                log.debug("caché DEM ilegible, se recomputa: %s", exc)
        if not self.permitir_descarga:
            raise RuntimeError("sin caché y descarga deshabilitada")
        raster, bytes_tot = self._descargar_mosaico(bbox)
        if ruta is not None:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            np.savez(ruta, datos=raster.datos, lon0=raster.lon0, lat0=raster.lat0,
                     dlon=raster.dlon, dlat=raster.dlat, nodata=raster.nodata)
        meta["bytes_descargados"] = bytes_tot
        return raster, meta

    # ---- cálculo principal ----------------------------------------------------
    def elevar(self, G) -> tuple[dict[int, float], dict[str, Any]]:
        import numpy as np

        nodos = list(G.nodes)
        n = len(nodos)
        nlat = np.array([float(G.nodes[v]["y"]) for v in nodos])
        nlon = np.array([float(G.nodes[v]["x"]) for v in nodos])

        m = self.margen_grados
        bbox = (round(float(nlon.min()) - m, 5), round(float(nlat.min()) - m, 5),
                round(float(nlon.max()) + m, 5), round(float(nlat.max()) + m, 5))

        try:
            raster, info = self._obtener_dem(bbox)
        except Exception as exc:
            alturas = {int(v): 0.0 for v in nodos}
            meta = {"fuente": self.nombre, "nodos": n, "directos": 0,
                    "cobertura_directa": 0.0,
                    "aviso": f"no se pudo obtener DEM 3DEP ({exc}); alturas = 0 (degradación a plano)"}
            return alturas, meta

        valores, dentro = raster.muestrear(nlon, nlat)
        directos = int(dentro.sum())
        alturas: dict[int, float] = {}
        for i, v in enumerate(nodos):
            alturas[int(v)] = float(valores[i]) if bool(dentro[i]) else 0.0

        alt_val = np.array([valores[i] for i in range(n) if dentro[i]], dtype=float)
        meta = {
            "fuente": self.nombre,
            "nodos": n,
            "directos": directos,
            "cobertura_directa": round(directos / n, 4),
            "interpolados": n - directos,
            "resolucion_grados": self.resolucion_grados,
            "resolucion_m_aprox": round(self.resolucion_grados * 111320.0, 1),
            "bbox": list(bbox),
            "raster_px": [raster.ancho, raster.alto],
            "bytes_descargados": info.get("bytes_descargados", 0),
            "desde_cache": info.get("desde_cache", False),
            "altura_min_m": round(float(alt_val.min()), 1) if alt_val.size else None,
            "altura_max_m": round(float(alt_val.max()), 1) if alt_val.size else None,
        }
        return alturas, meta


# ---- lector GeoTIFF mínimo (float32, sin compresión, strips o tiles) ---------
def _reajustar(datos, h, w):
    """Recorta o rellena un array 2D a (h, w) (defensa ante tamaños inesperados)."""
    import numpy as np

    salida = np.full((h, w), -9999.0, dtype=np.float32)
    hh = min(h, datos.shape[0]); ww = min(w, datos.shape[1])
    salida[:hh, :ww] = datos[:hh, :ww]
    return salida


def _leer_geotiff(blob: bytes) -> "_Raster":
    """Lee un GeoTIFF little/big-endian, 1 banda float32, sin compresión.

    Soporta organización por *strips* (RowsPerStrip) o por *tiles*
    (TileWidth/TileLength). Lee el georreferenciado de ModelPixelScaleTag (33550)
    y ModelTiepointTag (33922). Pensado para el formato exacto que devuelve el
    ImageServer de 3DEP con pixelType=F32; lanza ``ValueError`` si no se cumple.
    """
    import numpy as np

    if len(blob) < 8:
        raise ValueError("GeoTIFF demasiado corto")
    orden = blob[:2]
    if orden == b"II":
        en = "<"
    elif orden == b"MM":
        en = ">"
    else:
        raise ValueError("no es un TIFF (orden de bytes desconocido)")
    magic = struct.unpack(en + "H", blob[2:4])[0]
    if magic != 42:
        raise ValueError("no es un TIFF clásico (magic != 42)")
    off_ifd = struct.unpack(en + "I", blob[4:8])[0]

    n_entradas = struct.unpack(en + "H", blob[off_ifd:off_ifd + 2])[0]
    tags: dict[int, tuple[int, int, int]] = {}  # tag -> (tipo, count, value_or_offset)
    tam_tipo = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
    base = off_ifd + 2
    for i in range(n_entradas):
        e = base + i * 12
        tag, tipo, count = struct.unpack(en + "HHI", blob[e:e + 8])
        tags[tag] = (tipo, count, e + 8)

    def leer_valores(tag):
        if tag not in tags:
            return None
        tipo, count, pos_campo = tags[tag]
        ts = tam_tipo.get(tipo, 0)
        total = ts * count
        if total <= 4:
            pos = pos_campo
        else:
            pos = struct.unpack(en + "I", blob[pos_campo:pos_campo + 4])[0]
        fmt = {1: "B", 3: "H", 4: "I", 11: "f", 12: "d"}.get(tipo)
        if tipo == 2:  # ASCII
            return list(blob[pos:pos + count])
        if fmt is None:
            raise ValueError(f"tipo TIFF no soportado: {tipo}")
        return list(struct.unpack(en + fmt * count, blob[pos:pos + ts * count]))

    def un(tag, default=None):
        v = leer_valores(tag)
        return v[0] if v else default

    ancho = un(256); alto = un(257)
    bits = un(258); compresion = un(259, 1)
    muestras = un(277, 1); sample_format = un(339, 1)
    if ancho is None or alto is None:
        raise ValueError("faltan dimensiones de imagen")
    if compresion != 1:
        raise ValueError(f"compresión no soportada: {compresion} (se requiere sin comprimir)")
    if muestras != 1:
        raise ValueError(f"se requiere 1 banda, hay {muestras}")
    if bits != 32 or sample_format != 3:
        raise ValueError(f"se requiere float32 (bits={bits}, sampleformat={sample_format})")

    dt = np.dtype(np.float32).newbyteorder("<" if en == "<" else ">")
    datos = np.zeros((alto, ancho), dtype=np.float32)

    tile_w = un(322); tile_h = un(323)
    if tile_w and tile_h:
        offsets = leer_valores(324)
        counts = leer_valores(325)
        tiles_por_fila = (ancho + tile_w - 1) // tile_w
        for idx, (off, cnt) in enumerate(zip(offsets, counts)):
            buf = np.frombuffer(blob[off:off + cnt], dtype=dt)
            if buf.size < tile_w * tile_h:
                buf = np.resize(buf, tile_w * tile_h)
            tile = buf[:tile_w * tile_h].reshape(tile_h, tile_w)
            ty = idx // tiles_por_fila
            tx = idx % tiles_por_fila
            y0 = ty * tile_h; x0 = tx * tile_w
            y1 = min(y0 + tile_h, alto); x1 = min(x0 + tile_w, ancho)
            datos[y0:y1, x0:x1] = tile[:y1 - y0, :x1 - x0]
    else:
        rows_per_strip = un(278, alto)
        offsets = leer_valores(273)
        counts = leer_valores(279)
        fila = 0
        for off, cnt in zip(offsets, counts):
            buf = np.frombuffer(blob[off:off + cnt], dtype=dt)
            nf = min(rows_per_strip, alto - fila)
            datos[fila:fila + nf, :] = buf[:nf * ancho].reshape(nf, ancho)
            fila += nf

    escala = leer_valores(33550)   # (sx, sy, sz) grados/px
    tie = leer_valores(33922)      # (i, j, k, X, Y, Z)
    if not escala or not tie:
        raise ValueError("faltan tags de georreferenciado (ModelPixelScale/Tiepoint)")
    sx, sy = float(escala[0]), float(escala[1])
    i_px, j_px, _, X, Y, _ = (float(x) for x in tie[:6])
    # Centro del pixel (0,0): esquina del tiepoint menos (i,j) px.
    lon0 = X - i_px * sx
    lat0 = Y + j_px * sy      # Y es el borde norte; fila 0 = norte
    dlon = sx
    dlat = -sy                # lat decrece al bajar de fila

    nodata = None
    # GDAL_NODATA (42113) como ASCII, por si viene.
    if 42113 in tags:
        v = leer_valores(42113)
        try:
            nodata = float("".join(chr(c) for c in v if c).strip())
        except (ValueError, TypeError):
            nodata = None
    if nodata is None:
        nodata = -9999.0  # pedimos noData=-9999 en la descarga

    return _Raster(datos, lon0, lat0, dlon, dlat, nodata=nodata)
