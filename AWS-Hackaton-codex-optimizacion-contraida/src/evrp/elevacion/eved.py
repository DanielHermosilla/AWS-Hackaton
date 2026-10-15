"""Fuente de elevación eVED: altura por nodo OSM a partir de telemetría eVED.

Idea
----
El dataset eVED trae, para cada punto GPS mapeado a la red, su altura suavizada
(`Elevation Smoothed[m]`) sobre coordenadas ya ajustadas a la calzada
(`Matched Latitude/Longitude`). Agregamos esos puntos al nodo vial OSM más
cercano (dentro de un radio) con la **mediana** (robusta a ruido/outliers) y, para
los nodos sin ningún punto cercano, interpolamos a partir de los nodos con dato
(IDW o vecino más cercano). Así obtenemos `elevation` para todos los nodos del
grafo sin ninguna dependencia externa (ni DEM ni red).

Cobertura
---------
`elevar` reporta cuántos nodos tienen dato **directo** (observado), la fracción de
cobertura directa y, para los interpolados, la distribución de la distancia al
nodo observado más cercano (así se sabe cuánto "inventó" la interpolación).

Caché
-----
El resultado se cachea en un `.npz` cuya firma combina el hash del grafo (nodos +
coordenadas) con los parámetros de agregación/interpolación y un hash del CSV de
origen. Si cambia cualquiera, se recomputa.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import math
from pathlib import Path
from typing import Any

from . import FuenteElevacion

log = logging.getLogger(__name__)

R_TIERRA_M = 6371008.8  # radio medio terrestre (m), consistente con datos.haversine_km


class FuenteEved(FuenteElevacion):
    """Altura por nodo OSM desde eVED (Matched lat/lon + Elevation Smoothed).

    Parámetros
    ----------
    ruta_csv : str | Path
        CSV eVED con columnas ``Matched Latitude[deg]``, ``Matched Longitude[deg]``
        y ``Elevation Smoothed[m]`` (fallback a ``Elevation Raw[m]``).
    radio_m : float
        Radio máximo (m) para asignar un punto a un nodo vial. Mediana por nodo.
    interpolacion : {"idw", "vecino"}
        Método para rellenar nodos sin dato directo.
    idw_k : int
        Nº de vecinos observados usados en IDW.
    idw_potencia : float
        Exponente p de IDW (peso ∝ 1/d^p).
    cache_dir : str | Path | None
        Carpeta de caché ``.npz``. ``None`` desactiva la caché.
    max_filas : int | None
        Límite de filas del CSV a leer (para pruebas rápidas). ``None`` = todas.
    """

    nombre = "eved"

    def __init__(self, ruta_csv: str | Path, radio_m: float = 120.0,
                 interpolacion: str = "idw", idw_k: int = 6, idw_potencia: float = 2.0,
                 cache_dir: str | Path | None = ".cache/elevacion", max_filas: int | None = None):
        if interpolacion not in ("idw", "vecino"):
            raise ValueError("interpolacion debe ser 'idw' o 'vecino'")
        if radio_m <= 0:
            raise ValueError("radio_m debe ser > 0")
        self.ruta_csv = Path(ruta_csv)
        self.radio_m = float(radio_m)
        self.interpolacion = interpolacion
        self.idw_k = int(idw_k)
        self.idw_potencia = float(idw_potencia)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.max_filas = max_filas

    # ---- carga de puntos eVED -------------------------------------------------
    def _leer_puntos(self):
        """Devuelve (lat[], lon[], h[]) de los puntos eVED válidos como arrays numpy."""
        import numpy as np

        lats, lons, hs = [], [], []
        with open(self.ruta_csv, encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            campos = set(lector.fieldnames or [])
            col_lat = "Matched Latitude[deg]" if "Matched Latitude[deg]" in campos else "Latitude[deg]"
            col_lon = "Matched Longitude[deg]" if "Matched Longitude[deg]" in campos else "Longitude[deg]"
            col_h = "Elevation Smoothed[m]" if "Elevation Smoothed[m]" in campos else "Elevation Raw[m]"
            for i, r in enumerate(lector):
                if self.max_filas is not None and i >= self.max_filas:
                    break
                try:
                    la = float(r[col_lat]); lo = float(r[col_lon]); h = float(r[col_h])
                except (KeyError, TypeError, ValueError):
                    continue
                if not (math.isfinite(la) and math.isfinite(lo) and math.isfinite(h)):
                    continue
                if not (-90 <= la <= 90 and -180 <= lo <= 180):
                    continue
                lats.append(la); lons.append(lo); hs.append(h)
        return (np.asarray(lats), np.asarray(lons), np.asarray(hs))

    # ---- firma / caché --------------------------------------------------------
    def _hash_grafo(self, G) -> str:
        h = hashlib.sha256()
        for v, d in sorted(G.nodes(data=True), key=lambda t: t[0]):
            h.update(f"{v}:{round(float(d['y']), 6)}:{round(float(d['x']), 6)};".encode())
        return h.hexdigest()[:16]

    def _hash_csv(self) -> str:
        try:
            st = self.ruta_csv.stat()
            return hashlib.sha256(f"{self.ruta_csv.name}:{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:12]
        except OSError:
            return "sincsv"

    def _firma(self, G) -> str:
        params = f"{self.radio_m}:{self.interpolacion}:{self.idw_k}:{self.idw_potencia}:{self.max_filas}"
        base = f"{self._hash_grafo(G)}|{self._hash_csv()}|{params}"
        return hashlib.sha256(base.encode()).hexdigest()[:20]

    def _ruta_cache(self, G) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"eved_{self._firma(G)}.npz"

    def _cargar_cache(self, G):
        ruta = self._ruta_cache(G)
        if ruta is None or not ruta.exists():
            return None
        try:
            import json

            import numpy as np

            z = np.load(ruta, allow_pickle=False)
            nodos = z["nodos"]; alt = z["alt"]
            alturas = {int(a): float(b) for a, b in zip(nodos, alt)}
            meta = json.loads(str(z["meta"]))
            meta["desde_cache"] = True
            return alturas, meta
        except Exception as exc:  # la caché es solo optimización
            log.debug("No se pudo cargar la caché de elevación: %s", exc)
            return None

    def _guardar_cache(self, G, alturas, meta) -> None:
        ruta = self._ruta_cache(G)
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
            log.debug("No se pudo guardar la caché de elevación: %s", exc)

    # ---- proyección local -----------------------------------------------------
    @staticmethod
    def _proyectar(lat, lon, lat0, lon0):
        """Equirectangular local (m): x=R·cosφ0·Δλ, y=R·Δφ. Exacta a corta distancia."""
        import numpy as np

        x = R_TIERRA_M * math.cos(math.radians(lat0)) * np.radians(lon - lon0)
        y = R_TIERRA_M * np.radians(lat - lat0)
        return np.column_stack([x, y])

    # ---- cálculo principal ----------------------------------------------------
    def elevar(self, G) -> tuple[dict[int, float], dict[str, Any]]:
        import numpy as np
        from scipy.spatial import cKDTree

        cacheado = self._cargar_cache(G)
        if cacheado is not None:
            return cacheado

        nodos = list(G.nodes)
        nlat = np.array([float(G.nodes[v]["y"]) for v in nodos])
        nlon = np.array([float(G.nodes[v]["x"]) for v in nodos])
        n = len(nodos)

        plat, plon, ph = self._leer_puntos()

        if len(plat) == 0:
            alturas = {int(v): 0.0 for v in nodos}
            meta = {"fuente": self.nombre, "nodos": n, "directos": 0,
                    "cobertura_directa": 0.0, "puntos_eved": 0,
                    "aviso": "sin puntos eVED válidos; alturas = 0 (degradación a plano)"}
            self._guardar_cache(G, alturas, meta)
            return alturas, meta

        # Proyección local centrada en el grafo (metros planos: KDTree euclídeo).
        lat0 = float(nlat.mean())
        lon0 = float(nlon.mean())
        xy_nodos = self._proyectar(nlat, nlon, lat0, lon0)
        xy_puntos = self._proyectar(plat, plon, lat0, lon0)

        # 1) Asignar cada punto eVED al nodo más cercano dentro del radio.
        arbol_nodos = cKDTree(xy_nodos)
        dpn, ipn = arbol_nodos.query(xy_puntos, k=1)   # distancia punto→nodo, índice nodo
        dentro = dpn <= self.radio_m
        asign: dict[int, list[float]] = {}
        for idx_nodo, h, ok in zip(ipn, ph, dentro):
            if ok:
                asign.setdefault(int(idx_nodo), []).append(float(h))

        directo_idx = sorted(asign)
        alturas_dir = {i: float(np.median(asign[i])) for i in directo_idx}
        n_puntos_por_nodo = {i: len(asign[i]) for i in directo_idx}
        directos = len(directo_idx)

        alturas: dict[int, float] = {}
        for i in directo_idx:
            alturas[int(nodos[i])] = alturas_dir[i]

        # 2) Interpolar los nodos sin dato directo desde los nodos observados.
        dist_interp: list[float] = []
        faltan = [i for i in range(n) if i not in asign]
        if directos > 0 and faltan:
            xy_dir = xy_nodos[directo_idx]
            h_dir = np.array([alturas_dir[i] for i in directo_idx])
            arbol_dir = cKDTree(xy_dir)
            xy_faltan = xy_nodos[faltan]
            if self.interpolacion == "vecino":
                d1, j1 = arbol_dir.query(xy_faltan, k=1)
                for i, dd, jj in zip(faltan, d1, j1):
                    alturas[int(nodos[i])] = float(h_dir[int(jj)])
                    dist_interp.append(float(dd))
            else:  # IDW con los k vecinos observados más cercanos
                k = min(self.idw_k, len(directo_idx))
                dk, jk = arbol_dir.query(xy_faltan, k=k)
                dk = np.atleast_2d(dk.T).T if k == 1 else dk
                jk = np.atleast_2d(jk.T).T if k == 1 else jk
                for r, i in enumerate(faltan):
                    dd = np.atleast_1d(dk[r])
                    cols = np.atleast_1d(jk[r]).astype(int)
                    dist_interp.append(float(dd.min()))
                    if dd.min() < 1e-6:
                        alturas[int(nodos[i])] = float(h_dir[cols[int(np.argmin(dd))]])
                    else:
                        w = 1.0 / np.power(dd, self.idw_potencia)
                        alturas[int(nodos[i])] = float(np.dot(w, h_dir[cols]) / w.sum())
        elif faltan:  # no hay ningún dato directo
            for i in faltan:
                alturas[int(nodos[i])] = 0.0

        # 3) Estadísticas de cobertura.
        def _pct(arr, q):
            return round(float(np.percentile(arr, q)), 1) if len(arr) else None

        total_puntos = int(sum(len(v) for v in asign.values()))
        meta = {
            "fuente": self.nombre,
            "nodos": n,
            "directos": directos,
            "cobertura_directa": round(directos / n, 4),
            "interpolados": len(faltan),
            "puntos_eved": int(len(plat)),
            "puntos_asignados": total_puntos,
            "radio_m": self.radio_m,
            "interpolacion": self.interpolacion,
            "puntos_por_nodo_mediana": (int(np.median(list(n_puntos_por_nodo.values())))
                                        if n_puntos_por_nodo else 0),
            "dist_interp_m": {
                "mediana": _pct(dist_interp, 50),
                "p90": _pct(dist_interp, 90),
                "max": round(float(max(dist_interp)), 1) if dist_interp else None,
            },
            "altura_min_m": round(float(min(alturas.values())), 1) if alturas else None,
            "altura_max_m": round(float(max(alturas.values())), 1) if alturas else None,
            "desde_cache": False,
        }
        self._guardar_cache(G, alturas, meta)
        return alturas, meta
