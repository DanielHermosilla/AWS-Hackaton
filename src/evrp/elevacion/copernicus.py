"""Fuente de elevación Copernicus DEM 30 m (GLO-30, AWS Open Data).

Idea
----
El dataset ``s3://copernicus-dem-30m`` (acceso anónimo, Registry of Open Data on
AWS) publica un DEM global a 30 m (1 arcosegundo) en teselas COG de 1°×1° en
EPSG:4326. A diferencia de eVED (telemetría dispersa), es un **raster denso**: hay
un valor de altura para prácticamente cualquier punto terrestre, así que la
cobertura "directa" por nodo es total dentro del área descargada (no hay que
interpolar entre nodos observados: se interpola **dentro** del raster).

Esta fuente, dado un grafo OSM:

1. Calcula las teselas de 1°×1° que cubren la caja del grafo (con margen).
2. Descarga de S3 **solo** esas teselas a ``.cache/elevacion/copernicus`` (anónimo,
   vía ``boto3`` con firma deshabilitada). Reutiliza la caché si ya existen.
3. Lee los GeoTIFF con ``rasterio`` (import perezoso) y muestrea la altura de cada
   nodo con interpolación **bilineal** sobre el raster.

Degradación segura
------------------
El motor nunca depende de esta fuente ni de que ``rasterio``/``boto3`` estén
instalados: si falta la dependencia de lectura, o no hay teselas, o un nodo cae
fuera del área cubierta, se devuelve 0.0 para esos nodos y se reporta en los
metadatos (equivalente al perfil plano). Igual que ``FuenteEved``.

Nombre de tesela Copernicus
---------------------------
``Copernicus_DSM_COG_10_N<lat>_00_<E|W><lon>_00_DEM`` con el GeoTIFF
``Copernicus_DSM_COG_10_N<lat>_00_<E|W><lon>_00_DEM.tif``. ``<lat>``/``<lon>`` son
las esquinas **inferior-izquierda** (sur/oeste) enteras de la tesela de 1°×1°.

Caché
-----
El resultado por grafo se cachea en un ``.npz`` cuya firma combina el hash del
grafo (nodos + coords), la lista de teselas y los parámetros de muestreo.
"""
from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path
from typing import Any

from . import FuenteElevacion

log = logging.getLogger(__name__)

BUCKET = "copernicus-dem-30m"
REGION = "us-east-1"
# Resolución nominal GLO-30: 1 arcosegundo = 1/3600 grados.
GRADOS_POR_PIXEL = 1.0 / 3600.0


def _nombre_tesela(lat_sur: int, lon_oeste: int) -> str:
    """Nombre de la carpeta/tesela Copernicus para la esquina SO entera (lat, lon)."""
    ns = f"N{lat_sur:02d}" if lat_sur >= 0 else f"S{abs(lat_sur):02d}"
    ew = f"E{lon_oeste:03d}" if lon_oeste >= 0 else f"W{abs(lon_oeste):03d}"
    return f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"


def _teselas_para_bbox(lat_min, lat_max, lon_min, lon_max) -> list[tuple[int, int]]:
    """Esquinas SO enteras (lat, lon) de las teselas 1°×1° que cubren la caja."""
    teselas = []
    for la in range(math.floor(lat_min), math.floor(lat_max) + 1):
        for lo in range(math.floor(lon_min), math.floor(lon_max) + 1):
            teselas.append((la, lo))
    return teselas


