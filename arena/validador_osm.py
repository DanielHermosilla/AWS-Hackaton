"""Validador neutral INDEPENDIENTE de evrp y de ev_routing.

Lee el MISMO GraphML (OSM, EPSG:4326, MultiDiGraph con 'length' en metros y 'x','y'
en nodos) con networkx y reimplementa la fisica de bateria/energia en arena/, sin
importar ningun motor. Sirve de piso comun para comparar rutas de cualquier motor.

Semantica (identica a los supuestos del PDF del companero y del perfil ev_routing):
  - energia de un tramo vial = distancia_km * consumo_kwh_km (modelo distancia-only).
  - cada servicio (base/cliente/cargador) se conecta a su interseccion vial mas
    cercana por un acceso recto bidireccional (haversine), limitado por
    max_snap_distance_m; si lo supera, el nodo es inaccesible (se reporta).
  - la energia entre dos nodos de servicio es la del CAMINO VIAL MAS CORTO (en metros)
    sobre el grafo dirigido, sumando accesos. Esto reproduce "sin rutas rectas
    entre clientes: se preservan los arcos dirigidos de la red".
  - bateria: arranca en soc_inicial*B; en cada tramo b <- min(B, b - e); nunca puede
    caer por debajo de la reserva; la regeneracion que excede B se pierde.
  - recarga: al llegar a un cargador compatible (no terminal) la bateria sube a B.

Entrada por ruta: lista de node_id de servicio del CSV, empezando y terminando en BASE.
Validar devuelve un informe con entregas, energia, km, bateria minima y violaciones.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt

import networkx as nx

TOL = 1e-6


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia en metros entre (lat, lon)."""
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    v = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_009 * asin(min(1.0, sqrt(v)))


@dataclass
class NodoServicio:
    node_id: str
    tipo: str  # base | visit | charger
    lat: float
    lon: float
    conectores: frozenset[str]


def _norm_con(texto: str) -> frozenset[str]:
    partes = []
    for sep in (";", ","):
        texto = texto.replace(sep, "|")
    for p in texto.split("|"):
        p = p.strip().upper()
        if p:
            partes.append(p)
    return frozenset(partes)


_TIPO = {"base": "base", "depot": "base", "deposito": "base",
         "visit": "visit", "client": "visit", "cliente": "visit", "customer": "visit",
         "charger": "charger", "cargador": "charger", "station": "charger"}


