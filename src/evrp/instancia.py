"""Instancia contraída: nodos clave, estadísticos de camino y arcos factibles por tipo.

Notación (ver docs/base_conocimiento.md y el modelo consolidado):
  ê  energía total del camino P_ij
  π̂  pico de consumo acumulado (batería extra necesaria al salir)
  σ̂  ê − mínimo acumulado (limita la regeneración almacenable)
  λ̂  máximo tramo continuo de consumo
  β_i batería al salir de la base (b_ini) o de un cargador (B)
  ρ_ij batería al llegar a j saliendo de i ∈ {0} ∪ F
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import reserva_kwh
from .datos import Nodo, compatible
from .energia import ModeloEnergia
from .red import Red

FIN_SUFIJO = "#fin"
EPS = 1e-9


@dataclass(frozen=True)
class Estad:
    e: float    # ê
    pi: float   # π̂
    sig: float  # σ̂
    lam: float  # λ̂


def estadisticos(energias: list[float]) -> Estad:
    s = mn = pico = lam = 0.0
    for x in energias:
        s += x
        pico = max(pico, s)
        mn = min(mn, s)
        lam = max(lam, s - mn)
    return Estad(s, pico, s - mn, lam)


@dataclass
class TipoVehiculo:
    nombre: str
    cantidad: int
    B: float
    b_ini: float
    b_min: float
    conectores: set[str]
    energia: ModeloEnergia


@dataclass
class DatosTipo:
    tipo: TipoVehiculo
    F: list[str]                                  # cargadores compatibles (tras poda)
    arcos: dict[tuple[str, str], Estad]           # A_θ con sus estadísticos
    descartados_compat: list[str] = field(default_factory=list)
    podados: list[str] = field(default_factory=list)

    def beta(self, i: str, ini: str) -> float:
        return self.tipo.b_ini if i == ini else self.tipo.B

    def rho(self, i: str, j: str, ini: str) -> float:
        s = self.arcos[(i, j)]
        return min(self.beta(i, ini) - s.e, self.tipo.B - s.sig)


@dataclass
class Instancia:
    nodos: dict[str, Nodo]
    base: str
    clientes: list[str]
    tipos: list[DatosTipo]
    red: Red

    @property
    def ini(self) -> str:
        return self.base

    @property
    def fin(self) -> str:
        return self.base + FIN_SUFIJO

    def real(self, k: str) -> str:
        """Id del CSV para un nodo clave (la llegada a la base es la base)."""
        return self.base if k == self.fin else k


def k_vecinos_efectivo(esc: dict, n_clientes: int) -> int:
    """"auto": exacto (0) hasta `umbral_exacto` clientes; sobre eso, `k_auto` (heurístico)."""
    k = (esc or {}).get("k_vecinos", 0)
    if k == "auto":
        return 0 if n_clientes <= int(esc.get("umbral_exacto", 25)) else int(esc.get("k_auto", 10))
    return int(k or 0)


def tipos_desde_config(cfg: dict) -> list[TipoVehiculo]:
    pendiente = cfg["pipeline"]["energia"] == "pendiente"
    tipos = []
    for g in cfg["flota"]:
        t = cfg["tipos_vehiculo"][g["tipo"]]
        B = float(t["bateria_kwh"])
        tipos.append(TipoVehiculo(
            nombre=g["tipo"], cantidad=int(g.get("cantidad", 1)), B=B,
            b_ini=float(t["soc_inicial"]) * B, b_min=reserva_kwh(t),
            conectores={str(c) for c in t["conectores"]},
            energia=ModeloEnergia(float(t["consumo_kwh_km"]), float(t.get("masa_kg", 1590)),
                                  float(t.get("eta_traccion", 0.9)), float(t.get("eta_regeneracion", 0.6)),
                                  pendiente),
        ))
    # Grupos con el mismo tipo se suman (vehículos idénticos).
    unidos: dict[str, TipoVehiculo] = {}
    for t in tipos:
        if t.nombre in unidos:
            unidos[t.nombre].cantidad += t.cantidad
        else:
            unidos[t.nombre] = t
    return list(unidos.values())


def _estad_par(red: Red, energia: ModeloEnergia, i: str, j: str) -> Estad:
    return estadisticos([energia.tramo(km, dh) for km, dh in red.tramos(i, j)])


def _dominado(f: str, g: str, est, otros_in: list[str], otros_out: list[str]) -> bool:
    """g domina a f: entrar/salir por g nunca es peor que por f en ningún estadístico."""
    for i in otros_in:
        a, b = est[(i, f)], est[(i, g)]
        if b.e > a.e + EPS or b.pi > a.pi + EPS or b.lam > a.lam + EPS:
            return False
    for j in otros_out:
        a, b = est[(f, j)], est[(g, j)]
        if b.e > a.e + EPS or b.sig > a.sig + EPS or b.pi > a.pi + EPS or b.lam > a.lam + EPS:
            return False
    return True


def construir(nodos: list[Nodo], red: Red, cfg: dict) -> Instancia:
    por_id = {n.id: n for n in nodos}
    base = next(n.id for n in nodos if n.tipo == "base")
    clientes = [n.id for n in nodos if n.tipo == "cliente"]
    tipos = tipos_desde_config(cfg)
    inst = Instancia(por_id, base, clientes, [], red)
    ini, fin = inst.ini, inst.fin
    modo = cfg["pipeline"]["cargadores"]

    for t in tipos:
        todos_carg = [n for n in nodos if n.tipo == "cargador"]
        F = [n.id for n in todos_carg if compatible(n, t.conectores)]
        incompatibles = [n.id for n in todos_carg if n.id not in F]
        claves = [base, *clientes, *F]
        est: dict[tuple[str, str], Estad] = {}
        for i in claves:
            for j in claves:
                if i != j:
                    est[(i, j)] = _estad_par(red, t.energia, i, j)
        for i in claves:
            if i != base:
                est[(i, fin)] = est[(i, base)]
        est[(ini, fin)] = Estad(0.0, 0.0, 0.0, 0.0)

        podados: list[str] = []
        if modo == "dominancia":
            vivos = list(F)
            for f in list(F):
                otros = [x for x in vivos if x != f]
                ent = [ini, *clientes, *otros]
                sal = [*clientes, *otros, fin]
                for g in otros:
                    if _dominado(f, g, est, [x for x in ent if x != g], [x for x in sal if x != g]):
                        vivos.remove(f)
                        podados.append(f)
                        break
            F = vivos
        elif modo == "top_r":
            r = int(cfg["cargadores"]["top_r"])
            keep: set[str] = set()
            for v in [ini, *clientes]:
                keep.update(sorted(F, key=lambda f: est[(v, f)].e)[:r])
                if v != ini:
                    keep.update(sorted(F, key=lambda f: est[(f, v)].e)[:r])
            keep.update(sorted(F, key=lambda f: est[(f, fin)].e)[:r])
            podados = [f for f in F if f not in keep]
            F = [f for f in F if f in keep]

        Fs = set(F)
        arcos: dict[tuple[str, str], Estad] = {}
        margen = t.B - t.b_min
        for i in [ini, *clientes, *F]:
            for j in [*clientes, *F, fin]:
                if i == j or (i in Fs and j in Fs and i == j):
                    continue
                s = est[(i, j)]
                if s.lam > margen + EPS:                                   # filtro (a)
                    continue
                if i == ini or i in Fs:
                    beta = t.b_ini if i == ini else t.B
                    if beta + EPS < t.b_min + s.pi:                         # filtro (b)
                        continue
                elif t.b_min + s.pi > t.B + EPS:                           # filtro (c)
                    continue
                arcos[(i, j)] = s
        arcos[(ini, fin)] = est[(ini, fin)]
        # Poda heurística k-vecinos: por cada cliente conserva solo sus k arcos
        # cliente->cliente de menor energía (entrantes y salientes). Reduce el modelo
        # para escalar; PUEDE perder el óptimo exacto, por eso es opcional (k>0).
        # Se preserva simetría (si i->j sobrevive, se intenta mantener j->i) y los
        # arcos usados por la solución inicial, cuando se proporciona.
        k_vec = k_vecinos_efectivo(cfg.get("escala", {}), len(clientes))
        if k_vec > 0 and len(clientes) > k_vec:
            arcos = _podar_k_vecinos(arcos, clientes, k_vec)
        inst.tipos.append(DatosTipo(t, F, arcos, incompatibles, podados))
    return inst


def _podar_k_vecinos(arcos: dict[tuple[str, str], Estad], clientes: list[str], k: int,
                     obligatorios: set[tuple[str, str]] | None = None) -> dict[tuple[str, str], Estad]:
    """Conserva, por cliente, los k arcos cliente->cliente de menor ê (entrada y salida).

    Reducción HEURÍSTICA (puede perder el óptimo). Los arcos con base/cargadores/fin
    y los `obligatorios` (p.ej. de la solución inicial) se conservan siempre.
    """
    Cs = set(clientes)
    oblig = obligatorios or set()
    cc = [(i, j) for (i, j) in arcos if i in Cs and j in Cs]
    salida: dict[str, list[tuple[float, str, str]]] = {c: [] for c in clientes}
    entrada: dict[str, list[tuple[float, str, str]]] = {c: [] for c in clientes}
    for (i, j) in cc:
        e = arcos[(i, j)].e
        salida[i].append((e, i, j))
        entrada[j].append((e, i, j))
    mantener: set[tuple[str, str]] = set()
    for c in clientes:
        for _, i, j in sorted(salida[c])[:k]:
            mantener.add((i, j))
        for _, i, j in sorted(entrada[c])[:k]:
            mantener.add((i, j))
    out = {}
    for (i, j), s in arcos.items():
        if i in Cs and j in Cs:
            if (i, j) in mantener or (j, i) in mantener or (i, j) in oblig:
                out[(i, j)] = s
        else:
            out[(i, j)] = s
    return out