class FuenteCopernicus(FuenteElevacion):
    """Altura por nodo OSM desde Copernicus DEM 30 m (GLO-30, AWS Open Data).

    Parámetros
    ----------
    cache_tiles : str | Path
        Carpeta donde se guardan los GeoTIFF descargados de S3.
    cache_dir : str | Path | None
        Carpeta de la caché ``.npz`` del resultado por grafo. ``None`` la desactiva.
    margen_grados : float
        Margen añadido a la caja del grafo al elegir teselas (robustez en bordes).
    permitir_descarga : bool
        Si ``False`` y falta una tesela en la caché local, no se intenta S3.
    muestreo : {"bilineal", "vecino"}
        Interpolación dentro del raster al muestrear el nodo.
    """

    nombre = "copernicus"

    def __init__(self, cache_tiles: str | Path = ".cache/elevacion/copernicus",
                 cache_dir: str | Path | None = ".cache/elevacion",
                 margen_grados: float = 0.0, permitir_descarga: bool = True,
                 muestreo: str = "bilineal"):
        if muestreo not in ("bilineal", "vecino"):
            raise ValueError("muestreo debe ser 'bilineal' o 'vecino'")
        self.cache_tiles = Path(cache_tiles)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.margen_grados = float(margen_grados)
        self.permitir_descarga = bool(permitir_descarga)
        self.muestreo = muestreo

    # ---- teselas / descarga ---------------------------------------------------
    def _ruta_tif(self, lat_sur: int, lon_oeste: int) -> Path:
        base = _nombre_tesela(lat_sur, lon_oeste)
        return self.cache_tiles / f"{base}.tif"

    def _clave_s3(self, lat_sur: int, lon_oeste: int) -> str:
        base = _nombre_tesela(lat_sur, lon_oeste)
        return f"{base}/{base}.tif"

    def _descargar_tesela(self, lat_sur: int, lon_oeste: int) -> tuple[Path | None, int]:
        """Devuelve (ruta_local, bytes_descargados). ruta=None si no existe en S3."""
        destino = self._ruta_tif(lat_sur, lon_oeste)
        if destino.exists():
            return destino, 0
        if not self.permitir_descarga:
            return None, 0
        import boto3
        from botocore import UNSIGNED
        from botocore.client import Config
        from botocore.exceptions import ClientError

        s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version=UNSIGNED))
        clave = self._clave_s3(lat_sur, lon_oeste)
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp = destino.with_suffix(".tif.part")
            s3.download_file(BUCKET, clave, str(tmp))
            tmp.replace(destino)
            return destino, destino.stat().st_size
        except ClientError as exc:  # tesela inexistente (p. ej. océano) u otro error
            codigo = exc.response.get("Error", {}).get("Code", "")
            if codigo in ("404", "NoSuchKey"):
                log.info("Tesela Copernicus inexistente en S3: %s", clave)
                return None, 0
            raise

    # ---- firma / caché del resultado -----------------------------------------
    def _hash_grafo(self, G) -> str:
        h = hashlib.sha256()
        for v, d in sorted(G.nodes(data=True), key=lambda t: t[0]):
            h.update(f"{v}:{round(float(d['y']), 6)}:{round(float(d['x']), 6)};".encode())
        return h.hexdigest()[:16]

    def _firma(self, G, teselas) -> str:
        ts = ",".join(_nombre_tesela(la, lo) for la, lo in sorted(teselas))
        base = f"{self._hash_grafo(G)}|{ts}|{self.muestreo}|{self.margen_grados}"
        return hashlib.sha256(base.encode()).hexdigest()[:20]

    def _ruta_cache(self, G, teselas) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"copernicus_{self._firma(G, teselas)}.npz"

    def _cargar_cache(self, G, teselas):
        ruta = self._ruta_cache(G, teselas)
        if ruta is None or not ruta.exists():
            return None
        try:
            import json

            import numpy as np

            z = np.load(ruta, allow_pickle=False)
            alturas = {int(a): float(b) for a, b in zip(z["nodos"], z["alt"])}
            meta = json.loads(str(z["meta"]))
            meta["desde_cache"] = True
            return alturas, meta
        except Exception as exc:  # la caché es solo optimización
            log.debug("No se pudo cargar la caché Copernicus: %s", exc)
            return None

    def _guardar_cache(self, G, teselas, alturas, meta) -> None:
        ruta = self._ruta_cache(G, teselas)
        if ruta is None:
            return
        try:
            import json

            import numpy as np

            ruta.parent.mkdir(parents=True, exist_ok=True)
            nodos = np.array(list(alturas.keys()), dtype=np.int64)
            alt = np.array(list(alturas.values()), dtype=float)
            np.savez(ruta, nodos=nodos, alt=alt, meta=json.dumps(meta, ensure_ascii=False))
        except Exception as exc:
            log.debug("No se pudo guardar la caché Copernicus: %s", exc)

    # ---- muestreo del raster --------------------------------------------------
    @staticmethod
    def _muestrear_raster(ds, nlat, nlon, bilineal: bool):
        """Muestrea alturas (m) en (nlat, nlon) con un dataset rasterio abierto.

        Devuelve ``(valores, mascara_valida)``: valores float; máscara True donde el
        punto cae dentro del raster y no es nodata.
        """
        import numpy as np

        a = ds.read(1).astype("float64")
        nodata = ds.nodata
        if nodata is not None:
            a = np.where(a == nodata, np.nan, a)
        # Mapea lon/lat a coordenadas de píxel (col, fila) fraccionarias.
        import warnings

        inv = ~ds.transform  # affine inversa: (col, fila) = inv * (x, y)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PendingDeprecationWarning)
            cols, filas = inv * (np.asarray(nlon), np.asarray(nlat))
        H, W = a.shape
        valores = np.full(len(nlat), np.nan, dtype="float64")
        dentro = (cols >= 0) & (cols <= W - 1) & (filas >= 0) & (filas <= H - 1)
        if not np.any(dentro):
            return valores, np.zeros(len(nlat), dtype=bool)
        c = cols[dentro]
        r = filas[dentro]
        if not bilineal:
            ci = np.clip(np.round(c).astype(int), 0, W - 1)
            ri = np.clip(np.round(r).astype(int), 0, H - 1)
            valores[dentro] = a[ri, ci]
        else:
            c0 = np.clip(np.floor(c).astype(int), 0, W - 1)
            r0 = np.clip(np.floor(r).astype(int), 0, H - 1)
            c1 = np.clip(c0 + 1, 0, W - 1)
            r1 = np.clip(r0 + 1, 0, H - 1)
            fc = c - c0
            fr = r - r0
            v00 = a[r0, c0]; v01 = a[r0, c1]; v10 = a[r1, c0]; v11 = a[r1, c1]
            top = v00 * (1 - fc) + v01 * fc
            bot = v10 * (1 - fc) + v11 * fc
            valores[dentro] = top * (1 - fr) + bot * fr
        mascara = dentro & np.isfinite(valores)
        return valores, mascara

    # ---- cálculo principal ----------------------------------------------------
    def elevar(self, G) -> tuple[dict[int, float], dict[str, Any]]:
        import numpy as np

        nodos = list(G.nodes)
        nlat = np.array([float(G.nodes[v]["y"]) for v in nodos])
        nlon = np.array([float(G.nodes[v]["x"]) for v in nodos])
        n = len(nodos)

        if n == 0:
            return {}, {"fuente": self.nombre, "nodos": 0, "directos": 0,
                        "cobertura_directa": 0.0, "aviso": "grafo vacío"}

        m = self.margen_grados
        teselas = _teselas_para_bbox(nlat.min() - m, nlat.max() + m,
                                     nlon.min() - m, nlon.max() + m)

        cacheado = self._cargar_cache(G, teselas)
        if cacheado is not None:
            return cacheado

        # Dependencia de lectura perezosa: sin rasterio -> degradación segura.
        try:
            import rasterio  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            alturas = {int(v): 0.0 for v in nodos}
            meta = {"fuente": self.nombre, "nodos": n, "directos": 0,
                    "cobertura_directa": 0.0, "teselas": [_nombre_tesela(*t) for t in teselas],
                    "aviso": f"rasterio no disponible ({exc}); alturas = 0 (degradación a plano)"}
            self._guardar_cache(G, teselas, alturas, meta)
            return alturas, meta

        import time

        import rasterio

        t0 = time.perf_counter()
        bytes_descargados = 0
        teselas_ok: list[tuple[int, int]] = []
        rutas: list[Path] = []
        for la, lo in teselas:
            ruta, nbytes = self._descargar_tesela(la, lo)
            bytes_descargados += nbytes
            if ruta is not None:
                teselas_ok.append((la, lo))
                rutas.append(ruta)
        seg_descarga = time.perf_counter() - t0

        if not rutas:
            alturas = {int(v): 0.0 for v in nodos}
            meta = {"fuente": self.nombre, "nodos": n, "directos": 0,
                    "cobertura_directa": 0.0, "teselas": [_nombre_tesela(*t) for t in teselas],
                    "aviso": "ninguna tesela disponible; alturas = 0 (degradación a plano)",
                    "bytes_descargados": bytes_descargados}
            self._guardar_cache(G, teselas, alturas, meta)
            return alturas, meta

        t1 = time.perf_counter()
        valores = np.full(n, np.nan, dtype="float64")
        cubierto = np.zeros(n, dtype=bool)
        for ruta in rutas:
            with rasterio.open(ruta) as ds:
                vals, mask = self._muestrear_raster(ds, nlat, nlon, self.muestreo == "bilineal")
            nuevos = mask & ~cubierto
            valores[nuevos] = vals[nuevos]
            cubierto |= mask
        seg_muestreo = time.perf_counter() - t1

        directos = int(cubierto.sum())
        alturas: dict[int, float] = {}
        for i, v in enumerate(nodos):
            alturas[int(v)] = float(valores[i]) if cubierto[i] else 0.0

        hs_validas = valores[cubierto]
        meta = {
            "fuente": self.nombre,
            "nodos": n,
            "directos": directos,
            "cobertura_directa": round(directos / n, 4),
            "fuera_de_cobertura": int(n - directos),
            "teselas": [_nombre_tesela(*t) for t in teselas_ok],
            "teselas_pedidas": len(teselas),
            "muestreo": self.muestreo,
            "resolucion_m_aprox": 30,
            "bytes_descargados": int(bytes_descargados),
            "mb_descargados": round(bytes_descargados / 1e6, 2),
            "segundos_descarga": round(seg_descarga, 2),
            "segundos_muestreo": round(seg_muestreo, 2),
            "altura_min_m": round(float(np.nanmin(hs_validas)), 1) if directos else None,
            "altura_max_m": round(float(np.nanmax(hs_validas)), 1) if directos else None,
            "desde_cache": False,
        }
        self._guardar_cache(G, teselas, alturas, meta)
        return alturas, meta


__all__ = ["FuenteCopernicus", "_nombre_tesela", "_teselas_para_bbox"]
