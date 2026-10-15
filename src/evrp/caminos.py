"""Algoritmos de caminos de mínima energía entre nodos clave (exactos).

Todos operan sobre un `GrafoCaminos` común: una adyacencia dirigida con costos
reducidos no negativos (energía + potencial), más metadatos para heurísticas
(coordenadas y potencial por nodo). Así se comparan en igualdad de condiciones y
se verifica que entregan la misma energía por par.

Costos reducidos y Dijkstra exacto
-----------------------------------
Con el modelo e = c·ℓ + κ·([Δh]⁺/η_d − η_r·[Δh]⁻) y el potencial p(v)=κ·η_r·h(v),
el costo reducido de un arco u→v es

    c̃(u,v) = e(u,v) + p(u) − p(v) ≥ 0

(la demostración está en RedOSM). La distancia reducida de un camino i→…→j es
telescópica:

    d̃(i,j) = d(i,j) + p(i) − p(j),

donde d es la energía real. Por tanto el camino que minimiza d̃ minimiza también d
(difieren en la constante p(i)−p(j)), y Dijkstra sobre c̃ es exacto.

Heurística admisible para A*
----------------------------
Buscamos el mínimo de d̃ hasta el destino t. Para cualquier nodo v,

    d̃(v,t) = d(v,t) + p(v) − p(t)
            = Σ (c·ℓ + κ·(...)) + p(v) − p(t)
            ≥ Σ c·ℓ + p(v) − p(t)            (el término de pendiente ≥ −p: ver abajo)
            ≥ c·haversine(v,t) + p(v) − p(t)  (ℓ ≥ haversine y la suma es ≥ la cuerda).

El término κ·([Δh]⁺/η_d − η_r·[Δh]⁻) sumado a lo largo del camino es ≥ κ·η_r·Σ(−[Δh]⁻)
≥ κ·η_r·(−Δh_total si baja) ≥ −(p(t)−p(v))… de hecho Σ e ≥ Σ c·ℓ + (p(t)−p(v))
por telescopía de p, de modo que d̃(v,t) ≥ Σ c·ℓ ≥ c·haversine(v,t). Usamos la cota
más apretada

    h(v) = c·haversine(v,t) + p(v) − p(t),

que es admisible (≤ d̃(v,t)) y consistente. Con el perfil "plano" p≡0 y queda
h(v)=c·haversine(v,t).
"""
from __future__ import annotations

import heapq
import math

from .datos import haversine_km


class GrafoCaminos:
    """Adyacencia dirigida con costos reducidos ≥ 0 y metadatos para heurísticas.

    - ``ady[u]``: lista de (v, costo_reducido, km, dh) — el motor solo usa km/dh.
    - ``pot[u]``: potencial p(u) (0 en perfil plano).
    - ``lat[u]``, ``lon[u]``: coordenadas del nodo (radianes para la heurística).
    - ``consumo``: c (kWh/km), para la heurística haversine.
    """

    __slots__ = ("ady", "pot", "lat", "lon", "consumo", "_nodos", "_idx",
                 "_csr", "_rev")

    def __init__(self, ady, pot, lat_lon, consumo):
        self.ady = ady
        self.pot = pot
        self.consumo = consumo
        self.lat = {v: math.radians(ll[0]) for v, ll in lat_lon.items()}
        self.lon = {v: math.radians(ll[1]) for v, ll in lat_lon.items()}
        self._nodos = None
        self._idx = None
        self._csr = None
        self._rev = None

    # --- utilidades compartidas -------------------------------------------
    def _h(self, v, lat_t, lon_t, pot_t):
        """Heurística admisible c·haversine(v,t) + p(v) − p(t) en kWh."""
        la, lo = self.lat[v], self.lon[v]
        s1 = math.sin((lat_t - la) / 2) ** 2
        s2 = math.sin((lon_t - lo) / 2) ** 2
        hav = 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(
            s1 + math.cos(la) * math.cos(lat_t) * s2)))
        return self.consumo * hav + self.pot[v] - pot_t

    def _reconstruir(self, pred, origen, destino):
        cam = [destino]
        while cam[-1] != origen:
            p = pred.get(cam[-1])
            if p is None:
                raise RuntimeError(f"Sin camino {origen}→{destino}")
            cam.append(p)
        return cam[::-1]

    def _rev_ady(self):
        if self._rev is None:
            rev: dict[int, list[tuple[int, float]]] = {}
            for u, vecinos in self.ady.items():
                for v, w, _, _ in vecinos:
                    rev.setdefault(v, []).append((u, w))
            self._rev = rev
        return self._rev


