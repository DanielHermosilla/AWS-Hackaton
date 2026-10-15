"""Formulación compacta: los cargadores se modelan como atributos de arco.

Cada arco a = (i, j, f) une dos nodos "de servicio" (base o clientes) directamente
(f = None) o pasando por UN cargador f. Como la carga es completa e instantánea,
entre dos clientes consecutivos basta un cargador salvo que el alcance obligue a
encadenar cargadores (F→F); ese caso queda fuera de esta formulación (usar
solver.formulacion = completa). Para cada par (i, j) se conservan los cargadores
Pareto-óptimos en (energía, batería requerida al salir, batería al llegar), hasta
`cargadores_por_arco`, más los que use la solución inicial.

Conectividad: MTZ con elevación de Desrochers–Laporte sobre las posiciones u_i.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass

import highspy
import numpy as np

from .heuristica import Solucion
from .instancia import DatosTipo, Instancia

log = logging.getLogger(__name__)
FACTIBLE = 2


def _presupuesto_adaptativo(limite: float, n_clientes: int, columnas: int, esc: dict) -> float:
    """Ajusta el presupuesto del MILP para acotar el tiempo TOTAL del pipeline.

    `limite` ya es el presupuesto del MILP (el llamador puede haberle restado el
    tiempo de red+heurística). Aquí solo imponemos un piso: para n_clientes grandes
    el MILP con poda k-vecinos sí mejora el arranque, así que no recortamos por tamaño;
    únicamente garantizamos un mínimo útil `min_s` (por defecto 10 s). Para instancias
    pequeñas (<= `umbral_pequeno`, por defecto 25) se mantiene el presupuesto completo
    para preservar el óptimo probado a 20 clientes.
    """
    min_s = float(esc.get("min_s", 10.0))
    return max(min_s, limite)


@dataclass(frozen=True)
class Arco:
    i: str
    j: str
    f: str | None
    e: float        # energía total del arco
    req: float      # π̂ del primer tramo (batería extra necesaria al salir de i)
    llegada: float  # batería al llegar a j si se sale de f (o de la base); nan si i es cliente directo
    sig: float      # σ̂ del tramo que llega a j (para (9) en arcos directos cliente→cliente)


def arcos_compactos(dt: DatosTipo, inst: Instancia, max_f: int, obligatorios: set) -> list[Arco]:
    Cs = set(inst.clientes)
    origenes = [inst.ini, *inst.clientes]
    destinos = [*inst.clientes, inst.fin]
    B = dt.tipo.B
    out: list[Arco] = []
    for i in origenes:
        beta_i = dt.tipo.b_ini if i == inst.ini else None
        for j in destinos:
            if i == j:
                continue
            if i == inst.ini and j == inst.fin:
                out.append(Arco(i, j, None, 0.0, 0.0, B, 0.0))
                continue
            d = dt.arcos.get((i, j))
            if d is not None:
                lleg = min(beta_i - d.e, B - d.sig) if beta_i is not None else float("nan")
                out.append(Arco(i, j, None, d.e, d.pi, lleg, d.sig))
            cands = []
            for f in dt.F:
                a, b = dt.arcos.get((i, f)), dt.arcos.get((f, j))
                if a is None or b is None:
                    continue
                cands.append(Arco(i, j, f, a.e + b.e, a.pi, min(B - b.e, B - b.sig), b.sig))
            pareto = [c for c in cands if not any(
                (o.e <= c.e and o.req <= c.req and o.llegada >= c.llegada) and
                (o.e < c.e or o.req < c.req or o.llegada > c.llegada) for o in cands)]
            pareto.sort(key=lambda c: c.e)
            elegidos = pareto[:max_f]
            elegidos += [c for c in cands if (i, j, c.f) in obligatorios and c not in elegidos]
            out.extend(elegidos)
    return out


def _tramos_de(ruta: list[str], cargadores: set[str]) -> list[tuple[str, str, str | None]]:
    """[ini, a, f, b, fin] -> [(ini,a,None), (a,b,f), (b,fin,None)]. Falla si hay F→F."""
    out, i, f = [], ruta[0], None
    for v in ruta[1:]:
        if v in cargadores:
            if f is not None:
                raise ValueError("La ruta encadena cargadores; requiere la formulación completa")
            f = v
        else:
            out.append((i, v, f))
            i, f = v, None
    return out


class ModeloCompacto:
    def __init__(self, inst: Instancia, cfg_solver: dict, inicial: Solucion | None = None):
        self.inst, self.cfg = inst, cfg_solver
        self.h = h = highspy.Highs()
        if not cfg_solver.get("mostrar_log"):
            h.silent()
        if cfg_solver.get("hilos"):
            h.setOptionValue("threads", int(cfg_solver["hilos"]))
        h.setOptionValue("mip_rel_gap", float(cfg_solver.get("gap_relativo", 0.0)))
        esc = cfg_solver.get("escala", {}) or {}
        if esc.get("mip_heuristic_effort") is not None:
            h.setOptionValue("mip_heuristic_effort", float(esc["mip_heuristic_effort"]))
        if esc.get("presolve"):
            h.setOptionValue("presolve", str(esc["presolve"]))
        if esc.get("mip_detect_symmetry") is not None:
            h.setOptionValue("mip_detect_symmetry", bool(esc["mip_detect_symmetry"]))
        self.inicial = inicial
        self.x: dict[tuple[int, Arco], highspy.highs_var] = {}
        self.b, self.u, self.y = {}, {}, {}
        self.arcos: dict[int, list[Arco]] = {}
        self._construir(int(cfg_solver.get("cargadores_por_arco", 3)))

    def _obligatorios(self, dt: DatosTipo) -> set:
        if not self.inicial:
            return set()
        Fs = set(dt.F)
        return {t for r in self.inicial.rutas.get(dt.tipo.nombre, []) for t in _tramos_de(r, Fs)}

    def _construir(self, max_f: int):
        inst, h = self.inst, self.h
        C, Cs, nC = inst.clientes, set(inst.clientes), len(inst.clientes)
        cfg_todos = bool(self.cfg.get("usar_todos_vehiculos")) and \
            sum(dt.tipo.cantidad for dt in inst.tipos) <= nC
        for c in C:
            self.y[c] = h.addBinary(name=f"y_{c}")
            self.u[c] = h.addVariable(lb=1, ub=max(1, nC), name=f"u_{c}")
        visitas, E = defaultdict(list), []
        X = defaultdict(list)  # (i,j) clientes -> x de todos los tipos y cargadores
        for t, dt in enumerate(inst.tipos):
            B, bmin, n = dt.tipo.B, dt.tipo.b_min, dt.tipo.cantidad
            arcos = arcos_compactos(dt, inst, max_f, self._obligatorios(dt))
            self.arcos[t] = arcos
            ent, sal = defaultdict(list), defaultdict(list)
            for c in C:
                self.b[(c, t)] = h.addVariable(lb=0, ub=B, name=f"b_{c}_{t}")
            for a in arcos:
                if a.i == inst.ini and a.j == inst.fin:
                    v = h.addIntegral(lb=0, ub=0 if cfg_todos else n, name=f"x_idle_{t}")
                else:
                    v = h.addBinary(name=f"x_{a.i}_{a.j}_{a.f}_{t}")
                self.x[(t, a)] = v
                sal[a.i].append(v)
                ent[a.j].append(v)
                E.append(a.e * v)
                if a.i in Cs and a.j in Cs:
                    X[(a.i, a.j)].append(v)
                if a.j in Cs:
                    if a.i == inst.ini or a.f is not None:                     # (7)
                        h.addConstr(self.b[(a.j, t)] + (B - a.llegada) * v <= B)
                    else:                                                      # (8),(9)
                        h.addConstr(self.b[(a.j, t)] - self.b[(a.i, t)] + (a.e + B) * v <= B)
                        if a.sig > 0:
                            h.addConstr(self.b[(a.j, t)] + a.sig * v <= B)
                if a.i in Cs:                                                  # (10)
                    h.addConstr(self.b[(a.i, t)] - (bmin + a.req) * v >= 0)
            h.addConstr(h.qsum(sal[inst.ini]) == n)                            # (1)
            for c in C:
                h.addConstr(h.qsum(ent[c]) - h.qsum(sal[c]) == 0)              # (2)
                visitas[c].extend(ent[c])
        for c in C:
            h.addConstr(self.y[c] - h.qsum(visitas[c]) == 0)                    # (3)
        # MTZ elevado (Desrochers–Laporte): u_j ≥ u_i + 1 − nC(1 − X_ij) + (nC − 2) X_ji
        for (i, j), xs in X.items():
            inv = X.get((j, i), [])
            expr = self.u[j] - self.u[i] - nC * h.qsum(xs)
            if inv and nC > 2:
                expr = expr - (nC - 2) * h.qsum(inv)
            h.addConstr(expr >= 1 - nC)
        self.E = h.qsum(E)
        self.Y = h.qsum(list(self.y.values()))

    # ------------------------------------------------------------ utilidades
    def _objetivo(self, sentido, expr):
        h, n = self.h, self.h.getNumCol()
        h.changeColsCost(n, np.arange(n, dtype=np.int32), np.zeros(n))
        idx = np.array(expr.idxs, dtype=np.int32)
        h.changeColsCost(len(idx), idx, np.array(expr.vals, dtype=float))
        h.changeObjectiveSense(highspy.ObjSense.kMaximize if sentido == "max" else highspy.ObjSense.kMinimize)

    def _resolver(self, limite):
        h = self.h
        h.setOptionValue("time_limit", max(0.5, float(limite)))
        h.run()
        info = h.getInfo()
        return h.modelStatusToString(h.getModelStatus()), info.primal_solution_status == FACTIBLE, info

    def _vector_inicial(self, sol: Solucion) -> list[float]:
        inst = self.inst
        val = [0.0] * self.h.getNumCol()
        Cs = set(inst.clientes)
        for t, dt in enumerate(inst.tipos):
            indice = {(a.i, a.j, a.f): a for a in self.arcos[t]}
            rutas = sol.rutas.get(dt.tipo.nombre, [])
            for ruta in rutas:
                b = dt.tipo.b_ini
                pos = 0
                for (i, j, f) in _tramos_de(ruta, set(dt.F)):
                    a = indice[(i, j, f)]
                    val[self.x[(t, a)].index] = 1
                    if i == inst.ini or f is not None:
                        b = a.llegada
                    else:
                        b = min(b - a.e, dt.tipo.B - a.sig)
                    if j in Cs:
                        pos += 1
                        val[self.b[(j, t)].index] = b
                        val[self.y[j].index] = 1
                        val[self.u[j].index] = pos
            idle = indice[(inst.ini, inst.fin, None)]
            val[self.x[(t, idle)].index] = dt.tipo.cantidad - len(rutas)
        for c in inst.clientes:  # u de clientes no atendidos: cualquier valor válido
            if val[self.y[c].index] == 0:
                val[self.u[c].index] = 1
        return val

    def _iniciar_con(self, vec):
        s = highspy.HighsSolution()
        s.col_value = list(vec)
        s.value_valid = True
        self.h.setSolution(s)

    # --------------------------------------------------------------- principal
    def optimizar(self, inicial: Solucion | None, todos_certificados: bool):
        h, inst = self.h, self.inst
        t0 = time.perf_counter()
        limite = float(self.cfg.get("tiempo_limite_s", 60))
        esc = self.cfg.get("escala", {}) or {}
        if esc.get("adaptativo"):
            limite = _presupuesto_adaptativo(limite, len(inst.clientes), h.getNumCol(), esc)
        traza = {"formulacion": "compacta", "columnas": h.getNumCol(), "filas": h.getNumRow(),
                 "limite_s": round(limite, 2)}
        vec0 = self._vector_inicial(inicial) if inicial else None
        if todos_certificados:
            h.addConstr(self.Y == len(inst.clientes))
            traza["fase1"] = "omitida (certificado constructivo N*=|C|)"
            n_est = len(inst.clientes)
        else:
            self._objetivo("max", self.Y)
            if vec0:
                self._iniciar_con(vec0)
            estado, hay, info = self._resolver(limite / 2)
            traza["fase1"] = {"estado": estado, "N*": round(info.objective_function_value) if hay else None}
            if not hay:
                return None, traza
            n_est = round(info.objective_function_value)
            vec0 = list(h.getSolution().col_value)
            h.addConstr(self.Y >= n_est)
        self._objetivo("min", self.E)
        if vec0:
            self._iniciar_con(vec0)
        estado, hay, info = self._resolver(limite - (time.perf_counter() - t0))
        traza["fase2"] = {"estado": estado, "energia": info.objective_function_value if hay else None,
                          "cota": info.mip_dual_bound, "gap": info.mip_gap if hay else None}
        traza["N*"] = n_est
        traza["tiempo_s"] = round(time.perf_counter() - t0, 3)
        if not hay:
            return None, traza
        return self._extraer(list(h.getSolution().col_value)), traza

    def _extraer(self, val) -> Solucion:
        inst = self.inst
        sol = Solucion({dt.tipo.nombre: [] for dt in inst.tipos}, set(), 0.0, "milp")
        for t, dt in enumerate(inst.tipos):
            sucesores = defaultdict(list)
            for a in self.arcos[t]:
                k = int(round(val[self.x[(t, a)].index]))
                if k and not (a.i == inst.ini and a.j == inst.fin):
                    sucesores[a.i].extend([a] * k)
                    sol.energia += k * a.e
            for a in sucesores[inst.ini]:
                ruta, actual, guard = [inst.ini], a, 0
                while True:
                    if actual.f:
                        ruta.append(actual.f)
                    ruta.append(actual.j)
                    if actual.j == inst.fin or guard > len(inst.clientes) + 1:
                        break
                    if not sucesores[actual.j]:  # redondeo numérico: ruta incompleta
                        log.warning("Ruta sin sucesor en %s; el validador la rechazará", actual.j)
                        break
                    actual = sucesores[actual.j].pop(0)
                    guard += 1
                sol.rutas[dt.tipo.nombre].append(ruta)
                sol.atendidos.update(v for v in ruta if v in set(inst.clientes))
        return sol
