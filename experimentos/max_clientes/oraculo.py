"""Oráculo independiente del MILP para instancias pequeñas (<= 8 clientes).

No usa los estadísticos (ê, π̂, σ̂, λ̂) ni la heurística ni HiGHS. Simula la batería
tramo a tramo con `inst.red.tramos` y el modelo de energía del tipo, exactamente como
el validador. Calcula el máximo de clientes atendibles (N*) y, para ese N*, la energía
mínima, por enumeración exhaustiva de subconjuntos y permutaciones, permitiendo
encadenar cargadores (F→F) mediante un camino de mínima energía entre dos "paradas de
servicio" (base/cliente) a través de cualquier número de cargadores.

Alcance: pensado para |C| <= 8 y flotas de 1–2 vehículos homogéneos. Es exponencial;
sirve como verdad de referencia, no como solver.
"""
from __future__ import annotations

import heapq
import math
from functools import lru_cache
from itertools import combinations, permutations

from evrp.instancia import DatosTipo, Instancia

INF = math.inf


def _tramos(inst: Instancia, u: str, v: str):
    """Tramos de la red mapeando el nodo-fin virtual a la base real."""
    return inst.red.tramos(inst.real(u), inst.real(v))


def _energia_tramo_a_tramo(inst: Instancia, dt: DatosTipo, u: str, v: str):
    """(energía total, batería mínima vista) de recorrer u->v saliendo lleno-relativo.

    Devuelve la energía del arco directo u->v (sin recargar en el camino) y el
    consumo acumulado necesario; la factibilidad depende de la batería de salida.
    """
    e = 0.0
    pico = 0.0  # consumo acumulado máximo (π̂ reconstruido por simulación directa)
    acc = 0.0
    for km, dh in _tramos(inst, u, v):
        x = dt.tipo.energia.tramo(km, dh)
        e += x
        acc += x
        pico = max(pico, acc)
    return e, pico


def _salida_llegada(inst, dt, u, v, b_salida):
    """Batería al llegar a v saliendo de u con b_salida, o None si no alcanza reserva.

    Simula tramo a tramo con tope B (regeneración no supera B) y exige >= b_min en todo
    momento. Independiente de los estadísticos del MILP.
    """
    B, bmin = dt.tipo.B, dt.tipo.b_min
    b = b_salida
    for km, dh in _tramos(inst, u, v):
        b = min(B, b - dt.tipo.energia.tramo(km, dh))
        if b < bmin - 1e-9:
            return None
    return b


def _dijkstra_servicio(inst: Instancia, dt: DatosTipo):
    """Para cada par (origen de servicio -> destino de servicio) devuelve la energía
    mínima del mejor camino que puede pasar por 0+ cargadores (recarga completa en cada
    uno). Orígenes: base y clientes (salen con B salvo la base, que sale con b_ini).
    Destinos: clientes, cargadores y la base de llegada.

    Modelo: un "estado" es (nodo, batería al llegar). En cada cargador se recarga a B.
    Entre paradas de servicio no se recarga. Buscamos el camino de energía mínima que
    conecte dos paradas respetando la reserva; esto cubre cadenas F->F.
    """
    F = list(dt.F)
    B, bmin = dt.tipo.B, dt.tipo.b_min

    def mejor_energia(origen: str, b_ini: float, destino: str) -> float:
        """Energía mínima para ir de `origen` (con b_ini) a `destino` pudiendo pasar por
        cargadores (recarga completa). Devuelve INF si no es alcanzable."""
        # Estado: nodo intermedio. En cargadores la batería se repone a B, así que el
        # estado "mejor batería" en un cargador es siempre B; basta rastrear energía mín.
        # Dijkstra sobre {origen} U F, relajando aristas a cualquier nodo.
        dist = {origen: 0.0}
        bat = {origen: b_ini}
        pq = [(0.0, origen)]
        best_dest = INF
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, INF) + 1e-12:
                continue
            bu = B if u in set(F) else bat[u]
            # intentar llegar directo al destino
            ll = _salida_llegada(inst, dt, u, destino, bu)
            if ll is not None:
                best_dest = min(best_dest, d + _energia_tramo_a_tramo(inst, dt, u, destino)[0])
            # expandir a cargadores
            for f in F:
                if f == u:
                    continue
                if _salida_llegada(inst, dt, u, f, bu) is None:
                    continue
                nd = d + _energia_tramo_a_tramo(inst, dt, u, f)[0]
                if nd < dist.get(f, INF) - 1e-12:
                    dist[f] = nd
                    bat[f] = B
                    heapq.heappush(pq, (nd, f))
        return best_dest

    return mejor_energia