# ----------------------------------------------------------------------------
# (1) Dijkstra multi-destino desde cada origen (algoritmo actual).
# ----------------------------------------------------------------------------
def multi_destino(g: GrafoCaminos, orig_claves: dict[str, int],
                  pares) -> dict[tuple[str, str], list[int]]:
    por_origen: dict[int, list[tuple[str, str]]] = {}
    for i, j in pares:
        por_origen.setdefault(orig_claves[i], []).append((i, j))
    caminos: dict[tuple[str, str], list[int]] = {}
    for s, lista in por_origen.items():
        destinos = {orig_claves[j] for _, j in lista}
        pred = _dijkstra_multi(g, s, destinos)
        for i, j in lista:
            caminos[(i, j)] = g._reconstruir(pred, s, orig_claves[j])
    return caminos


def _dijkstra_multi(g: GrafoCaminos, origen, destinos):
    dist = {origen: 0.0}
    pred: dict[int, int] = {}
    pend = set(destinos)
    h = [(0.0, origen)]
    while h and pend:
        d, u = heapq.heappop(h)
        if d > dist.get(u, math.inf):
            continue
        pend.discard(u)
        for v, w, _, _ in g.ady.get(u, []):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                pred[v] = u
                heapq.heappush(h, (nd, v))
    return pred


# ----------------------------------------------------------------------------
# (2) Dijkstra bidireccional par a par.
# ----------------------------------------------------------------------------
def bidireccional(g: GrafoCaminos, orig_claves: dict[str, int],
                  pares) -> dict[tuple[str, str], list[int]]:
    rev = g._rev_ady()
    caminos: dict[tuple[str, str], list[int]] = {}
    for i, j in pares:
        caminos[(i, j)] = _bidir(g, rev, orig_claves[i], orig_claves[j])
    return caminos


def _bidir(g, rev, s, t):
    if s == t:
        return [s]
    df = {s: 0.0}; db = {t: 0.0}
    pf: dict[int, int] = {}; pb: dict[int, int] = {}
    hf = [(0.0, s)]; hb = [(0.0, t)]
    vis_f: set[int] = set(); vis_b: set[int] = set()
    mejor = math.inf
    enc = None
    while hf and hb:
        if hf[0][0] + hb[0][0] >= mejor:
            break
        # avanza el frente más pequeño
        if hf[0][0] <= hb[0][0]:
            d, u = heapq.heappop(hf)
            if d > df.get(u, math.inf):
                continue
            vis_f.add(u)
            for v, w, _, _ in g.ady.get(u, []):
                nd = d + w
                if nd < df.get(v, math.inf):
                    df[v] = nd; pf[v] = u
                    heapq.heappush(hf, (nd, v))
                    if v in db and nd + db[v] < mejor:
                        mejor = nd + db[v]; enc = v
        else:
            d, u = heapq.heappop(hb)
            if d > db.get(u, math.inf):
                continue
            vis_b.add(u)
            for v, w in rev.get(u, []):
                nd = d + w
                if nd < db.get(v, math.inf):
                    db[v] = nd; pb[v] = u
                    heapq.heappush(hb, (nd, v))
                    if v in df and df[v] + nd < mejor:
                        mejor = df[v] + nd; enc = v
    if enc is None:
        raise RuntimeError(f"Sin camino {s}→{t}")
    # reconstruye s→enc (adelante) + enc→t (atrás)
    izq = [enc]
    while izq[-1] != s:
        izq.append(pf[izq[-1]])
    izq.reverse()
    der = []
    x = enc
    while x != t:
        x = pb[x]; der.append(x)
    return izq + der


# ----------------------------------------------------------------------------
# (3) A* par a par con heurística haversine admisible.
# ----------------------------------------------------------------------------
def a_estrella(g: GrafoCaminos, orig_claves: dict[str, int],
               pares) -> dict[tuple[str, str], list[int]]:
    caminos: dict[tuple[str, str], list[int]] = {}
    for i, j in pares:
        caminos[(i, j)] = _astar(g, orig_claves[i], orig_claves[j])
    return caminos


