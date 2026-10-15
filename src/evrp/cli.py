"""Interfaz de línea de comandos: python -m evrp {solve, calibrar}."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config as cfgmod


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m evrp", description="Motor de ruteo para flota eléctrica")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("solve", help="Genera rutas para un archivo de nodos")
    s.add_argument("--nodes", required=True, help="CSV de nodos (formato del desafío)")
    s.add_argument("--config", default=None, help="YAML de configuración (opcional)")
    s.add_argument("--out", default="results", help="Directorio de salida")
    s.add_argument("--vehiculos", type=int, default=None, help="Atajo: cantidad de vehículos del primer grupo")
    s.add_argument("--tiempo", type=float, default=None, help="Atajo: límite de tiempo del solver (s)")
    s.add_argument("--red", choices=["haversine", "osm"], default=None, help="Atajo: pipeline.red")
    s.add_argument("--perfil", action="append", default=None,
                   help="Perfil de supuestos (repetible): " + ", ".join(cfgmod.perfiles_disponibles()))
    s.add_argument("-v", "--verbose", action="store_true")

    c = sub.add_parser("calibrar", help="Calibra consumo y batería con eVED_EV.csv")
    c.add_argument("--ev", default="DATA/eVED_EV.csv")
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

    from .pipeline import ejecutar

    extra: dict = {}
    cfg = cfgmod.cargar(a.config, None, a.perfil)
    if a.vehiculos is not None:
        flota = [dict(g) for g in cfg["flota"]]
        flota[0]["cantidad"] = a.vehiculos
        extra["flota"] = flota
    if a.tiempo is not None:
        extra["solver"] = {"tiempo_limite_s": a.tiempo}
    if a.red is not None:
        extra["pipeline"] = {"red": a.red}
    if extra:
        cfg = cfgmod.validar(cfgmod.fusionar(cfg, extra))
    res = ejecutar(a.nodes, cfg, a.out)
    print(json.dumps({"rutas": res["rutas"], **{k: res["kpis"][k] for k in
                      ("factible", "entregas", "clientes", "energia_total_kwh", "tiempo_computo_s")}},
                     indent=2, ensure_ascii=False))
    return 0 if res["kpis"]["factible"] else 2


if __name__ == "__main__":
    sys.exit(main())
