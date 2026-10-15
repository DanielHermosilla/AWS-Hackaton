"""MILP de flujo en arcos sobre el grafo contraído (modelo consolidado, restricciones (1)–(12)).

Variables por tipo θ: x_ijθ (veces que se recorre P_ij), b_iθ (batería al llegar al
cliente i) y, en modo 'flujo', φ_ijθ (flujo de conectividad). Globales: y_i (entrega).
Objetivo lexicográfico: P1 max Σ y_i ; P2 min E_total = Σ ê_ij x_ijθ con Σ y_i = N*.

Conectividad (solver.conectividad):
  flujo  — restricciones (4)–(6),(12) con φ (compacto, relajación débil).
  cortes — sin φ; se agregan cortes de conectividad Σ_{arcos que entran a S} x ≥ V_i
           para cada cliente i de una componente S desconectada de la base, y se
           vuelve a resolver (relajación más fuerte; exacto al terminar sin cortes nuevos).
Los ciclos solo-cliente ya son imposibles por (8) (suma de ê > 0 en el ciclo).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import highspy
import numpy as np

from .heuristica import Solucion, llegada
from .instancia import Instancia

log = logging.getLogger(__name__)

FACTIBLE = 2  # HighsSolutionStatus kSolutionStatusFeasible


class ModeloMILP:
    def __init__(self, inst: Instancia, cfg_solver: dict):
        self.inst = inst
        self.cfg = cfg_solver
        self.modo = cfg_solver.get("conectividad", "cortes")
        if self.modo not in ("flujo", "cortes"):
            raise ValueError("solver.conectividad debe ser 'flujo' o 'cortes'")
        self.h = highspy.Highs()
        h = self.h
        if not cfg_solver.get("mostrar_log"):
            h.silent()
        if cfg_solver.get("hilos"):
            h.setOptionValue("threads", int(cfg_solver["hilos"]))
        h.setOptionValue("mip_rel_gap", float(cfg_solver.get("gap_relativo", 0.0)))
        self.x, self.phi, self.b, self.y = {}, {}, {}, {}
        self.ent: dict[int, dict] = {}
        self.cortes = 0
        self._construir()

    # ------------------------------------------------------------------ modelo
    def _construir(self):
        inst, h = self.inst, self.h
        C = inst.clientes
        Cs = set(C)
        nC = len(C)
        U = nC + sum(dt.tipo.cantidad for dt in inst.tipos)
        flujo = self.modo == "flujo"
        for c in C:
            self.y[c] = h.addBinary(name=f"y_{c}")
        visitas = defaultdict(list)
        E = []
        for t, dt in enumerate(inst.tipos):
            n = dt.tipo.cantidad
            B, bmin = dt.tipo.B, dt.tipo.b_min
            Fs = set(dt.F)
            ent, sal = defaultdict(list), defaultdict(list)
            fent, fsal = defaultdict(list), defaultdict(list)
            for (i, j), s in dt.arcos.items():
                if i in Cs or j in Cs:
                    v = h.addBinary(name=f"x_{i}_{j}_{t}")
                elif i in Fs and j in Fs:
                    v = h.addIntegral(lb=0, ub=U, name=f"x_{i}_{j}_{t}")
                else:
                    ub_ = 0 if (i == inst.ini and j == inst.fin and self.cfg.get("usar_todos_vehiculos")
                                and sum(d.tipo.cantidad for d in inst.tipos) <= nC) else n
                    v = h.addIntegral(lb=0, ub=ub_, name=f"x_{i}_{j}_{t}")
                self.x[(i, j, t)] = v
                sal[i].append(v)
                ent[j].append(v)
                E.append(s.e * v)
                if flujo:
                    p = h.addVariable(lb=0, ub=nC, name=f"phi_{i}_{j}_{t}")
                    self.phi[(i, j, t)] = p
                    fsal[i].append(p)
                    fent[j].append(p)
                    h.addConstr(p - nC * v <= 0)                               # (4)
                    if j in Cs:
                        h.addConstr(p - v >= 0)                                # (12)
            self.ent[t] = ent
            for c in C:
                self.b[(c, t)] = h.addVariable(lb=0, ub=B, name=f"b_{c}_{t}")
            h.addConstr(h.qsum(sal[inst.ini]) == n)                            # (1)
            for v_ in [*C, *dt.F]:
                h.addConstr(h.qsum(ent[v_]) - h.qsum(sal[v_]) == 0)            # (2)
            for c in C:
                visitas[c].extend(ent[c])
                if flujo:
                    h.addConstr(h.qsum(fent[c]) - h.qsum(fsal[c]) - h.qsum(ent[c]) == 0)  # (5)
            if flujo:
                for f in dt.F:
                    h.addConstr(h.qsum(fent[f]) - h.qsum(fsal[f]) == 0)        # (6)
            for (i, j), s in dt.arcos.items():
                v = self.x[(i, j, t)]
                if j in Cs and (i == inst.ini or i in Fs):                     # (7)
                    rho = dt.rho(i, j, inst.ini)
                    h.addConstr(self.b[(j, t)] + (B - rho) * v <= B)
                if i in Cs and j in Cs:
                    h.addConstr(self.b[(j, t)] - self.b[(i, t)] + (s.e + B) * v <= B)  # (8)
                    if s.sig > 0:
                        h.addConstr(self.b[(j, t)] + s.sig * v <= B)          # (9)
                if i in Cs:
                    h.addConstr(self.b[(i, t)] - (bmin + s.pi) * v >= 0)      # (10)
        for c in C:
            h.addConstr(self.y[c] - h.qsum(visitas[c]) == 0)                    # (3)
        self.E = h.qsum(E)                                                     # (11)
        self.Y = h.qsum(list(self.y.values()))

    # ------------------------------------------------------- solución inicial
    def _vector_inicial(self, sol: Solucion) -> list[float]:
        inst = self.inst
        val = [0.0] * self.h.getNumCol()
        Cs = set(inst.clientes)
        for t, dt in enumerate(inst.tipos):
            rutas = sol.rutas.get(dt.tipo.nombre, [])
            for ruta in rutas:
                b = dt.tipo.b_ini
                for k, (u, v) in enumerate(zip(ruta, ruta[1:])):
                    val[self.x[(u, v, t)].index] += 1
                    if self.phi:
                        val[self.phi[(u, v, t)].index] += sum(1 for z in ruta[k + 1:] if z in Cs)
                    b = llegada(dt, inst, u, v, b)
                    if v in Cs:
                        val[self.b[(v, t)].index] = b
                        val[self.y[v].index] = 1
                    elif v != inst.fin:
                        b = dt.tipo.B
            val[self.x[(inst.ini, inst.fin, t)].index] += dt.tipo.cantidad - len(rutas)
        return val

    def _iniciar_con(self, vector):
        s = highspy.HighsSolution()
        s.col_value = list(vector)
        s.value_valid = True
        self.h.setSolution(s)

    def _objetivo(self, sentido: str, expr):
        """Fija el objetivo sin resolver (h.minimize/maximize descartan la solución inicial)."""
        h = self.h
        n = h.getNumCol()
        h.changeColsCost(n, np.arange(n, dtype=np.int32), np.zeros(n))
        idx = np.array(expr.idxs, dtype=np.int32)
        h.changeColsCost(len(idx), idx, np.array(expr.vals, dtype=float))
        h.changeObjectiveSense(highspy.ObjSense.kMaximize if sentido == "max" else highspy.ObjSense.kMinimize)

    def _resolver(self, limite: float):
        h = self.h
        h.setOptionValue("time_limit", max(0.5, float(limite)))
        h.run()
        info = h.getInfo()
        return h.modelStatusToString(h.getModelStatus()), info.primal_solution_status == FACTIBLE, info

    # ------------------------------------------------------ cortes perezosos
    def _agregar_cortes(self, valores) -> int:
        """Agrega cortes para las componentes desconectadas de la base. Devuelve cuántos."""
        inst, h = self.inst, self.h
        Cs = set(inst.clientes)
        nuevos = 0
        for t, dt in enumerate(inst.tipos):
            ady = defaultdict(set)
            nodos_usados = set()
            for (i, j) in dt.arcos:
                if valores[self.x[(i, j, t)].index] > 0.5:
                    ady[i].add(j)
                    nodos_usados.update((i, j))
            alcanzables = {inst.ini}
            cola = deque([inst.ini])
            while cola:
                u = cola.popleft()
                for v in ady[u]:
                    if v not in alcanzables:
                        alcanzables.add(v)
                        cola.append(v)
            sueltos = nodos_usados - alcanzables
            for S in _componentes(sueltos, ady):
                clientes_S = [c for c in S if c in Cs]
                if not clientes_S:
                    continue
                entrada = [self.x[(i, j, t)] for (i, j) in dt.arcos if j in S and i not in S]
                for c in clientes_S:
                    h.addConstr(h.qsum(entrada) - h.qsum(self.ent[t][c]) >= 0)
                    nuevos += 1
        self.cortes += nuevos
        return nuevos

    def _resolver_con_cortes(self, limite: float, t0: float, inicial_vec):
        """Resuelve el objetivo vigente agregando cortes hasta obtener una solución conexa."""
        iteraciones = 0
        while True:
            iteraciones += 1
            if inicial_vec is not None:
                self._iniciar_con(inicial_vec)
            restante = limite - (time.perf_counter() - t0)
            estado, hay, info = self._resolver(restante)
            if not hay:
                return estado, False, info, None, iteraciones
            valores = list(self.h.getSolution().col_value)
            if self.modo == "flujo" or self._agregar_cortes(valores) == 0:
                return estado, True, info, valores, iteraciones
            if time.perf_counter() - t0 >= limite:
                return "Time limit reached (cortes pendientes)", False, info, None, iteraciones

    # --------------------------------------------------------------- principal
    def optimizar(self, inicial: Solucion | None, todos_certificados: bool) -> tuple[Solucion | None, dict]:
        h, inst = self.h, self.inst
        t0 = time.perf_counter()
        limite = float(self.cfg.get("tiempo_limite_s", 60))
        traza: dict = {"conectividad": self.modo, "columnas": h.getNumCol(), "filas": h.getNumRow()}
        vec0 = self._vector_inicial(inicial) if inicial else None
        if todos_certificados:
            h.addConstr(self.Y == len(inst.clientes))
            traza["fase1"] = "omitida (certificado constructivo N*=|C|)"
            n_estrella = len(inst.clientes)
        else:
            self._objetivo("max", self.Y)
            estado, hay, info, valores, it = self._resolver_con_cortes(limite / 2, t0, vec0)
            traza["fase1"] = {"estado": estado, "iteraciones": it,
                              "N*": round(info.objective_function_value) if hay else None}
            if not hay:
                return None, traza
            n_estrella = round(info.objective_function_value)
            vec0 = valores
            h.addConstr(self.Y >= n_estrella)
        self._objetivo("min", self.E)
        estado, hay, info, valores, it = self._resolver_con_cortes(limite, t0, vec0)
        traza["fase2"] = {"estado": estado, "iteraciones": it, "cortes": self.cortes,
                          "energia": info.objective_function_value if hay else None,
                          "cota": info.mip_dual_bound, "gap": info.mip_gap if hay else None}
        traza["N*"] = n_estrella
        traza["tiempo_s"] = round(time.perf_counter() - t0, 3)
        if not hay:
            return None, traza
        return self._extraer(valores), traza

    # -------------------------------------------------------------- extracción
    def _extraer(self, valores: list[float]) -> Solucion:
        inst = self.inst
        sol = Solucion({dt.tipo.nombre: [] for dt in inst.tipos}, set(), 0.0, "milp")
        Cs = set(inst.clientes)
        for t, dt in enumerate(inst.tipos):
            ady: dict[str, list[str]] = defaultdict(list)
            for (i, j), s in dt.arcos.items():
                k = int(round(valores[self.x[(i, j, t)].index]))
                ady[i].extend([j] * k)
                sol.energia += k * s.e
            ady[inst.fin].extend([inst.ini] * dt.tipo.cantidad)
            rutas, actual = [], []
            for v in _hierholzer(ady, inst.ini):
                if v == inst.ini:
                    actual = [v]
                    continue
                actual.append(v)
                if v == inst.fin:
                    rutas.append(actual)
            rutas = [r for r in rutas if any(z in Cs for z in r)]
            rutas.sort(key=len, reverse=True)
            sol.rutas[dt.tipo.nombre] = rutas
            for r in rutas:
                sol.atendidos.update(z for z in r if z in Cs)
        return sol


def _componentes(nodos: set[str], ady) -> list[set[str]]:
    """Componentes conexas (no dirigidas) del subgrafo inducido por `nodos`."""
    vecinos = defaultdict(set)
    for u in nodos:
        for v in ady[u]:
            if v in nodos:
                vecinos[u].add(v)
                vecinos[v].add(u)
    vistos, comps = set(), []
    for s in nodos:
        if s in vistos:
            continue
        comp, pila = set(), [s]
        while pila:
            u = pila.pop()
            if u in comp:
                continue
            comp.add(u)
            pila.extend(vecinos[u] - comp)
        vistos |= comp
        comps.append(comp)
    return comps


def _hierholzer(ady: dict[str, list[str]], inicio: str) -> list[str]:
    """Circuito euleriano dirigido desde `inicio` (solo la componente alcanzable)."""
    pend = {u: list(vs) for u, vs in ady.items()}
    pila, circuito = [inicio], []
    while pila:
        u = pila[-1]
        if pend.get(u):
            pila.append(pend[u].pop())
        else:
            circuito.append(pila.pop())
    return circuito[::-1]
