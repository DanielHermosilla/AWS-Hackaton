"""Pruebas de los algoritmos de caminos de mínima energía (src/evrp/caminos.py).

Verifican que todos los algoritmos (multi-destino, bidireccional, A*, ALT, scipy,
networkx) entregan la MISMA energía por par (tol. 1e-9 relativa) y que la opción
`red.algoritmo_caminos` no cambia los resultados del pipeline.
"""
import math
from pathlib import Path

import pytest

from evrp import config
from evrp.caminos import ALGORITMOS, GrafoCaminos, resolver_caminos
from evrp.datos import cargar_nodos
from evrp.instancia import tipos_desde_config
from evrp.red import RedOSM

RAIZ = Path(__file__).resolve().parents[1]
COMP = RAIZ / "data" / "competition_routing_nodes.csv"


def _grafo_juguete():
    """Grafo dirigido pequeño con pesos (= energía, potencial 0). Coordenadas lineales.

    0→1→2→3→4 encadenado (barato) y un atajo caro 0→4. El mínimo 0→4 es la cadena.
    """
    ady = {
        0: [(1, 1.0, 1.0, 0.0), (4, 10.0, 10.0, 0.0)],
        1: [(2, 1.0, 1.0, 0.0)],
        2: [(3, 1.0, 1.0, 0.0)],
        3: [(4, 1.0, 1.0, 0.0)],
        4: [(0, 1.0, 1.0, 0.0)],
    }
    pot = {v: 0.0 for v in range(5)}
    lat_lon = {v: (0.0, 0.001 * v) for v in range(5)}  # casi colineales
    return GrafoCaminos(ady, pot, lat_lon, consumo=0.1)


def _energia(g, cam):
    e = 0.0
    for u, v in zip(cam, cam[1:]):
        w = next(c for (vv, _, c, _) in g.ady[u] if vv == v)  # km del arco
        e += g.consumo * w
    return e


def test_todos_los_algoritmos_mismo_optimo_juguete():
    g = _grafo_juguete()
    claves = {chr(ord("A") + v): v for v in range(5)}
    pares = [("A", "E")]
    energias = {}
    for alg in ALGORITMOS:
        g._csr = g._nodos = g._idx = g._rev = None
        cam = resolver_caminos(g, claves, pares, alg)[("A", "E")]
        assert cam[0] == 0 and cam[-1] == 4
        energias[alg] = _energia(g, cam)
    # el óptimo es la cadena 0→1→2→3→4 (4 arcos × 1 km × 0.1 = 0.4), no el atajo (1.0)
    ref = energias["multi_destino"]
    assert abs(ref - 0.4) < 1e-12
    for alg, e in energias.items():
        assert abs(e - ref) < 1e-9, f"{alg} difiere: {e} vs {ref}"


@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
def test_algoritmos_coinciden_en_mapa_real():
    """Sobre el mapa empaquetado y la instancia oficial: misma energía por par."""
    nodos = cargar_nodos(COMP)
    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False}}, ["eved"])
    energia = tipos_desde_config(cfg)[0].energia
    r = RedOSM(2.0, ".cache/osm", None, None, False, "multi_destino", True)
    r.preparar(nodos, energia)

    pot = {v: 0.0 for v in r._ady}
    lat_lon = {v: (r.G.nodes[v]["y"], r.G.nodes[v]["x"]) for v in r._ady}
    for n in nodos:
        s = r._snap[n.id]
        lat_lon.setdefault(s, (r.G.nodes[s]["y"], r.G.nodes[s]["x"]))
        pot.setdefault(s, 0.0)
    g = GrafoCaminos(r._ady, pot, lat_lon, energia.consumo_kwh_km)
    orig = {n.id: r._snap[n.id] for n in nodos}

    # subconjunto de pares (base + 5 clientes) para que las variantes par-a-par sean rápidas
    ids = [n.id for n in nodos if n.tipo in ("base", "cliente")][:6]
    pares = [(i, j) for i in ids for j in ids if i != j]

    def energia_camino(cam):
        return sum(energia.tramo(*r._tramo_arco[(u, v)]) for u, v in zip(cam, cam[1:]))

    ref = {p: energia_camino(resolver_caminos(g, orig, [p], "multi_destino")[p]) for p in pares}
    for alg in ALGORITMOS:
        g._csr = g._nodos = g._idx = g._rev = None
        caminos = resolver_caminos(g, orig, pares, alg)
        for p in pares:
            e = energia_camino(caminos[p])
            assert math.isclose(e, ref[p], rel_tol=1e-9, abs_tol=1e-12), f"{alg} {p}: {e} vs {ref[p]}"


@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
def test_pipeline_identico_entre_algoritmos():
    """La opción red.algoritmo_caminos no cambia energía ni km del resultado."""
    from evrp.pipeline import ejecutar

    def kpis(alg):
        cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False,
                                           "algoritmo_caminos": alg},
                                   "solver": {"tiempo_limite_s": 30}}, ["eved"])
        return ejecutar(str(COMP), cfg, None)["kpis"]

    a = kpis("multi_destino")
    b = kpis("scipy")
    assert a["entregas"] == b["entregas"]
    assert abs(a["energia_total_kwh"] - b["energia_total_kwh"]) < 1e-9
    assert abs(a["km_total"] - b["km_total"]) < 1e-9


def test_algoritmo_invalido():
    g = _grafo_juguete()
    with pytest.raises(ValueError):
        resolver_caminos(g, {"A": 0}, [("A", "A")], "inexistente")
