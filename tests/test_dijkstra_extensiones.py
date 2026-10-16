"""Pruebas de las extensiones de la etapa de caminos (F0, F2, F1-lite).

Todas las extensiones son opciones de config APAGADAS por defecto. La prueba clave
verifica que el resultado por defecto es idéntico a v0.3.0 (competition/eved =
11.1466 kWh, 20/20) y que activar las opciones no rompe el pipeline.
"""
import math
from pathlib import Path

import pytest

import evrp
from evrp import InstanciaPreparada, config
from evrp.datos import cargar_nodos
from evrp.energia import FACTOR_MAXSPEED, tiempo_arco_min, velocidad_efectiva_kmh
from evrp.instancia import tipos_desde_config
from evrp.red import crear_red

RAIZ = Path(__file__).resolve().parents[1]
COMP = RAIZ / "data" / "competition_routing_nodes.csv"

BASE_CFG = {"red": {"osm_permitir_descarga": False}, "solver": {"hilos": 1, "tiempo_limite_s": 60}}


# --- unidades de energia/velocidad (sin red) --------------------------------
def test_velocidad_efectiva_maxspeed_y_tabla():
    v = velocidad_efectiva_kmh("residential", "25 mph")
    assert math.isclose(v, 25 * 1.609344 * FACTOR_MAXSPEED, rel_tol=1e-6)
    assert velocidad_efectiva_kmh("residential", None) == 30.0
    assert velocidad_efectiva_kmh("motorway", None) == 95.0
    assert velocidad_efectiva_kmh("??", None) == 32.0
    assert velocidad_efectiva_kmh(["residential", "unclassified"], None) == 30.0


def test_tiempo_arco_min_monotono():
    assert tiempo_arco_min(1.0, "residential") < tiempo_arco_min(2.0, "residential")
    assert tiempo_arco_min(1.0, "motorway") < tiempo_arco_min(1.0, "residential")
    assert tiempo_arco_min(0.0, "residential") == 0.0


# --- el default NO cambia (clave) -------------------------------------------
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafio")
def test_default_identico_v030():
    r = evrp.resolver(str(COMP), BASE_CFG, ["eved"])
    assert r.kpis["entregas"] == 20
    assert math.isclose(r.kpis["energia_total_kwh"], 11.1466, abs_tol=1e-3)


@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafio")
@pytest.mark.parametrize("extra", [
    {"avisar_clamp": True},
    {"tiempo_arco": True},
    {"tiempo_arco": True, "t_max_trayecto_min": 30},
    {"caminos_alternativos": True},
])
def test_opciones_no_cambian_default(extra):
    """Opciones que, en competition/eved, NO deben alterar el resultado por defecto."""
    cfg = {"red": {"osm_permitir_descarga": False, **extra},
           "solver": {"hilos": 1, "tiempo_limite_s": 60}}
    r = evrp.resolver(str(COMP), cfg, ["eved"])
    assert r.kpis["entregas"] == 20
    assert math.isclose(r.kpis["energia_total_kwh"], 11.1466, abs_tol=1e-3)


# --- F0: assert/aviso del clamp ---------------------------------------------
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafio")
def test_clamp_no_recorta_en_config_real():
    nodos = cargar_nodos(COMP)
    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False, "avisar_clamp": True}}, ["eved"])
    energia = tipos_desde_config(cfg)[0].energia
    red = crear_red(cfg)
    red.preparar(nodos, energia)
    assert red.clamp_info["arcos_recortados"] == 0
    assert red.clamp_info["min_reducido"] >= -1e-6


# --- F2: tiempo por arco y T_max --------------------------------------------
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafio")
def test_tiempo_arco_y_tmax():
    nodos = cargar_nodos(COMP)
    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False, "tiempo_arco": True}}, ["eved"])
    energia = tipos_desde_config(cfg)[0].energia
    red = crear_red(cfg)
    red.preparar(nodos, energia)
    ids = [n.id for n in nodos]
    ts = [red.t_trayecto_min(i, j) for i in ids for j in ids if i != j]
    assert all(t >= 0 for t in ts) and max(ts) > 0
    red.t_max_trayecto_min = 15.0
    red._aplicar_extensiones(nodos, energia)
    descartados_15 = len(red.pares_descartados_tmax)
    red.t_max_trayecto_min = 1000.0
    red._aplicar_extensiones(nodos, energia)
    assert len(red.pares_descartados_tmax) == 0
    assert descartados_15 > 0


# --- F1-lite: camino alternativo de menor pico ------------------------------
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafio")
def test_camino_alternativo_disponible():
    nodos = cargar_nodos(COMP)
    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False,
                                       "caminos_alternativos": True}}, ["eved"])
    energia = tipos_desde_config(cfg)[0].energia
    red = crear_red(cfg)
    red.preparar(nodos, energia)
    alt = red.camino_alternativo("BASE", nodos[1].id)
    assert alt is None or alt[0] == red._snap["BASE"]


# --- esquema /2 de la instancia preparada (lee /1 y /2) ---------------------
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafio")
def test_esquema_v2_ida_y_vuelta(tmp_path):
    prep = evrp.preparar(COMP, {"red": {"osm_permitir_descarga": False, "tiempo_arco": True}}, ["eved"])
    assert prep.esquema.endswith("/2")
    assert prep.tiempos_par and all(t >= 0 for t in prep.tiempos_par.values())
    ruta = prep.guardar(tmp_path / "i.json.gz")
    cargada = InstanciaPreparada.cargar(ruta)
    assert cargada.esquema == prep.esquema
    assert cargada.tiempos_par.keys() == prep.tiempos_par.keys()
    r = evrp.resolver_preparada(cargada, None, ["eved"])
    assert r.kpis["entregas"] == 20
    assert math.isclose(r.kpis["energia_total_kwh"], 11.1466, abs_tol=1e-3)
