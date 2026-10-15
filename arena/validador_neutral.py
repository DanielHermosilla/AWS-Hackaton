"""Validador neutral: comprueba rutas de CUALQUIER motor sobre el MISMO grafo OSM.

No depende de las variables ni los estadisticos de ningun solver. Reconstruye la
fisica a partir de las primitivas publicas de evrp (datos, red, energia):

  - inicio y fin en la BASE,
  - cada cliente a lo sumo una vez,
  - cargadores compatibles con el vehiculo,
  - bateria >= reserva tramo a tramo, con saturacion min{B, .} (regeneracion no
    almacenable se pierde),
  - energia recalculada con el mismo consumo kwh/km.

Entradas admitidas por ruta:
  - "clave": lista de node_id del CSV (base, clientes, cargadores). Se EXPANDE con
    el camino de minima energia entre nodos clave (RedOSM/RedHaversine de evrp).
  - "calle": lista de tramos (km, desnivel_m) ya resueltos por el motor (p.ej. los
    arcos de ev_routing). En este modo cada "parada" trae sus tramos de llegada.

El validador recalcula energia y bateria; no confia en los numeros del motor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from evrp.datos import Nodo, cargar_nodos, compatible
from evrp.energia import ModeloEnergia

TOL = 1e-6


@dataclass
class Supuestos:
    bateria_kwh: float
    reserva_kwh: float
    soc_inicial: float
    consumo_kwh_km: float
    conectores: set[str]
    pendiente: bool = False
    masa_kg: float = 1590.0
    eta_traccion: float = 0.90
    eta_regeneracion: float = 0.60

    @property
    def b_ini(self) -> float:
        return self.soc_inicial * self.bateria_kwh

    def energia(self) -> ModeloEnergia:
        return ModeloEnergia(self.consumo_kwh_km, self.masa_kg, self.eta_traccion,
                             self.eta_regeneracion, self.pendiente)


@dataclass
class ReporteVehiculo:
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


class ValidadorNeutral:
    """Carga el CSV y prepara la red UNA vez; valida multiples conjuntos de rutas."""

    def __init__(self, csv_nodos: str, sup: Supuestos, red: str = "osm",
                 grafo: str | None = None, osm_cache: str = "results/arena/.cache/osm"):
        self.nodos = cargar_nodos(csv_nodos)
        self.por_id = {n.id: n for n in self.nodos}
        self.base = next(n.id for n in self.nodos if n.tipo == "base")
        self.clientes = [n.id for n in self.nodos if n.tipo == "cliente"]
        self.sup = sup
        self.energia_mod = sup.energia()
        self.red = self._crear_red(red, grafo, osm_cache)
        self.red.preparar(self.nodos, self.energia_mod)

    def _crear_red(self, red, grafo, osm_cache):
        from evrp.red import RedHaversine, RedOSM
        if red == "haversine":
            return RedHaversine(1.30)
        return RedOSM(margen_km=2.0, cache=osm_cache, grafo=grafo,
                      max_acceso_m=None, permitir_descarga=False)

    # ------------------------------------------------------------------ clave
    def validar_clave(self, rutas: dict[str, list[str]]) -> ResultadoNeutral:
        """rutas: {vehiculo: [node_id, ...]} en nodos clave del CSV."""
        reportes: list[ReporteVehiculo] = []
        vistos: dict[str, str] = {}
        errores: list[str] = []
        for veh, nodos in rutas.items():
            rep = ReporteVehiculo(veh, list(nodos))
            self._chequeos_estructura(nodos, veh, rep, vistos)
            if not rep.errores:
                self._simular_clave(nodos, rep)
            errores += [f"{veh}: {e}" for e in rep.errores]
            reportes.append(rep)
        return self._agregar(reportes, vistos, errores)

    def _chequeos_estructura(self, nodos, veh, rep, vistos):
        if not nodos or nodos[0] != self.base or nodos[-1] != self.base:
            rep.errores.append("la ruta no empieza y termina en la BASE")
        for v in nodos:
            n = self.por_id.get(v)
            if n is None:
                rep.errores.append(f"nodo inexistente: {v}")
            elif n.tipo == "cliente":
                if v in vistos:
                    rep.errores.append(f"cliente {v} repetido (tambien en {vistos[v]})")
                vistos[v] = veh
            elif n.tipo == "cargador" and not compatible(n, self.sup.conectores):
                rep.errores.append(f"cargador {v} incompatible con el vehiculo")

    def _simular_clave(self, nodos, rep):
        b = self.sup.b_ini
        bmin = b
        B = self.sup.bateria_kwh
        reserva = self.sup.reserva_kwh
        for u, v in zip(nodos, nodos[1:]):
            for km, dh in self.red.tramos(u, v):
                e = self.energia_mod.tramo(km, dh)
                b = min(B, b - e)
                rep.energia_kwh += e
                rep.km += km
                bmin = min(bmin, b)
                if b < reserva - TOL:
                    rep.errores.append(
                        f"bateria {b:.3f} < reserva {reserva:.3f} en tramo {u}->{v}")
                    rep.bateria_min_kwh = bmin
                    rep.bateria_final_kwh = b
                    return
            nodo = self.por_id[v]
            if nodo.tipo == "cargador" and v != nodos[-1]:
                b = B
                rep.recargas += 1
        rep.bateria_min_kwh = bmin
        rep.bateria_final_kwh = b

    # ------------------------------------------------------------------ calle
    def validar_calle(self, rutas: dict[str, dict]) -> ResultadoNeutral:
        """rutas: {vehiculo: {"nodos": [...], "tramos_por_paso": [[(km,dh),...], ...]}}.

        tramos_por_paso[i] son los tramos elementales para ir de nodos[i] a nodos[i+1].
        Util para motores calle a calle (ev_routing) que ya resolvieron sus arcos.
        """
        reportes: list[ReporteVehiculo] = []
        vistos: dict[str, str] = {}
        errores: list[str] = []
        for veh, datos in rutas.items():
            nodos = datos["nodos"]
            tramos = datos.get("tramos_por_paso", [])
            rep = ReporteVehiculo(veh, list(nodos))
            self._chequeos_estructura(nodos, veh, rep, vistos)
            if not rep.errores:
                self._simular_calle(nodos, tramos, rep)
            errores += [f"{veh}: {e}" for e in rep.errores]
            reportes.append(rep)
        return self._agregar(reportes, vistos, errores)

    def _simular_calle(self, nodos, tramos_por_paso, rep):
        b = self.sup.b_ini
        bmin = b
        B = self.sup.bateria_kwh
        reserva = self.sup.reserva_kwh
        for i, (u, v) in enumerate(zip(nodos, nodos[1:])):
            tramos = tramos_por_paso[i] if i < len(tramos_por_paso) else self.red.tramos(u, v)
            for km, dh in tramos:
                e = self.energia_mod.tramo(km, dh)
                b = min(B, b - e)
                rep.energia_kwh += e
                rep.km += km
                bmin = min(bmin, b)
                if b < reserva - TOL:
                    rep.errores.append(
                        f"bateria {b:.3f} < reserva {reserva:.3f} en tramo {u}->{v}")
                    rep.bateria_min_kwh = bmin
                    rep.bateria_final_kwh = b
                    return
            nodo = self.por_id[v]
            if nodo.tipo == "cargador" and v != nodos[-1]:
                b = B
                rep.recargas += 1
        rep.bateria_min_kwh = bmin
        rep.bateria_final_kwh = b

    # ------------------------------------------------------------------ comun
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
            por_vehiculo={r.vehiculo: {"energia_kwh": round(r.energia_kwh, 4),
                                       "km": round(r.km, 3),
                                       "bateria_min_kwh": round(r.bateria_min_kwh, 4),
                                       "bateria_final_kwh": round(r.bateria_final_kwh, 4),
                                       "recargas": r.recargas,
                                       "errores": r.errores} for r in reportes},
        )