def leer_servicios(csv_nodos: str) -> list[NodoServicio]:
    out: list[NodoServicio] = []
    with open(csv_nodos, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            tipo = _TIPO.get((r.get("node_type") or "").strip().lower())
            if tipo is None:
                continue
            out.append(NodoServicio(
                node_id=r["node_id"].strip(),
                tipo=tipo,
                lat=float(r["latitude"]),
                lon=float(r["longitude"]),
                conectores=_norm_con(r.get("connector_types") or "")))
    return out


@dataclass
class ReporteVeh:
    vehiculo: str
    nodos: list[str]
    energia_kwh: float = 0.0
    km: float = 0.0
    bateria_min_kwh: float = 0.0
    bateria_final_kwh: float = 0.0
    recargas: int = 0
    errores: list[str] = field(default_factory=list)


@dataclass
class ResultadoNeutral:
    factible: bool
    entregas: int
    clientes: int
    no_atendidos: list[str]
    energia_total_kwh: float
    km_total: float
    errores: list[str]
    por_vehiculo: dict[str, dict]


class ValidadorOSM:
    """Carga el GraphML y el CSV una vez; valida multiples conjuntos de rutas en clave.

    Independiente de evrp y de ev_routing: usa solo networkx + CSV.
    """

    def __init__(self, csv_nodos: str, graphml: str, *, bateria_kwh: float,
                 reserva_kwh: float, soc_inicial: float, consumo_kwh_km: float,
                 conectores_vehiculo: set[str], max_snap_distance_m: float = 100.0):
        self.B = float(bateria_kwh)
        self.reserva = float(reserva_kwh)
        self.b_ini = float(soc_inicial) * float(bateria_kwh)
        self.rate = float(consumo_kwh_km)
        self.conectores_veh = {c.strip().upper() for c in conectores_vehiculo}
        self.max_snap = float(max_snap_distance_m)

        self.servicios = leer_servicios(csv_nodos)
        self.por_id = {s.node_id: s for s in self.servicios}
        self.base = next(s.node_id for s in self.servicios if s.tipo == "base")
        self.clientes = [s.node_id for s in self.servicios if s.tipo == "visit"]

        self._g = self._cargar_grafo(graphml)
        self._snap, self._snap_dist = self._snapear()
        # Cache de distancias de camino mas corto (metros) entre junctions.
        self._dist_cache: dict[tuple[str, str], float | None] = {}

    # ------------------------------------------------------------- grafo
    @staticmethod
    def _cargar_grafo(graphml: str) -> nx.MultiDiGraph:
        g = nx.read_graphml(graphml)
        if not g.is_directed():
            raise ValueError("el GraphML debe ser dirigido")
        # Normaliza length a float; descarta aristas sin longitud finita.
        for _u, _v, data in g.edges(data=True):
            try:
                data["length"] = float(data.get("length"))
            except (TypeError, ValueError):
                data["length"] = float("inf")
        for _n, data in g.nodes(data=True):
            data["y"] = float(data["y"])
            data["x"] = float(data["x"])
        return g

    def _snapear(self) -> tuple[dict[str, str], dict[str, float]]:
        """Cada servicio -> interseccion vial mas cercana (haversine). Guarda distancia."""
        coords = [(n, (d["y"], d["x"])) for n, d in self._g.nodes(data=True)]
        snap: dict[str, str] = {}
        dist: dict[str, float] = {}
        for s in self.servicios:
            pos = (s.lat, s.lon)
            mejor, mejor_d = None, float("inf")
            for nid, c in coords:
                d = haversine_m(pos, c)
                if d < mejor_d:
                    mejor, mejor_d = nid, d
            snap[s.node_id] = mejor
            dist[s.node_id] = mejor_d
        return snap, dist

    def _dist_vial_m(self, a_srv: str, b_srv: str) -> float | None:
        """Distancia minima (m) entre dos servicios: acceso + camino vial + acceso."""
        ja, jb = self._snap[a_srv], self._snap[b_srv]
        clave = (ja, jb)
        if clave not in self._dist_cache:
            try:
                self._dist_cache[clave] = nx.shortest_path_length(
                    self._g, ja, jb, weight="length")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self._dist_cache[clave] = None
        d = self._dist_cache[clave]
        if d is None:
            return None
        return self._snap_dist[a_srv] + d + self._snap_dist[b_srv]

    def snap_max_m(self) -> float:
        """Mayor distancia de acceso entre los servicios del CSV (clientes/base/cargadores)."""
        return max(self._snap_dist.values())

    def snap_max_cliente_base_m(self) -> float:
        """Mayor acceso considerando solo base y clientes (los que fuerza entregar)."""
        rel = [self._snap_dist[s.node_id] for s in self.servicios
               if s.tipo in ("base", "visit")]
        return max(rel) if rel else 0.0

    # ------------------------------------------------------------- validacion
    def validar_clave(self, rutas: dict[str, list[str]]) -> ResultadoNeutral:
        reportes: list[ReporteVeh] = []
        vistos: dict[str, str] = {}
        errores: list[str] = []
        for veh, nodos in rutas.items():
            rep = ReporteVeh(veh, list(nodos))
            self._estructura(nodos, veh, rep, vistos)
            if not rep.errores:
                self._simular(nodos, rep)
            errores += [f"{veh}: {e}" for e in rep.errores]
            reportes.append(rep)
        return self._agregar(reportes, vistos, errores)

    def _estructura(self, nodos, veh, rep, vistos):
        if not nodos or nodos[0] != self.base or nodos[-1] != self.base:
            rep.errores.append("la ruta no empieza y termina en la BASE")
            return
        for v in nodos:
            s = self.por_id.get(v)
            if s is None:
                rep.errores.append(f"nodo inexistente: {v}")
            elif self._snap_dist.get(v, float("inf")) > self.max_snap + TOL:
                rep.errores.append(
                    f"nodo {v} inaccesible: acceso {self._snap_dist[v]:.1f} m > "
                    f"max_snap {self.max_snap:.0f} m")
            elif s.tipo == "visit":
                if v in vistos:
                    rep.errores.append(f"cliente {v} repetido (tambien en {vistos[v]})")
                vistos[v] = veh
            elif s.tipo == "charger" and not (self.conectores_veh & s.conectores):
                rep.errores.append(f"cargador {v} incompatible con el vehiculo")

    def _simular(self, nodos, rep):
        b = self.b_ini
        bmin = b
        for i, (u, v) in enumerate(zip(nodos, nodos[1:])):
            d_m = self._dist_vial_m(u, v)
            if d_m is None:
                rep.errores.append(f"sin camino vial {u}->{v}")
                rep.bateria_min_kwh = bmin
                rep.bateria_final_kwh = b
                return
            km = d_m / 1000.0
            e = km * self.rate
            b = min(self.B, b - e)
            rep.energia_kwh += e
            rep.km += km
            bmin = min(bmin, b)
            if b < self.reserva - TOL:
                rep.errores.append(
                    f"bateria {b:.3f} < reserva {self.reserva:.3f} en tramo {u}->{v}")
                rep.bateria_min_kwh = bmin
                rep.bateria_final_kwh = b
                return
            s = self.por_id[v]
            if s.tipo == "charger" and v != nodos[-1]:
                b = self.B
                rep.recargas += 1
        rep.bateria_min_kwh = bmin
        rep.bateria_final_kwh = b

    def _agregar(self, reportes, vistos, errores) -> ResultadoNeutral:
        no_atendidos = [c for c in self.clientes if c not in vistos]
        return ResultadoNeutral(
            factible=not errores,
            entregas=len(vistos),
            clientes=len(self.clientes),
            no_atendidos=no_atendidos,
            energia_total_kwh=round(sum(r.energia_kwh for r in reportes), 4),
            km_total=round(sum(r.km for r in reportes), 3),
            errores=errores,
            por_vehiculo={r.vehiculo: {
                "energia_kwh": round(r.energia_kwh, 4),
                "km": round(r.km, 3),
                "bateria_min_kwh": round(r.bateria_min_kwh, 4),
                "bateria_final_kwh": round(r.bateria_final_kwh, 4),
                "recargas": r.recargas,
                "errores": r.errores} for r in reportes})
