"""Benchmark de algoritmos de caminos de mínima energía (etapa 'red').

Mide por separado: carga/descompresión del grafo, ajuste a la calle, construcción
de adyacencia y resolución de caminos; con N nodos clave variables. Verifica que
todos los algoritmos dan la misma energía por par (tol. 1e-9 relativa) y caminos
equivalentes en energía. Genera instancias sintéticas con evrp.sintetico.

Uso:
    uv run python experimentos/caminos/bench.py                 # tabla completa
    uv run python experimentos/caminos/bench.py --tamanos 21 81 # subconjunto
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data" / "competition_routing_nodes.csv"
TMP = Path(__file__).resolve().parent / "_instancias"

ALGS = ["multi_destino", "bidireccional", "a_estrella", "alt", "scipy", "networkx"]


def _instancia(n_total: int):
    """Genera (o reutiliza) una instancia con ~n_total nodos clave (1 base + clientes + cargadores).

    Reparte: 1 base, ~mitad clientes, ~mitad cargadores, para ejercitar orígenes variados.
    """
    from evrp import sintetico

    TMP.mkdir(parents=True, exist_ok=True)
    ruta = TMP / f"nodos_{n_total}.csv"
    if not ruta.exists():
        resto = n_total - 1
        clientes = resto // 2
        cargadores = resto - clientes
        filas = sintetico.generar(clientes, semilla=7, referencia=DATA, cargadores=cargadores)
        sintetico.escribir(filas, ruta)
    return ruta


def _preparar_base(nodos, energia):
    """Carga grafo + ajuste + adyacencia una sola vez; devuelve el RedOSM listo."""
    from evrp.red import RedOSM

    r = RedOSM(2.0, ".cache/osm", None, None, False, "multi_destino", True)
    t = {}
    t0 = time.perf_counter(); G = r._descargar(nodos); t["carga_grafo"] = time.perf_counter() - t0
    r.G = G
    r._pos = {n.id: (n.lat, n.lon) for n in nodos}
    elev = {v: float(d.get("elevation", 0.0) or 0.0) for v, d in G.nodes(data=True)}
    t0 = time.perf_counter(); r._ajustar_calle(nodos, G); t["ajuste_calle"] = time.perf_counter() - t0
    t0 = time.perf_counter(); pot = r._construir_adyacencia(G, elev, energia); t["adyacencia"] = time.perf_counter() - t0
    return r, pot, t


def _energia_camino(ady_km_dh, consumo, usar_pend, kappa, eta_d, eta_r, cam):
    """Energía real (sin potencial) de un camino [nodo,...] usando el arco u→v."""
    e = 0.0
    for u, v in zip(cam, cam[1:]):
        km, dh = ady_km_dh[(u, v)]
        e += consumo * km
        if usar_pend and dh:
            e += kappa * (dh / eta_d if dh > 0 else eta_r * dh)
    return e


def correr(tamanos, algoritmos, repeticiones=1):
    from evrp.caminos import GrafoCaminos, resolver_caminos
    from evrp.datos import cargar_nodos
    from evrp.instancia import tipos_desde_config
    from evrp import config

    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False}}, ["eved"])
    energia = tipos_desde_config(cfg)[0].energia

    filas_tiempo = []   # (N, etapa_base dict, {alg: segundos})
    resumen_verif = []  # (N, max_err_rel, caminos_distintos)
    for n_cli in tamanos:
        ruta = _instancia(n_cli)
        nodos = cargar_nodos(ruta)
        N = len(nodos)
        r, pot, t_base = _preparar_base(nodos, energia)
        orig = {n.id: r._snap[n.id] for n in nodos}
        lat_lon = {v: (r.G.nodes[v]["y"], r.G.nodes[v]["x"]) for v in r._ady}
        for n in nodos:
            s = r._snap[n.id]
            lat_lon.setdefault(s, (r.G.nodes[s]["y"], r.G.nodes[s]["x"]))
        g = GrafoCaminos(r._ady, pot, lat_lon, energia.consumo_kwh_km)
        pares = [(n.id, m.id) for n in nodos for m in nodos if n.id != m.id]

        tiempos = {}
        energias = {}   # alg -> {par: energia_real}
        ekm = dict(r._tramo_arco)
        for alg in algoritmos:
            mejor = float("inf")
            caminos = None
            for _ in range(repeticiones):
                g._csr = None; g._nodos = None; g._idx = None; g._rev = None  # sin reusar caché interna
                t0 = time.perf_counter()
                caminos = resolver_caminos(g, orig, pares, alg)
                dt = time.perf_counter() - t0
                mejor = min(mejor, dt)
            tiempos[alg] = mejor
            energias[alg] = {
                par: _energia_camino(ekm, energia.consumo_kwh_km, energia.usar_pendiente,
                                     energia.kappa, energia.eta_traccion, energia.eta_regeneracion,
                                     caminos[par])
                for par in pares}
        # verificación contra multi_destino (referencia)
        ref = energias[algoritmos[0]]
        max_err = 0.0
        distintos = 0
        for alg in algoritmos[1:]:
            for par in pares:
                a, b = ref[par], energias[alg][par]
                denom = max(abs(a), 1e-12)
                err = abs(a - b) / denom
                max_err = max(max_err, err)
                if err > 1e-9:
                    distintos += 1
        filas_tiempo.append((N, t_base, tiempos))
        resumen_verif.append((N, max_err, distintos))
        print(f"N={N:4d}  caminos(s): " +
              "  ".join(f"{a}={tiempos[a]:.3f}" for a in algoritmos))
        print(f"        base(s): carga={t_base['carga_grafo']:.3f} "
              f"ajuste={t_base['ajuste_calle']:.3f} adyacencia={t_base['adyacencia']:.3f}")
        print(f"        verif: max_err_rel={max_err:.2e}  pares_distintos={distintos}")
    return filas_tiempo, resumen_verif


def _tabla_md(tamanos, filas_tiempo, resumen_verif, algoritmos):
    out = ["## Tiempos de resolución de caminos (s), por N nodos clave\n"]
    out.append("| N | " + " | ".join(algoritmos) + " |")
    out.append("|---|" + "|".join("---" for _ in algoritmos) + "|")
    for (N, _, tiempos) in filas_tiempo:
        out.append(f"| {N} | " + " | ".join(f"{tiempos[a]:.3f}" for a in algoritmos) + " |")
    out.append("\n## Tiempos de las etapas base (s), por N\n")
    out.append("| N | carga_grafo | ajuste_calle | adyacencia |")
    out.append("|---|---|---|---|")
    for (N, tb, _) in filas_tiempo:
        out.append(f"| {N} | {tb['carga_grafo']:.3f} | {tb['ajuste_calle']:.3f} | {tb['adyacencia']:.3f} |")
    out.append("\n## Verificación de equivalencia (vs multi_destino)\n")
    out.append("| N | max_err_rel energía | pares con energía distinta |")
    out.append("|---|---|---|")
    for (N, err, dist) in resumen_verif:
        out.append(f"| {N} | {err:.2e} | {dist} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tamanos", type=int, nargs="+", default=[21, 41, 81, 121, 181],
                    help="número TOTAL de nodos clave (1 base + ~mitad clientes + ~mitad cargadores)")
    ap.add_argument("--algoritmos", nargs="+", default=ALGS)
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", default=str(Path(__file__).resolve().parent / "resultados.md"))
    args = ap.parse_args()
    filas, verif = correr(args.tamanos, args.algoritmos, args.repeticiones)
    tabla = _tabla_md(args.tamanos, filas, verif, args.algoritmos)
    Path(args.salida).write_text(tabla, encoding="utf-8")
    print("\n" + tabla)
    print(f"Tabla escrita en {args.salida}")


if __name__ == "__main__":
    main()
