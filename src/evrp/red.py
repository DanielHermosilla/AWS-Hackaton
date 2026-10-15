"""Redes de transporte entre nodos clave.

Una Red entrega, para cada par de nodos clave (i, j), la secuencia de tramos
elementales del camino elegido: [(km, Δh_m), ...]. El resto del motor solo usa
esa interfaz, así que cambiar haversine por OSM no toca el modelo.
"""
from __future__ import annotations

import heapq
import logging
import math
from abc import ABC, abstractmethod
from pathlib import Path

from .datos import Nodo, haversine_km
from .energia import ModeloEnergia

log = logging.getLogger(__name__)

Tramo = tuple[float, float]  # (km, desnivel en metros)


class Red(ABC):
    nombre = "abstracta"

    @abstractmethod
    def preparar(self, nodos: list[Nodo], energia: ModeloEnergia) -> None:
        """Precalcula los caminos entre todos los pares de nodos clave."""

    @abstractmethod
    def tramos(self, i: str, j: str) -> list[Tramo]:
        """Tramos elementales del camino i→j (lista vacía si i y j coinciden)."""

    def geometria(self, i: str, j: str) -> list[tuple[float, float]]:
        """Puntos (lat, lon) del camino, para mapas. Por defecto, línea recta."""
        return [self._pos[i], self._pos[j]]

    def km(self, i: str, j: str) -> float:
        return sum(t[0] for t in self.tramos(i, j))


class RedHaversine(Red):
    """Distancia en línea recta × factor vial. Sin elevación. No requiere internet."""

    nombre = "haversine"

    def __init__(self, factor_vial: float = 1.3):
        if factor_vial < 1:
            raise ValueError("factor_vial debe ser >= 1")
        self.factor = factor_vial
        self._pos: dict[str, tuple[float, float]] = {}

    def preparar(self, nodos, energia):
        self._pos = {n.id: (n.lat, n.lon) for n in nodos}

    def tramos(self, i, j):
        if i == j:
            return []
        (a, b), (c, d) = self._pos[i], self._pos[j]
        km = self.factor * haversine_km(a, b, c, d)
        return [(km, 0.0)] if km > 0 else []


