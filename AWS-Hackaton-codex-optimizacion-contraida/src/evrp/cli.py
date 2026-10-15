"""Interfaz de línea de comandos.

    evrp preparar  --nodes X.csv [--perfil P] [--red osm|haversine] [--pendiente] [--geometria] --out inst.json.gz
    evrp resolver  --instancia inst.json.gz [--perfil P] [--vehiculos N] [--tiempo S] [--excluir ID ...] --out results/
    evrp solve     --nodes X.csv [mismas opciones de resolver] --out results/     (atajo: preparar + resolver)
    evrp calibrar  [--ev data/eVED_EV.csv] [--out results/calibracion.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config as cfgmod


def _opciones_comunes(s):
    s.add_argument("--config", default=None, help="YAML de configuración (opcional)")
    s.add_argument("--perfil", action="append", default=None,
                   help="Perfil de supuestos (repetible): " + ", ".join(cfgmod.perfiles_disponibles()))
    s.add_argument("-v", "--verbose", action="store_true")


def _opciones_red(s):
    s.add_argument("--red", choices=["haversine", "osm"], default=None, help="pipeline.red")
    s.add_argument("--pendiente", action="store_true", help="pipeline.energia=pendiente")
    s.add_argument("--elevacion", choices=["eved", "usgs", "copernicus"], default=None,
                   help="red.elevacion (implica --pendiente)")


def _opciones_solver(s):
    s.add_argument("--vehiculos", type=int, default=None, help="Cantidad de vehículos del primer grupo")
    s.add_argument("--tiempo", type=float, default=None, help="Presupuesto total y del MILP (s)")
    s.add_argument("--out", default="results", help="Directorio de salida")


def _cfg(a) -> dict:
    cfg = cfgmod.cargar(a.config, None, a.perfil)
    extra: dict = {}
    if getattr(a, "vehiculos", None) is not None:
        flota = [dict(g) for g in cfg["flota"]]
        flota[0]["cantidad"] = a.vehiculos
        extra["flota"] = flota
    if getattr(a, "tiempo", None) is not None:
        extra["solver"] = {"tiempo_limite_s": a.tiempo, "presupuesto_total_s": a.tiempo}
    if getattr(a, "red", None) is not None:
        extra.setdefault("pipeline", {})["red"] = a.red
    if getattr(a, "pendiente", False) or getattr(a, "elevacion", None):
        extra.setdefault("pipeline", {})["energia"] = "pendiente"
    if getattr(a, "elevacion", None):
        extra.setdefault("red", {})["elevacion"] = a.elevacion
    return cfgmod.validar(cfgmod.fusionar(cfg, extra)) if extra else cfg


def _imprimir(res) -> int:
    k = res["kpis"] if isinstance(res, dict) else res.kpis
    rutas = res["rutas"] if isinstance(res, dict) else res.rutas
    print(json.dumps({"rutas": rutas, **{c: k[c] for c in
                      ("factible", "entregas", "clientes", "energia_total_kwh", "tiempo_computo_s")}},
                     indent=2, ensure_ascii=False))
    return 0 if k["factible"] else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="evrp", description="Motor de ruteo para flota eléctrica")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("preparar", help="ETAPA 1: red vial → instancia preparada (.json/.json.gz)")
    pr.add_argument("--nodes", required=True, help="CSV de nodos (formato del desafío)")
    pr.add_argument("--out", required=True, help="Archivo de salida, p.ej. results/inst.json.gz")
    pr.add_argument("--geometria", action="store_true", help="Incluir puntos (lat, lon) de cada camino")
    _opciones_comunes(pr)
    _opciones_red(pr)

    rs = sub.add_parser("resolver", help="ETAPA 2: resolver una instancia preparada")
    rs.add_argument("--instancia", required=True, help="Archivo de `evrp preparar`")
    rs.add_argument("--excluir", nargs="*", default=None, help="Ids de nodos a ignorar")
    _opciones_comunes(rs)
    _opciones_solver(rs)
    rs.add_argument("--pendiente", action="store_true", help="Debe coincidir con la preparación")

    s = sub.add_parser("solve", help="Atajo: ETAPA 1 + ETAPA 2 desde el CSV")
    s.add_argument("--nodes", required=True, help="CSV de nodos (formato del desafío)")
    _opciones_comunes(s)
    _opciones_red(s)
    _opciones_solver(s)

    c = sub.add_parser("calibrar", help="Calibra consumo y batería con eVED_EV.csv")
    c.add_argument("--ev", default="data/eVED_EV.csv")
    c.add_argument("--out", default="results/calibracion.json")

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(a, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    if a.cmd == "calibrar":
        from .energia import calibrar_eved, guardar_calibracion

        res = calibrar_eved(a.ev)
        guardar_calibracion(res, a.out)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if a.cmd == "preparar":
        from .preparacion import preparar_con_cfg

        prep = preparar_con_cfg(a.nodes, _cfg(a), a.geometria)
        ruta = prep.guardar(a.out)
        print(json.dumps({"archivo": str(ruta), **prep.resumen()}, indent=2, ensure_ascii=False, default=str))
        return 0

    from .pipeline import ejecutar

    if a.cmd == "resolver":
        from .preparacion import InstanciaPreparada

        prep = InstanciaPreparada.cargar(a.instancia)
        return _imprimir(ejecutar(None, _cfg(a), a.out, preparada=prep, excluir=a.excluir))

    return _imprimir(ejecutar(a.nodes, _cfg(a), a.out))


if __name__ == "__main__":
    sys.exit(main())
