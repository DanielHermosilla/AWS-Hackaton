"""Utilidades compartidas de las evaluaciones de energía con 20 clientes.

Trabaja en proceso (sin lanzar subprocesos) para reutilizar instancias preparadas.
Un solo núcleo por diseño: cfg solver.hilos=1 y nada de paralelismo.
"""
from __future__ import annotations

import time
from pathlib import Path

from evrp import config as cfgmod
from evrp import sintetico
from evrp.instancia import construir, tipos_desde_config
from evrp.pipeline import ejecutar
from evrp.preparacion import InstanciaPreparada, preparar_con_cfg
from evrp.validador import validar

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data"
INST = Path(__file__).resolve().parent / "inst"
RES = Path(__file__).resolve().parent / "res"
REF = str(DATA / "competition_routing_nodes.csv")

# Calibración eVED del enunciado (modelo con pendiente).
CAL_EVED = dict(consumo_kwh_km=0.110, eta_traccion=0.50, eta_regeneracion=0.94)
# Factores de temperatura (kWh/km) — modelo plano escalado.
TEMP = {"frio_<0": 0.236, "templado_20_30": 0.127}


def instancias_sinteticas(n_clientes: int = 20, semillas=range(1, 11)) -> dict:
    """Genera (si falta) los CSV sintéticos y devuelve {nombre: ruta_csv}."""
    INST.mkdir(parents=True, exist_ok=True)
    out = {}
    for s in semillas:
        csv = INST / f"syn_s{s}.csv"
        if not csv.exists():
            filas = sintetico.generar(n_clientes, s, REF)
            sintetico.escribir(filas, csv)
        out[f"syn_s{s}"] = str(csv)
    return out


def instancias_oficiales() -> dict:
    return {"competition": str(DATA / "competition_routing_nodes.csv"),
            "evaluation": str(DATA / "evaluation_routing_nodes.csv")}


def cfg_base(perfil="eved", pendiente=False, elevacion=None, vehiculos=None,
             tiempo=30.0, usar_todos=False, consumo=None):
    """Config con 1 hilo (restricción de 1 núcleo). `consumo` sobrescribe kWh/km."""
    cfg = cfgmod.cargar(None, None, [perfil])
    extra = {"solver": {"hilos": 1, "tiempo_limite_s": tiempo, "presupuesto_total_s": tiempo,
                        "usar_todos_vehiculos": usar_todos}}
    if pendiente or elevacion:
        extra.setdefault("pipeline", {})["energia"] = "pendiente"
        if elevacion:
            extra.setdefault("red", {})["elevacion"] = elevacion
            extra["red"]["elevacion_csv"] = str(DATA / "eVED_EV.csv")
    if vehiculos is not None:
        flota = [dict(g) for g in cfg["flota"]]
        flota[0]["cantidad"] = vehiculos
        extra["flota"] = flota
    if consumo is not None:
        tv = {k: dict(v) for k, v in cfg["tipos_vehiculo"].items()}
        for v in tv.values():
            v["consumo_kwh_km"] = consumo
        extra["tipos_vehiculo"] = tv
    return cfgmod.validar(cfgmod.fusionar(cfg, extra))


def preparar(csv, cfg, destino):
    """Prepara (o carga de caché en disco) una InstanciaPreparada."""
    ruta = Path(destino)
    if ruta.exists():
        return InstanciaPreparada.cargar(ruta)
    prep = preparar_con_cfg(csv, cfg)
    prep.guardar(ruta)
    return prep


def resolver(prep, cfg, salida=None):
    t0 = time.perf_counter()
    res = ejecutar(None, cfg, salida, preparada=prep)
    res["kpis"]["_wall_s"] = round(time.perf_counter() - t0, 3)
    return res


def rutas_de(res):
    """Rutas con al menos un cliente (ida+vuelta a base = len>2)."""
    return {v: r for v, r in res["rutas"].items() if len(r) > 2}


def construir_instancia(prep, cfg):
    """Instancia (nodos+red+arcos) para pasar al validador independiente."""
    red = prep.a_red()
    nodos = list(prep.nodos)
    energia = tipos_desde_config(cfg)[0].energia
    red.preparar(nodos, energia)
    return construir(nodos, red, cfg)


def energia_de_rutas(prep_eval, cfg_eval, rutas, tipo_tipo):
    """Recalcula energía/factibilidad de `rutas` con la red+modelo de `cfg_eval`."""
    inst = construir_instancia(prep_eval, cfg_eval)
    tipo_de = {v: tipo_tipo for v in rutas}
    val = validar(inst, rutas, tipo_de)
    t = {dt.tipo.nombre: dt.tipo for dt in inst.tipos}[tipo_tipo]
    margenes = [r.bateria_min_kwh - t.b_min for r in val["reportes"] if not r.errores]
    return {"factible": val["factible"], "errores": val["errores"],
            "energia_total_kwh": round(val["energia_total_kwh"], 4),
            "entregas": val["entregas"],
            "margen_min_kwh": round(min(margenes), 4) if margenes else None,
            "b_min": t.b_min, "B": t.B}


def arcos_de_rutas(rutas):
    arcos = set()
    for r in rutas.values():
        for u, v in zip(r, r[1:]):
            arcos.add((u, v))
    return arcos


def dif_arcos(a, b):
    """% de arcos distintos entre dos planes (simétrica, sobre la unión)."""
    sa, sb = arcos_de_rutas(a), arcos_de_rutas(b)
    union = sa | sb
    if not union:
        return {"pct_distintos": 0.0, "n_union": 0, "n_comunes": 0}
    comunes = sa & sb
    return {"pct_distintos": round(100 * (1 - len(comunes) / len(union)), 1),
            "n_union": len(union), "n_comunes": len(comunes),
            "solo_a": len(sa - sb), "solo_b": len(sb - sa)}