def _astar(g, s, t):
    if s == t:
        return [s]
    lat_t, lon_t, pot_t = g.lat[t], g.lon[t], g.pot[t]
    gsc = {s: 0.0}
    pred: dict[int, int] = {}
    h0 = g._h(s, lat_t, lon_t, pot_t)
    frontera = [(h0, s)]
    while frontera:
        _, u = heapq.heappop(frontera)
        if u == t:
            return g._reconstruir(pred, s, t)
        du = gsc[u]
        for v, w, _, _ in g.ady.get(u, []):
            nd = du + w
            if nd < gsc.get(v, math.inf):
                gsc[v] = nd
                pred[v] = u
                heapq.heappush(frontera, (nd + g._h(v, lat_t, lon_t, pot_t), v))
    raise RuntimeError(f"Sin camino {s}→{t}")


# ----------------------------------------------------------------------------
# (4) ALT (A*, Landmarks, Triangle inequality).
# ----------------------------------------------------------------------------
def alt(g: GrafoCaminos, orig_claves: dict[str, int], pares,
        n_landmarks: int = 8) -> dict[tuple[str, str], list[int]]:
    marcas, df, db = _precomputar_landmarks(g, n_landmarks)
    caminos: dict[tuple[str, str], list[int]] = {}
    for i, j in pares:
        caminos[(i, j)] = _astar_alt(g, orig_claves[i], orig_claves[j], marcas, df, db)
    return caminos


def _precomputar_landmarks(g: GrafoCaminos, k: int):
    """Elige k landmarks por farthest-point y precalcula distancias dir/rev."""
    nodos = list(g.ady.keys())
    if not nodos:
        return [], {}, {}
    rev = g._rev_ady()
    marcas = [nodos[0]]
    df: dict[int, dict[int, float]] = {}
    db: dict[int, dict[int, float]] = {}
    for _ in range(min(k, len(nodos))):
        L = marcas[-1]
        df[L] = _dist_completo(g.ady, L)
        db[L] = _dist_completo(rev, L)
        # siguiente landmark: el más lejano de los ya elegidos (ida)
        lejano, mejor = L, -1.0
        for v in nodos:
            dmin = min(df[m].get(v, math.inf) for m in marcas)
            if dmin != math.inf and dmin > mejor:
                mejor, lejano = dmin, v
        if lejano in marcas:
            break
        marcas.append(lejano)
    # garantiza distancias del último landmark
    for L in marcas:
        if L not in df:
            df[L] = _dist_completo(g.ady, L)
            db[L] = _dist_completo(rev, L)
    return marcas, df, db