def resolver_oraculo(inst: Instancia, max_clientes_enum: int = 8) -> dict:
    """Enumera subconjuntos de clientes y permutaciones para hallar N* y energía mínima.

    Flota homogénea de 1–2 vehículos del primer tipo. Si hay 2 vehículos, se parte el
    subconjunto atendido en dos rutas (una por vehículo). Devuelve N* y energía mínima.
    """
    if len(inst.tipos) != 1:
        raise ValueError("El oráculo asume flota homogénea (un tipo)")
    dt = inst.tipos[0]
    n_veh = dt.tipo.cantidad
    C = list(inst.clientes)
    if len(C) > max_clientes_enum:
        raise ValueError(f"Oráculo limitado a <= {max_clientes_enum} clientes; hay {len(C)}")
    mejor = _dijkstra_servicio(inst, dt)
    ini, fin = inst.ini, inst.fin
    b_ini, B = dt.tipo.b_ini, dt.tipo.B

    @lru_cache(maxsize=None)
    def energia_ruta(seq: tuple[str, ...]) -> float:
        """Energía mínima de una ruta base->seq->base (con cadenas de cargadores), o INF."""
        if not seq:
            return 0.0
        # primer tramo sale de la base con b_ini; los demás clientes salen con... su
        # batería al llegar. Pero como entre clientes puede haber cargadores que repongan,
        # el estado de salida de un cliente es su batería de llegada. Simulamos la cadena.
        return _energia_cadena(seq)

    def _energia_cadena(seq: tuple[str, ...]) -> float:
        # Simulación con estados: batería al salir de cada parada de servicio.
        # Entre dos paradas consecutivas se usa el mejor camino (con cargadores) factible
        # desde la batería disponible. Como un cargador en el camino repone a B, la
        # batería de llegada al siguiente cliente depende de si hubo recarga. Para ser
        # exactos y simples, probamos: (a) directo sin recargar; (b) con recarga (sale B).
        # Programación dinámica sobre (índice, bateria_discreta) sería ideal; aquí usamos
        # búsqueda recursiva con memo sobre (idx, bateria redondeada).
        paradas = [ini, *seq, fin]
        from functools import lru_cache as _lru

        @_lru(maxsize=None)
        def rec(idx: int, b_centi: int) -> float:
            if idx == len(paradas) - 1:
                return 0.0
            u = paradas[idx]
            v = paradas[idx + 1]
            b = b_centi / 100.0
            mejor_e = INF
            # (a) directo
            ll = _salida_llegada(inst, dt, u, v, b)
            if ll is not None:
                e = _energia_tramo_a_tramo(inst, dt, u, v)[0]
                resto = rec(idx + 1, int(round(ll * 100)))
                if resto < INF:
                    mejor_e = min(mejor_e, e + resto)
            # (b) vía cadena de cargadores (sale de u con b, llega a v)
            e_cad = _mejor_con_cadena(u, b, v)
            if e_cad < INF:
                # tras pasar por >=1 cargador, la batería al llegar a v es la de salir del
                # último cargador (B) menos el último tramo. La recalculamos aquí.
                ll2 = _bateria_llegada_cadena(u, b, v)
                if ll2 is not None:
                    resto = rec(idx + 1, int(round(ll2 * 100)))
                    if resto < INF:
                        mejor_e = min(mejor_e, e_cad + resto)
            return mejor_e

        return rec(0, int(round(b_ini * 100)))

    def _mejor_con_cadena(u, b, v):
        """Energía mínima u->v pasando por >=1 cargador, saliendo de u con batería b."""
        F = list(dt.F)
        dist = {}
        pq = []
        for f in F:
            if _salida_llegada(inst, dt, u, f, b) is not None:
                e = _energia_tramo_a_tramo(inst, dt, u, f)[0]
                if e < dist.get(f, INF):
                    dist[f] = e
                    heapq.heappush(pq, (e, f))
        best = INF
        while pq:
            d, f = heapq.heappop(pq)
            if d > dist.get(f, INF) + 1e-12:
                continue
            ll = _salida_llegada(inst, dt, f, v, B)
            if ll is not None:
                best = min(best, d + _energia_tramo_a_tramo(inst, dt, f, v)[0])
            for g in F:
                if g == f:
                    continue
                if _salida_llegada(inst, dt, f, g, B) is not None:
                    nd = d + _energia_tramo_a_tramo(inst, dt, f, g)[0]
                    if nd < dist.get(g, INF) - 1e-12:
                        dist[g] = nd
                        heapq.heappush(pq, (nd, g))
        return best

    def _bateria_llegada_cadena(u, b, v):
        """Batería al llegar a v por la cadena de mínima energía (sale del último F con B)."""
        # Aproximación: tras cualquier cadena, el último cargador deja salir con B, así que
        # la batería de llegada a v es B menos el consumo del tramo final. Buscamos el
        # tramo final de menor consumo factible desde algún cargador alcanzable.
        F = list(dt.F)
        alcanzables = set()
        dist = {}
        pq = []
        for f in F:
            if _salida_llegada(inst, dt, u, f, b) is not None:
                dist[f] = _energia_tramo_a_tramo(inst, dt, u, f)[0]
                heapq.heappush(pq, (dist[f], f))
        while pq:
            d, f = heapq.heappop(pq)
            if d > dist.get(f, INF) + 1e-12:
                continue
            alcanzables.add(f)
            for g in F:
                if g != f and _salida_llegada(inst, dt, f, g, B) is not None:
                    nd = d + _energia_tramo_a_tramo(inst, dt, f, g)[0]
                    if nd < dist.get(g, INF) - 1e-12:
                        dist[g] = nd
                        heapq.heappush(pq, (nd, g))
        mejor_ll = None
        mejor_e = INF
        for f in alcanzables:
            ll = _salida_llegada(inst, dt, f, v, B)
            if ll is not None:
                e_total = dist[f] + _energia_tramo_a_tramo(inst, dt, f, v)[0]
                if e_total < mejor_e:
                    mejor_e = e_total
                    mejor_ll = ll
        return mejor_ll

    # Buscar el mayor subconjunto atendible.
    mejor_n = 0
    mejor_energia = INF
    for n in range(len(C), 0, -1):
        if n < mejor_n:
            break
        hay = False
        for sub in combinations(C, n):
            e = _mejor_particion(sub, n_veh, energia_ruta)
            if e < INF:
                hay = True
                if n > mejor_n or (n == mejor_n and e < mejor_energia):
                    mejor_n = n
                    mejor_energia = e
        if hay:
            # ya encontramos el N* máximo; refinamos energía sobre ese tamaño
            # (el bucle de n descendente garantiza que este es el máximo)
            break
    if mejor_n == 0:
        return {"n_estrella": 0, "energia": 0.0}
    return {"n_estrella": mejor_n, "energia": round(mejor_energia, 6)}


def _mejor_particion(sub: tuple[str, ...], n_veh: int, energia_ruta) -> float:
    """Energía mínima para atender exactamente `sub` con <= n_veh rutas."""
    mejor = INF
    if n_veh == 1:
        for perm in permutations(sub):
            e = energia_ruta(perm)
            if e < mejor:
                mejor = e
        return mejor
    # 2 vehículos: partir sub en dos grupos (uno puede ir vacío) y permutar cada uno.
    sub = list(sub)
    m = len(sub)
    for r in range(0, m // 2 + 1):
        for grupo_a in combinations(sub, r):
            resto = [x for x in sub if x not in grupo_a]
            ea = _mejor_particion(tuple(grupo_a), 1, energia_ruta)
            if ea >= INF:
                continue
            eb = _mejor_particion(tuple(resto), 1, energia_ruta)
            if eb >= INF:
                continue
            mejor = min(mejor, ea + eb)
    return mejor
