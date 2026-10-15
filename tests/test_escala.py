"""Pruebas rápidas de las mejoras de escala (agente ESCALA).

Usan red haversine (sin OSM) para ser rápidas y deterministas. Verifican:
  - poda k-vecinos: reduce arcos cliente->cliente y conserva factibilidad/entregas,
  - presupuesto adaptativo: respeta el piso min_s y no recorta instancias pequeñas,
  - el 2-opt acelerado produce tours válidos,
  - las claves de config nuevas se leen de forma defensiva (ausencia = comportamiento base).
"""
from pathlib import Path

import pytest

from evrp import config, heuristica
from evrp.datos import cargar_nodos
from evrp.instancia import construir, tipos_desde_config, _podar_k_vecinos
from evrp.milp_compacto import _presupuesto_adaptativo
from evrp.pipeline import ejecutar
from evrp.red import RedHaversine

CABECERA = ("node_id,node_type,latitude,longitude,address,network,total_ports,"
            "dc_fast_ports,level2_ports,connector_types,max_power_kw\n")


def _csv(tmp_path, filas):
    p = tmp_path / "nodos.csv"
    p.write_text(CABECERA + "\n".join(filas) + "\n", encoding="utf-8")
    return p


def _instancia_densa(tmp_path, nclientes=12):
    """Base + nclientes en una rejilla cercana + un cargador CHAdeMO; red haversine."""
    filas = ["BASE,base,0,0,,,,,,,"]
    for i in range(nclientes):
        lat = 0.002 * (i % 4)
        lon = 0.002 * (i // 4 + 1)
        filas.append(f"V{i + 1},visit,{lat},{lon},,,,,,,")
    filas.append("C1,charger,0,0.001,,,1,1,0,CHAdeMO,50")
    return _csv(tmp_path, filas)


def _cfg(**extra):
    extra.setdefault("pipeline", {"red": "haversine"})
    return config.cargar(None, extra)


# ------------------------------------------------------------ poda k-vecinos
def test_poda_k_vecinos_reduce_arcos(tmp_path):
    cfg = _cfg(solver={"tiempo_limite_s": 5})
    nodos = cargar_nodos(_instancia_densa(tmp_path, 12))
    red = RedHaversine(1.3)
    red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
    inst = construir(nodos, red, cfg)
    arcos0 = sum(len(dt.arcos) for dt in inst.tipos)

    cfg_k = _cfg(solver={"tiempo_limite_s": 5}, escala={"k_vecinos": 3})
    inst_k = construir(nodos, red, cfg_k)
    arcos_k = sum(len(dt.arcos) for dt in inst_k.tipos)
    assert arcos_k < arcos0  # la poda elimina arcos cliente->cliente


def test_poda_k_vecinos_conserva_cliente_arcos():
    # Grafo artificial: 4 clientes totalmente conectados + arcos a base/cargador.
    from evrp.instancia import Estad
    cs = ["V1", "V2", "V3", "V4"]
    arcos = {}
    for i, a in enumerate(cs):
        for j, b in enumerate(cs):
            if a != b:
                arcos[(a, b)] = Estad(float(abs(i - j)), 0.0, 0.0, 0.0)
        arcos[("BASE", a)] = Estad(1.0, 0.0, 0.0, 0.0)
        arcos[(a, "F1")] = Estad(1.0, 0.0, 0.0, 0.0)
    podado = _podar_k_vecinos(arcos, cs, k=1)
    # Se conservan todos los arcos no cliente->cliente.
    assert all((("BASE", c) in podado and (c, "F1") in podado) for c in cs)
    # Hay menos arcos cliente->cliente que en el original (12 pares).
    cc = [(i, j) for (i, j) in podado if i in cs and j in cs]
    assert len(cc) < 12


def test_poda_no_pierde_factibilidad(tmp_path):
    p = _instancia_densa(tmp_path, 12)
    base = ejecutar(str(p), _cfg(solver={"tiempo_limite_s": 10}), None)["kpis"]
    conk = ejecutar(str(p), _cfg(solver={"tiempo_limite_s": 10}, escala={"k_vecinos": 4}),
                    None)["kpis"]
    assert base["factible"] and conk["factible"]
    assert base["entregas"] == conk["entregas"] == 12
    # La poda no debería empeorar de forma apreciable en instancias pequeñas.
    assert conk["energia_total_kwh"] <= base["energia_total_kwh"] + 1e-3


# ----------------------------------------------------- presupuesto adaptativo
def test_presupuesto_adaptativo_piso():
    # Nunca por debajo de min_s.
    assert _presupuesto_adaptativo(5.0, 100, 10000, {"min_s": 10.0}) == 10.0
    # Si el límite supera min_s, se respeta el límite.
    assert _presupuesto_adaptativo(40.0, 100, 10000, {"min_s": 10.0}) == 40.0
    # Default min_s = 10.
    assert _presupuesto_adaptativo(3.0, 50, 5000, {}) == 10.0


def test_adaptativo_no_rompe_pipeline(tmp_path):
    p = _instancia_densa(tmp_path, 10)
    cfg = _cfg(solver={"tiempo_limite_s": 15, "escala": {"adaptativo": True, "min_s": 5}})
    k = ejecutar(str(p), cfg, None)["kpis"]
    assert k["factible"] and k["entregas"] == 10


# ------------------------------------------------------------ 2-opt acelerado
def test_tour_gigante_valido(tmp_path):
    cfg = _cfg(solver={"tiempo_limite_s": 5})
    nodos = cargar_nodos(_instancia_densa(tmp_path, 12))
    red = RedHaversine(1.3)
    red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
    inst = construir(nodos, red, cfg)
    tour = heuristica.tour_gigante(inst, inst.clientes, inst.tipos[0])
    assert sorted(tour) == sorted(inst.clientes)  # permutación de todos los clientes
    assert len(set(tour)) == len(tour)            # sin repetidos


# -------------------------------------------------- lectura defensiva de config
def test_sin_claves_escala_comportamiento_base(tmp_path):
    """Sin 'escala' en config, el pipeline funciona igual que antes (k=0, sin adaptativo)."""
    p = _instancia_densa(tmp_path, 8)
    k = ejecutar(str(p), _cfg(solver={"tiempo_limite_s": 8}), None)["kpis"]
    assert k["factible"] and k["entregas"] == 8