def _dist_completo(ady, origen):
    dist = {origen: 0.0}
    h = [(0.0, origen)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist.get(u, math.inf):
            continue
        for item in ady.get(u, []):
            v, w = item[0], item[1]
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


def _h_alt(v, t, marcas, df, db):
    """Cota inferior por desigualdad triangular con landmarks (admisible)."""
    mejor = 0.0
    for L in marcas:
        dfL, dbL = df[L], db[L]
        # dist(v,t) ≥ dist(L,t) − dist(L,v)  y  ≥ dist(v,L) − dist(t,L)
        a = dfL.get(t, math.inf) - dfL.get(v, math.inf)
        b = dbL.get(v, math.inf) - dbL.get(t, math.inf)
        for cand in (a, b):
            if cand != math.inf and cand > mejor:
                mejor = cand
    return mejor


def _astar_alt(g, s, t, marcas, df, db):
    if s == t:
        return [s]
    gsc = {s: 0.0}
    pred: dict[int, int] = {}
    frontera = [(_h_alt(s, t, marcas, df, db), s)]
    while frontera:
        _, u = heapq.heappop(frontera)
        if u == t:
            return g._reconstruir(pred, s, t)
        du = gsc[u]
        for v, w, _, _ in g.ady.get(u, []):
            nd = du + w
            if nd < gsc.get(v, math.inf):
                gsc[v] = nd
                pred[v] = u
                heapq.heappush(frontera, (nd + _h_alt(v, t, marcas, df, db), v))
    raise RuntimeError(f"Sin camino {s}→{t}")


# ----------------------------------------------------------------------------
# (5) scipy.sparse.csgraph.dijkstra multi-origen.
# ----------------------------------------------------------------------------
def _csr(g: GrafoCaminos):
    if g._csr is None:
        import numpy as np
        from scipy.sparse import csr_matrix

        nodos = list(g.ady.keys())
        # incluye nodos que solo aparecen como destino
        extra = {v for vs in g.ady.values() for v, *_ in vs} - set(nodos)
        nodos += list(extra)
        idx = {v: k for k, v in enumerate(nodos)}
        filas, cols, datos = [], [], []
        for u, vecinos in g.ady.items():
            iu = idx[u]
            for v, w, _, _ in vecinos:
                filas.append(iu); cols.append(idx[v]); datos.append(w)
        n = len(nodos)
        M = csr_matrix((np.array(datos), (np.array(filas), np.array(cols))), shape=(n, n))
        g._nodos = nodos
        g._idx = idx
        g._csr = M
    return g._csr, g._idx, g._nodos


def scipy_multi(g: GrafoCaminos, orig_claves: dict[str, int],
                pares) -> dict[tuple[str, str], list[int]]:
    import numpy as np
    from scipy.sparse.csgraph import dijkstra

    M, idx, nodos = _csr(g)
    origenes = sorted({orig_claves[i] for i, _ in pares})
    src_idx = np.array([idx[o] for o in origenes])
    _, pred = dijkstra(M, directed=True, indices=src_idx, return_predecessors=True)
    fila_de = {o: k for k, o in enumerate(origenes)}
    caminos: dict[tuple[str, str], list[int]] = {}
    for i, j in pares:
        f = fila_de[orig_claves[i]]
        s_i, t_i = idx[orig_claves[i]], idx[orig_claves[j]]
        cam = [t_i]
        while cam[-1] != s_i:
            p = int(pred[f, cam[-1]])
            if p < 0:
                raise RuntimeError(f"Sin camino {i}→{j}")
            cam.append(p)
        caminos[(i, j)] = [nodos[k] for k in reversed(cam)]
    return caminos


# ----------------------------------------------------------------------------
# (6) networkx multi_source / single_source Dijkstra.
# ----------------------------------------------------------------------------
def _nx_grafo(g: GrafoCaminos):
    import networkx as nx

    H = nx.DiGraph()
    for u, vecinos in g.ady.items():
        for v, w, _, _ in vecinos:
            H.add_edge(u, v, weight=w)
    return H


def networkx_dijkstra(g: GrafoCaminos, orig_claves: dict[str, int],
                      pares) -> dict[tuple[str, str], list[int]]:
    import networkx as nx

    H = _nx_grafo(g)
    por_origen: dict[int, list[tuple[str, str]]] = {}
    for i, j in pares:
        por_origen.setdefault(orig_claves[i], []).append((i, j))
    caminos: dict[tuple[str, str], list[int]] = {}
    for s, lista in por_origen.items():
        _, caminos_nx = nx.single_source_dijkstra(H, s, weight="weight")
        for i, j in lista:
            t = orig_claves[j]
            if t not in caminos_nx:
                raise RuntimeError(f"Sin camino {i}→{j}")
            caminos[(i, j)] = list(caminos_nx[t])
    return caminos


ALGORITMOS = {
    "multi_destino": multi_destino,
    "bidireccional": bidireccional,
    "a_estrella": a_estrella,
    "alt": alt,
    "scipy": scipy_multi,
    "networkx": networkx_dijkstra,
}

# Mejor medido (ver docs/experimentos/caminos.md): scipy multi-origen.
ALGORITMO_POR_DEFECTO = "scipy"


def resolver_caminos(g: GrafoCaminos, orig_claves, pares, algoritmo: str | None = None):
    """Resuelve todos los pares con el algoritmo pedido (o el mejor por defecto)."""
    nombre = algoritmo or ALGORITMO_POR_DEFECTO
    fn = ALGORITMOS.get(nombre)
    if fn is None:
        raise ValueError(f"algoritmo_caminos={nombre!r} no válido; opciones: {sorted(ALGORITMOS)}")
    return fn(g, orig_claves, pares)
