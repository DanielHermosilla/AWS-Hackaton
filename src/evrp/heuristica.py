"""Heurística constructiva: tour gigante + 2-opt + partición óptima (split) con reparación de batería.

Sirve como (1) solución inicial del MILP, (2) certificado constructivo de N* = |C|
cuando atiende a todos los clientes y (3) solver autónomo (pipeline.solver=heuristica).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .instancia import DatosTipo, Instancia

PENAL_OMITIR = 1e6


@dataclass
class Solucion:
    # rutas[nombre_tipo] = lista de rutas; cada ruta es [ini, ..., fin] con ids clave
    rutas: dict[str, list[list[str]]] = field(default_factory=dict)
    atendidos: set[str] = field(default_factory=set)
    energia: float = 0.0
    origen: str = ""


def llegada(dt: DatosTipo, inst: Instancia, i: str, j: str, b: float) -> float | None:
    """Batería al llegar a j saliendo de i con b, o None si el arco no es factible."""
    s = dt.arcos.get((i, j))
    if s is None or b + 1e-9 < dt.tipo.b_min + s.pi:
        return None
    return min(b - s.e, dt.tipo.B - s.sig)


def _escape(dt: DatosTipo, inst: Instancia) -> dict[str, float]:
    """Batería mínima en cada cliente para poder alcanzar algún cargador o la base."""
    out = {}
    destinos = [*dt.F, inst.fin]
    for c in inst.clientes:
        pis = [dt.arcos[(c, g)].pi for g in destinos if (c, g) in dt.arcos]
        out[c] = dt.tipo.b_min + min(pis) if pis else math.inf
    return out


class Reparador:
    """Inserta cargadores en una secuencia de clientes para que la batería alcance."""

    def __init__(self, dt: DatosTipo, inst: Instancia):
        self.dt, self.inst = dt, inst
        self.esc = _escape(dt, inst)

    def _paso(self, u: str, b: float, j: str, umbral: float):
        """Mejor forma de ir de u a j llegando con >= umbral: directo o vía 1 cargador."""
        dt, inst = self.dt, self.inst
        a = llegada(dt, inst, u, j, b)
        if a is not None and a + 1e-9 >= umbral:
            return [j], a, dt.arcos[(u, j)].e
        mejor = None
        for f in dt.F:
            if f == u or llegada(dt, inst, u, f, b) is None:
                continue
            a2 = llegada(dt, inst, f, j, dt.tipo.B)
            if a2 is None or a2 + 1e-9 < umbral:
                continue
            costo = dt.arcos[(u, f)].e + dt.arcos[(f, j)].e
            if mejor is None or costo < mejor[2]:
                mejor = ([f, j], a2, costo)
        return mejor

    def ruta(self, secuencia: list[str]):
        """Devuelve (ruta [ini..fin], energía) o None si no es reparable."""
        dt, inst = self.dt, self.inst
        u, b = inst.ini, dt.tipo.b_ini
        ruta, total = [u], 0.0
        for j in secuencia:
            p = self._paso(u, b, j, self.esc[j])
            if p is None:
                return None
            nodos, b, costo = p
            ruta += nodos
            total += costo
            u = j
        p = self._paso(u, b, inst.fin, dt.tipo.b_min)
        if p is None:
            return None
        ruta += p[0]
        return ruta, total + p[2]


def _costo_tour(t: list[str], e) -> float:
    return sum(e(a, b) for a, b in zip(t, t[1:]))


def tour_gigante(inst: Instancia, clientes: list[str], dt: DatosTipo, tiempo_max_s: float = 10.0) -> list[str]:
    """Vecino más cercano desde la base + 2-opt, con ê del tipo dado (sin batería)."""
    import time as _time

    def e(a, b):
        s = dt.arcos.get((a, b))
        return s.e if s is not None else 1e9

    pend, actual, tour = set(clientes), inst.ini, []
    while pend:
        nxt = min(pend, key=lambda c: e(actual, c))
        tour.append(nxt)
        pend.remove(nxt)
        actual = nxt
    completo = [inst.ini, *tour, inst.fin]
    # 2-opt con evaluación incremental (delta de las 2 aristas que cambian): O(n^2)
    # por pasada en vez de O(n^3). Resultado idéntico; solo acelera. Tope de tiempo
    # para no consumir el presupuesto del MILP en instancias grandes.
    t0 = _time.perf_counter()
    mejora = True
    while mejora:
        mejora = False
        if _time.perf_counter() - t0 > tiempo_max_s:
            break
        for i in range(1, len(completo) - 2):
            a, b = completo[i - 1], completo[i]
            for k in range(i + 1, len(completo) - 1):
                c, d = completo[k], completo[k + 1]
                delta = (e(a, c) + e(b, d)) - (e(a, b) + e(c, d))
                if delta < -1e-9:
                    completo[i:k + 1] = completo[i:k + 1][::-1]
                    b = completo[i]
                    mejora = True
    return completo[1:-1]


def resolver(inst: Instancia, usar_todos: bool = False) -> Solucion:
    reps = {dt.tipo.nombre: Reparador(dt, inst) for dt in inst.tipos}
    # Clientes que ningún tipo puede atender ni siquiera solos se omiten.
    servibles = [c for c in inst.clientes if any(r.ruta([c]) is not None for r in reps.values())]
    if not servibles:
        sol = Solucion({dt.tipo.nombre: [] for dt in inst.tipos}, set(), 0.0, "heuristica")
        return sol
    tour = tour_gigante(inst, servibles, inst.tipos[0])
    n = len(tour)
    tipos = inst.tipos
    cache: dict[tuple[int, int, int], tuple | None] = {}

    def segmento(ti: int, i: int, j: int):
        k = (ti, i, j)
        if k not in cache:
            cache[k] = reps[tipos[ti].tipo.nombre].ruta(tour[i:j])
        return cache[k]

    # Split con omisión: estado = (posición, vehículos restantes por tipo).
    inicio = tuple(dt.tipo.cantidad for dt in tipos)
    dp: dict[tuple[int, tuple], tuple[float, tuple | None]] = {(0, inicio): (0.0, None)}
    for i in range(n):
        for (pos, rest), (costo, _) in [(k, v) for k, v in dp.items() if k[0] == i]:
            # omitir el cliente i
            k2 = (i + 1, rest)
            c2 = costo + PENAL_OMITIR
            if k2 not in dp or c2 < dp[k2][0]:
                dp[k2] = (c2, (pos, rest, "omitir", None, None))
            for ti, quedan in enumerate(rest):
                if quedan == 0:
                    continue
                r2 = rest[:ti] + (quedan - 1,) + rest[ti + 1:]
                for j in range(i + 1, n + 1):
                    seg = segmento(ti, i, j)
                    if seg is None:
                        continue
                    k3 = (j, r2)
                    c3 = costo + seg[1]
                    if k3 not in dp or c3 < dp[k3][0] - 1e-12:
                        dp[k3] = (c3, (pos, rest, "ruta", ti, seg))
    finales = [(v[0], k) for k, v in dp.items() if k[0] == n]
    if usar_todos:  # todos los vehículos deben salir (si alcanza el número de clientes)
        todos = [(c, k) for c, k in finales if not any(k[1])]
        finales = todos or finales
    _, clave = min(finales)
    secs: list[tuple[int, list[str]]] = []
    while dp[clave][1] is not None:
        pos, rest, accion, ti, seg = dp[clave][1]
        if accion == "ruta":
            secs.append((ti, [x for x in seg[0] if x in set(inst.clientes)]))
        clave = (pos, rest)
    # Una secuencia (posiblemente vacía) por vehículo, para la búsqueda local.
    por_veh: list[tuple[int, list[str]]] = []
    for ti, dt in enumerate(tipos):
        propias = [s for t_, s in secs if t_ == ti]
        por_veh += [(ti, s) for s in propias] + [(ti, [])] * (dt.tipo.cantidad - len(propias))
    por_veh = busqueda_local(por_veh, [reps[dt.tipo.nombre] for dt in tipos], no_vaciar=usar_todos)
    return _armar(inst, tipos, reps, por_veh, "heuristica")


def _armar(inst, tipos, reps, por_veh, origen) -> Solucion:
    sol = Solucion({dt.tipo.nombre: [] for dt in tipos}, set(), 0.0, origen)
    for ti, seq in por_veh:
        if not seq:
            continue
        ruta, costo = reps[tipos[ti].tipo.nombre].ruta(seq)
        sol.rutas[tipos[ti].tipo.nombre].append(ruta)
        sol.energia += costo
        sol.atendidos.update(seq)
    return sol


def busqueda_local(por_veh: list[tuple[int, list[str]]], reps: list[Reparador], max_pasadas: int = 50,
                   no_vaciar: bool = False, tiempo_max_s: float = 5.0):
    """Relocate (entre y dentro de rutas) + 2-opt intra-ruta, con costo reparado.

    no_vaciar: no deja vehículos sin clientes (solver.usar_todos_vehiculos).
    tiempo_max_s: tope de tiempo para que la heurística no consuma el presupuesto del MILP.
    """
    import time

    t0 = time.perf_counter()
    cache: dict[tuple[int, tuple], float] = {}

    def costo(ti, seq):
        if not seq:
            return 0.0
        k = (ti, tuple(seq))
        if k not in cache:
            r = reps[ti].ruta(seq)
            cache[k] = math.inf if r is None else r[1]
        return cache[k]

    rutas = [list(s) for _, s in por_veh]
    tis = [ti for ti, _ in por_veh]
    for _ in range(max_pasadas):
        if time.perf_counter() - t0 > tiempo_max_s:
            break
        mejora = False
        # relocate
        for a in range(len(rutas)):
            i = 0
            while i < len(rutas[a]):
                if no_vaciar and len(rutas[a]) == 1:
                    break
                c = rutas[a][i]
                sin = rutas[a][:i] + rutas[a][i + 1:]
                base = costo(tis[a], rutas[a])
                ahorro_quitar = base - costo(tis[a], sin)
                mejor = None
                for b in range(len(rutas)):
                    destino = sin if b == a else rutas[b]
                    cb = costo(tis[b], destino)
                    for p in range(len(destino) + 1):
                        cand = destino[:p] + [c] + destino[p:]
                        delta = costo(tis[b], cand) - cb - ahorro_quitar
                        if delta < -1e-9 and (mejor is None or delta < mejor[0]):
                            mejor = (delta, b, p)
                if mejor:
                    _, b, p = mejor
                    rutas[a] = sin
                    destino = rutas[a] if b == a else rutas[b]
                    destino.insert(p, c)
                    mejora = True
                else:
                    i += 1
        # 2-opt intra-ruta
        for a in range(len(rutas)):
            r = rutas[a]
            for i in range(len(r) - 1):
                for k in range(i + 1, len(r)):
                    cand = r[:i] + r[i:k + 1][::-1] + r[k + 1:]
                    if costo(tis[a], cand) < costo(tis[a], r) - 1e-9:
                        rutas[a] = r = cand
                        mejora = True
        if not mejora:
            break
    return list(zip(tis, rutas))