class RedOSM(Red):
    """Grafo vial OpenStreetMap (osmnx). Caminos de mínima energía con Dijkstra.

    Si el modelo de energía usa pendiente, se usa el potencial p(v)=κ·η_r·h(v):
    los costos reducidos e + p(u) − p(v) son >= 0, así que Dijkstra es exacto.
    """

    nombre = "osm"

    def __init__(self, margen_km: float = 2.0, cache: str = ".cache/osm", grafo: str | None = None,
                 max_acceso_m: float | None = None, permitir_descarga: bool = True,
                 algoritmo_caminos: str | None = None, cache_adyacencia: bool = True):
        self.margen_km = margen_km
        self.cache = Path(cache)
        self.grafo = grafo
        self.max_acceso_m = max_acceso_m
        self.permitir_descarga = permitir_descarga
        # Algoritmo de caminos más cortos. None = el mejor medido (ver caminos.py).
        self.algoritmo_caminos = algoritmo_caminos
        self.cache_adyacencia = cache_adyacencia
        self.origen_grafo = ""
        self.tiempos: dict[str, float] = {}       # etapas de preparar(), en segundos
        self._pos: dict[str, tuple[float, float]] = {}
        self._snap: dict[str, int] = {}
        self._stub_km: dict[str, float] = {}
        self._caminos: dict[tuple[str, str], list[int]] = {}
        self.G = None

    def _bbox(self, nodos):
        lats = [n.lat for n in nodos]
        lons = [n.lon for n in nodos]
        dlat = self.margen_km / 111.0
        dlon = self.margen_km / (111.0 * math.cos(math.radians(sum(lats) / len(lats))))
        return (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)

    def _grafo_local(self):
        """Carga el grafo empaquetado (o el indicado en config); descomprime .gz en la caché."""
        import osmnx as ox

        ruta = Path(self.grafo) if self.grafo else Path(__file__).parent / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
        if not ruta.exists():
            return None
        if ruta.suffix == ".gz":
            import gzip
            import shutil

            self.cache.mkdir(parents=True, exist_ok=True)
            plano = self.cache / ruta.stem
            if not plano.exists() or plano.stat().st_mtime < ruta.stat().st_mtime:
                with gzip.open(ruta, "rb") as a, open(plano, "wb") as b:
                    shutil.copyfileobj(a, b)
            ruta = plano
        self.origen_grafo = str(ruta)
        return ox.load_graphml(ruta)

    @staticmethod
    def _cubre(G, nodos) -> bool:
        ys = [d["y"] for _, d in G.nodes(data=True)]
        xs = [d["x"] for _, d in G.nodes(data=True)]
        return all(min(ys) <= n.lat <= max(ys) and min(xs) <= n.lon <= max(xs) for n in nodos)

    def _descargar(self, nodos):
        import osmnx as ox  # dependencia del núcleo (pyproject)

        ox.settings.cache_folder = str(self.cache / "http")
        G = self._grafo_local()
        if G is not None and self._cubre(G, nodos):
            return G
        if not self.permitir_descarga:
            raise RuntimeError("El grafo local no cubre los nodos y la descarga está deshabilitada")
        bbox = self._bbox(nodos)
        self.cache.mkdir(parents=True, exist_ok=True)
        archivo = self.cache / ("drive_%.4f_%.4f_%.4f_%.4f.graphml" % bbox)
        if archivo.exists():
            G = ox.load_graphml(archivo)
        else:
            G = ox.graph_from_bbox(bbox, network_type="drive", simplify=True)
            G = ox.truncate.largest_component(G, strongly=True)
            ox.save_graphml(G, archivo)
        self.origen_grafo = str(archivo)
        return G

    def preparar(self, nodos, energia):
        import time

        t0 = time.perf_counter()
        G = self._descargar(nodos)        # carga/descompresión del grafo
        self.tiempos["carga_grafo"] = time.perf_counter() - t0
        self.G = G
        self._pos = {n.id: (n.lat, n.lon) for n in nodos}
        self.meta_elevacion = None
        fuente_elev = getattr(self, "elevacion", "ninguna")
        if energia.usar_pendiente and fuente_elev and fuente_elev != "ninguna":
            t1 = time.perf_counter()
            self.meta_elevacion = aplicar_elevacion(G, fuente_elev, getattr(self, "elevacion_cfg", {}))
            self.tiempos["elevacion"] = time.perf_counter() - t1
        elev = {v: float(d.get("elevation", 0.0) or 0.0) for v, d in G.nodes(data=True)}

        t0 = time.perf_counter()
        self._ajustar_calle(nodos, G)     # snap de nodos clave a la calle
        self.tiempos["ajuste_calle"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        pot = self._construir_adyacencia(G, elev, energia)  # adyacencia con costo reducido
        self.tiempos["adyacencia"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        self._resolver_caminos(nodos, energia, pot)         # caminos entre pares
        self.tiempos["caminos"] = time.perf_counter() - t0
        self._energia = energia

    def _ajustar_calle(self, nodos, G):
        """Ajusta cada nodo clave a la calle (geometría vectorizada con numpy)."""
        import numpy as np

        # Puntos de la geometría de cada calle: (lat, lon, nodo extremo más cercano por la calle,
        # km a lo largo de la calle hasta ese nodo). Así el acceso se mide a la calle, no al cruce.
        plat, plon, pnodo, pkm = [], [], [], []
        for u, v, d in G.edges(data=True):
            geom = d.get("geometry")
            pts = list(geom.coords) if geom is not None else [(G.nodes[u]["x"], G.nodes[u]["y"]),
                                                               (G.nodes[v]["x"], G.nodes[v]["y"])]
            acum = [0.0]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                acum.append(acum[-1] + haversine_km(y1, x1, y2, x2))
            total = acum[-1]
            for (x, y), a in zip(pts, acum):
                plat.append(y)
                plon.append(x)
                if a <= total - a:
                    pnodo.append(u); pkm.append(a)
                else:
                    pnodo.append(v); pkm.append(total - a)
        ys, xs = np.radians(plat), np.radians(plon)
        pkm_arr = np.array(pkm)
        for n in nodos:
            la, lo = math.radians(n.lat), math.radians(n.lon)
            h = np.sin((ys - la) / 2) ** 2 + math.cos(la) * np.cos(ys) * np.sin((xs - lo) / 2) ** 2
            d = 2 * 6371.0088 * np.arcsin(np.sqrt(np.minimum(1.0, h)))
            k = int(np.argmin(d + pkm_arr * 1e-6))  # desempate: más cerca de un cruce
            if self.max_acceso_m is not None and d[k] * 1000 > self.max_acceso_m:
                raise ValueError(f"{n.id} está a {d[k] * 1000:.0f} m de la calle más cercana "
                                 f"(máximo {self.max_acceso_m} m)")
            self._snap[n.id] = pnodo[k]
            self._stub_km[n.id] = float(d[k] + pkm_arr[k])

    def _construir_adyacencia(self, G, elev, energia):
        """Adyacencia con el mejor arco paralelo por energía y costo reducido ≥ 0.

        El resultado (independiente de los nodos clave) se cachea en .npz con el hash
        del grafo y los parámetros de energía, porque dominarla toma tiempo.
        """
        import time

        cacheado = self._cargar_adyacencia(energia)
        if cacheado is not None:
            self._ady, self._tramo_arco, pot = cacheado
            return pot
        pot = {v: energia.kappa * energia.eta_regeneracion * elev[v] if energia.usar_pendiente else 0.0
               for v in G.nodes}
        self._ady: dict[int, list[tuple[int, float, float, float]]] = {}
        mejor: dict[tuple[int, int], tuple[float, float]] = {}
        for u, v, d in G.edges(data=True):
            km = float(d.get("length", 0.0)) / 1000.0
            dh = elev[v] - elev[u]
            e = energia.tramo(km, dh)
            if (u, v) not in mejor or e < energia.tramo(*mejor[(u, v)]):
                mejor[(u, v)] = (km, dh)
        for (u, v), (km, dh) in mejor.items():
            red = energia.tramo(km, dh) + pot[u] - pot[v]
            self._ady.setdefault(u, []).append((v, max(red, 0.0), km, dh))
        self._tramo_arco = {(u, v): t for (u, v), t in mejor.items()}
        self._guardar_adyacencia(energia, pot)
        return pot

    def _firma_adyacencia(self, energia) -> str:
        """Hash estable del grafo de origen + parámetros de energía relevantes."""
        import hashlib

        h = hashlib.sha256()
        ruta = Path(self.origen_grafo)
        try:
            st = ruta.stat()
            h.update(f"{ruta.name}:{st.st_size}:{int(st.st_mtime)}".encode())
        except OSError:
            h.update(self.origen_grafo.encode())
        h.update(f"{energia.consumo_kwh_km}:{energia.masa_kg}:{energia.eta_traccion}:"
                 f"{energia.eta_regeneracion}:{energia.usar_pendiente}".encode())
        return h.hexdigest()[:16]

    def _ruta_cache_ady(self, energia) -> Path:
        return self.cache / "ady" / f"{self._firma_adyacencia(energia)}.npz"

    def _cargar_adyacencia(self, energia):
        if not self.cache_adyacencia:
            return None
        ruta = self._ruta_cache_ady(energia)
        if not ruta.exists():
            return None
        try:
            import numpy as np

            z = np.load(ruta, allow_pickle=False)
            u = z["u"]; v = z["v"]; w = z["w"]; km = z["km"]; dh = z["dh"]
            pn = z["pot_nodo"]; pv = z["pot_val"]
        except Exception:
            return None
        ady: dict[int, list[tuple[int, float, float, float]]] = {}
        tramo_arco: dict[tuple[int, int], tuple[float, float]] = {}
        for a, b, c, kk, hh in zip(u, v, w, km, dh):
            ia, ib = int(a), int(b)
            ady.setdefault(ia, []).append((ib, float(c), float(kk), float(hh)))
            tramo_arco[(ia, ib)] = (float(kk), float(hh))
        pot = {int(a): float(b) for a, b in zip(pn, pv)}
        return ady, tramo_arco, pot

    def _guardar_adyacencia(self, energia, pot) -> None:
        if not self.cache_adyacencia:
            return
        try:
            import numpy as np

            u, v, w, km, dh = [], [], [], [], []
            for a, vecinos in self._ady.items():
                for b, c, kk, hh in vecinos:
                    u.append(a); v.append(b); w.append(c); km.append(kk); dh.append(hh)
            ruta = self._ruta_cache_ady(energia)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            np.savez(ruta, u=np.array(u, dtype=np.int64), v=np.array(v, dtype=np.int64),
                     w=np.array(w), km=np.array(km), dh=np.array(dh),
                     pot_nodo=np.array(list(pot.keys()), dtype=np.int64),
                     pot_val=np.array(list(pot.values())))
        except Exception as exc:  # la caché es solo una optimización
            log.debug("No se pudo guardar la caché de adyacencia: %s", exc)

    def _resolver_caminos(self, nodos, energia, pot):
        from .caminos import GrafoCaminos, resolver_caminos

        orig = {n.id: self._snap[n.id] for n in nodos}
        lat_lon = {}
        for v in self._ady:
            lat_lon[v] = (self.G.nodes[v]["y"], self.G.nodes[v]["x"])
        for n in nodos:                      # asegura coordenadas de los snaps
            s = self._snap[n.id]
            lat_lon.setdefault(s, (self.G.nodes[s]["y"], self.G.nodes[s]["x"]))
        g = GrafoCaminos(self._ady, pot, lat_lon, energia.consumo_kwh_km)
        pares = [(n.id, m.id) for n in nodos for m in nodos if n.id != m.id]
        self._caminos = resolver_caminos(g, orig, pares, self.algoritmo_caminos)

    def _dijkstra(self, origen, destinos):
        dist = {origen: 0.0}
        pred: dict[int, int] = {}
        pend = set(destinos)
        h = [(0.0, origen)]
        while h and pend:
            d, u = heapq.heappop(h)
            if d > dist.get(u, math.inf):
                continue
            pend.discard(u)
            for v, w, _, _ in self._ady.get(u, []):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    pred[v] = u
                    heapq.heappush(h, (nd, v))
        return pred

    def tramos(self, i, j):
        if i == j:
            return []
        out: list[Tramo] = []
        if self._stub_km[i] > 0:
            out.append((self._stub_km[i], 0.0))
        cam = self._caminos[(i, j)]
        out.extend(self._tramo_arco[(u, v)] for u, v in zip(cam, cam[1:]))
        if self._stub_km[j] > 0:
            out.append((self._stub_km[j], 0.0))
        return out

    def geometria(self, i, j):
        cam = self._caminos.get((i, j), [])
        pts = [(self.G.nodes[v]["y"], self.G.nodes[v]["x"]) for v in cam]
        return [self._pos[i], *pts, self._pos[j]]


def crear_red(cfg: dict) -> Red:
    tipo = cfg["pipeline"]["red"]
    if tipo == "haversine":
        return RedHaversine(cfg["red"]["factor_vial"])
    if tipo == "osm":
        r = cfg["red"]
        red = RedOSM(r["osm_margen_km"], r["osm_cache"], r.get("osm_grafo"), r.get("max_acceso_m"),
                     bool(r.get("osm_permitir_descarga", True)),
                     r.get("algoritmo_caminos"), bool(r.get("cache_adyacencia", True)))
        red.elevacion = r.get("elevacion", "ninguna")
        red.elevacion_cfg = {"csv": r.get("elevacion_csv", "data/eVED_EV.csv"),
                             "radio_m": r.get("elevacion_radio_m", 120.0),
                             "interpolacion": r.get("elevacion_interpolacion", "idw")}
        return red
    raise ValueError(tipo)


def aplicar_elevacion(G, fuente: str, opciones: dict) -> dict:
    """Escribe G.nodes[v]['elevation'] con la fuente elegida. Degrada a plano si falla."""
    try:
        if fuente == "eved":
            from .elevacion.eved import FuenteEved

            f = FuenteEved(opciones["csv"], radio_m=float(opciones["radio_m"]),
                           interpolacion=opciones["interpolacion"])
        else:
            raise ValueError(f"Fuente de elevación no implementada: {fuente!r}")
        meta = f.aplicar(G)
        return {"fuente": fuente, **(meta if isinstance(meta, dict) else {})}
    except Exception as exc:  # noqa: BLE001 — la elevación es opcional
        log.warning("Elevación %s no disponible (%s); se usa terreno plano", fuente, exc)
        return {"fuente": fuente, "error": str(exc)[:200]}
