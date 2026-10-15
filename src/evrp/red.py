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
                 max_acceso_m: float | None = None, permitir_descarga: bool = True):
        self.margen_km = margen_km
        self.cache = Path(cache)
        self.grafo = grafo
        self.max_acceso_m = max_acceso_m
        self.permitir_descarga = permitir_descarga
        self.origen_grafo = ""
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
        import numpy as np

        G = self._descargar(nodos)
        self.G = G
        self._pos = {n.id: (n.lat, n.lon) for n in nodos}
        ids = list(G.nodes)
        elev = {v: float(d.get("elevation", 0.0) or 0.0) for v, d in G.nodes(data=True)}
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
        del ids
        # Adyacencia con el mejor arco paralelo por energía.
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
        destinos = {self._snap[n.id] for n in nodos}
        for n in nodos:
            pred = self._dijkstra(self._snap[n.id], destinos)
            for m in nodos:
                if m.id == n.id:
                    continue
                camino = [self._snap[m.id]]
                while camino[-1] != self._snap[n.id]:
                    p = pred.get(camino[-1])
                    if p is None:
                        raise RuntimeError(f"Sin camino vial {n.id}→{m.id}")
                    camino.append(p)
                self._caminos[(n.id, m.id)] = camino[::-1]
        self._energia = energia

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
        return RedOSM(r["osm_margen_km"], r["osm_cache"], r.get("osm_grafo"), r.get("max_acceso_m"),
                      bool(r.get("osm_permitir_descarga", True)))
    raise ValueError(tipo)
