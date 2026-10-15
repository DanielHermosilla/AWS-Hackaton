"""Validador independiente del solver.

Recibe las rutas en ids del CSV y vuelve a simular la batería tramo a tramo con la
red y el modelo de energía, sin usar los estadísticos ni las variables del MILP.
Política de carga: completa (hasta B) en cada cargador listado. Además calcula la
carga mínima necesaria para reportar la energía efectiva (definición del PDF).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .datos import compatible
from .instancia import Instancia, TipoVehiculo

TOL = 1e-6


@dataclass
class ReporteRuta:
    vehiculo: str
    tipo: str
    nodos: list[str]
    energia_kwh: float = 0.0
    km: float = 0.0
    bateria_min_kwh: float = 0.0
    bateria_final_kwh: float = 0.0
    paradas: list[dict] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


def _simular(inst: Instancia, t: TipoVehiculo, nodos: list[str], rep: ReporteRuta) -> None:
    b = t.b_ini
    bmin_vista = b
    for u, v in zip(nodos, nodos[1:]):
        tramos = inst.red.tramos(u, v)
        e_par = 0.0
        for km, dh in tramos:
            e = t.energia.tramo(km, dh)
            b = min(t.B, b - e)
            e_par += e
            rep.km += km
            bmin_vista = min(bmin_vista, b)
            if b < t.b_min - TOL:
                rep.errores.append(f"Batería {b:.3f} < reserva {t.b_min:.3f} en el tramo {u}→{v}")
                break
        rep.energia_kwh += e_par
        llegada = b
        nodo = inst.nodos[v]
        carga = 0.0
        if nodo.tipo == "cargador" and v != nodos[-1]:
            carga = t.B - b
            b = t.B
        rep.paradas.append({"nodo": v, "tipo": nodo.tipo, "energia_tramo_kwh": round(e_par, 4),
                            "bateria_llegada_kwh": round(llegada, 4), "carga_kwh": round(carga, 4),
                            "bateria_salida_kwh": round(b, 4)})
    rep.bateria_min_kwh = bmin_vista
    rep.bateria_final_kwh = b


def validar(inst: Instancia, rutas: dict[str, list[str]], tipo_de: dict[str, str]) -> dict:
    """rutas: {vehículo: [ids]}; tipo_de: {vehículo: nombre de tipo}."""
    tipos = {dt.tipo.nombre: dt.tipo for dt in inst.tipos}
    vistos: dict[str, str] = {}
    reportes, errores = [], []
    for veh, nodos in rutas.items():
        t = tipos[tipo_de[veh]]
        rep = ReporteRuta(veh, t.nombre, nodos)
        if not nodos or nodos[0] != inst.base or nodos[-1] != inst.base:
            rep.errores.append("La ruta no empieza y termina en la base")
        for v in nodos:
            n = inst.nodos.get(v)
            if n is None:
                rep.errores.append(f"Nodo inexistente: {v}")
            elif n.tipo == "cliente":
                if v in vistos:
                    rep.errores.append(f"Cliente {v} repetido (también en {vistos[v]})")
                vistos[v] = veh
            elif n.tipo == "cargador" and not compatible(n, t.conectores):
                rep.errores.append(f"Cargador {v} incompatible con {t.nombre}")
        if not rep.errores:
            _simular(inst, t, nodos, rep)
        errores += [f"{veh}: {e}" for e in rep.errores]
        reportes.append(rep)
    no_atendidos = [c for c in inst.clientes if c not in vistos]
    return {
        "factible": not errores,
        "errores": errores,
        "entregas": len(vistos),
        "clientes": len(inst.clientes),
        "no_atendidos": no_atendidos,
        "energia_total_kwh": sum(r.energia_kwh for r in reportes),
        "energia_efectiva_kwh": sum(_energia_efectiva(inst, tipos[r.tipo], r.nodos) for r in reportes
                                    if not r.errores),
        "reportes": reportes,
    }


def _energia_efectiva(inst: Instancia, t: TipoVehiculo, nodos: list[str]) -> float:
    """b_ini + Σq − b_final con carga mínima en cada cargador (inducción hacia atrás).

    Se simula tramo a tramo: con regeneración, cargar de más puede desperdiciar energía.
    """
    def requerido(segmento):  # batería mínima al salir para recorrer el segmento con reserva
        req = t.b_min
        for u, v in reversed(list(zip(segmento, segmento[1:]))):
            for km, dh in reversed(inst.red.tramos(u, v)):
                req = max(t.b_min, req + t.energia.tramo(km, dh))
        return min(req, t.B)

    paradas = [k for k, v in enumerate(nodos) if inst.nodos[v].tipo == "cargador" and 0 < k < len(nodos) - 1]
    b, total_q = t.b_ini, 0.0
    cortes = [0, *paradas, len(nodos) - 1]
    for a, z in zip(cortes, cortes[1:]):
        if a in paradas:
            q = max(0.0, requerido(nodos[a:z + 1]) - b)
            b += q
            total_q += q
        for u, v in zip(nodos[a:z + 1], nodos[a + 1:z + 1]):
            for km, dh in inst.red.tramos(u, v):
                b = min(t.B, b - t.energia.tramo(km, dh))
    return t.b_ini + total_q - b
