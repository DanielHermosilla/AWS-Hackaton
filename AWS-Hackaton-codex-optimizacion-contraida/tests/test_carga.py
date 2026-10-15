"""Potencia efectiva por conector y recarga acotada por potencia × tiempo por parada."""
from pathlib import Path

import pytest

from evrp import config
from evrp.datos import Nodo, cargar_nodos, potencia_efectiva_kw
from evrp.instancia import construir, tipos_desde_config
from evrp.pipeline import ejecutar
from evrp.red import RedHaversine
from evrp.validador import validar

RAIZ = Path(__file__).resolve().parents[1]
COMP = RAIZ / "data" / "competition_routing_nodes.csv"
CABECERA = "node_id,node_type,latitude,longitude,address,network,total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw\n"
LEAF = {"CHADEMO", "J1772"}


def _carg(conectores, kw, dc=None, ac=None):
    return Nodo("C", "cargador", 0, 0, 0, frozenset(conectores), None, kw, puertos_dc=dc, puertos_ac=ac)


# ------------------------------------------------------------ potencia efectiva
@pytest.mark.parametrize(("conectores", "kw", "dc", "ac", "esperado"), [
    ({"CHADEMO", "CCS", "NACS"}, 150.0, 10, 0, 50.0),      # estación rápida: manda el auto (50 kW)
    ({"CHADEMO"}, 30.0, 1, 0, 30.0),                        # estación más lenta que el auto
    ({"J1772"}, 19.2, 0, 5, 6.6),                           # AC: manda el cargador a bordo
    ({"J1772"}, 6.2, 0, 2, 6.2),                            # AC más lenta que el cargador a bordo
    ({"CCS", "NACS"}, 400.0, 20, 0, 0.0),                   # sin conector común
    ({"CHADEMO", "J1772"}, 80.0, 0, 6, 6.6),                # CHAdeMO listado sin puertos DC → solo AC
    ({"CHADEMO", "J1772"}, 80.0, 1, 6, 50.0),               # elige el mejor conector común
    ({"CHADEMO"}, None, None, None, 50.0),                  # potencia/puertos de la estación desconocidos
])
def test_potencia_efectiva_leaf(conectores, kw, dc, ac, esperado):
    assert potencia_efectiva_kw(_carg(conectores, kw, dc, ac), LEAF, 50.0, 6.6) == esperado


def test_potencia_nacs_depende_de_puertos_y_auto_sin_dato():
    tesla = {"NACS"}
    assert potencia_efectiva_kw(_carg({"NACS"}, 250.0, 4, 0), tesla, 170.0, 11.5) == 170.0
    assert potencia_efectiva_kw(_carg({"NACS"}, 16.0, 0, 4), tesla, 170.0, 11.5) == 11.5
    assert potencia_efectiva_kw(_carg({"CHADEMO"}, 50.0, 1, 0), LEAF, None, 6.6) is None


@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
def test_leaf_carga_rapida_solo_en_7_chademo():
    t = config.cargar(None, None)["tipos_vehiculo"]["leaf2013"]
    pot = {n.id: potencia_efectiva_kw(n, set(t["conectores"]), t["potencia_dc_kw"], t["potencia_ac_kw"])
           for n in cargar_nodos(COMP) if n.tipo == "cargador"}
    assert sorted(k for k, p in pot.items() if p and p >= 20) == sorted(
        ["C3", "C6", "C7", "C8", "C9", "C10", "C12"])
    assert all(p == 50.0 for k, p in pot.items() if p and p >= 20)
    assert sorted(k for k, p in pot.items() if p == 0.0) == sorted(["C1", "C2", "C4", "C5", "C11", "C14"])
    assert max(p for p in pot.values() if p and p < 20) <= 6.6


# --------------------------------------------------------- recarga acotada P × T
def _instancia(tmp_path):
    """V1 a ~2,25 kWh de la base. C_AC (J1772 6,6 kW) en la línea recta; C_DC (CHAdeMO 50 kW)
    con un pequeño desvío. B = 4 kWh, b_ini = 2,4, reserva = 0,4: hay que cargar ≥ ~1,5 kWh."""
    p = tmp_path / "nodos.csv"
    p.write_text(CABECERA + "\n".join([
        "BASE,base,0,0,,,,,,,",
        "V1,visit,0,0.10,,,,,,,",
        "CAC,charger,0,0.05,,,1,0,1,J1772,6.6",
        "CDC,charger,0.02,0.05,,,1,1,0,CHAdeMO,50",
    ]) + "\n", encoding="utf-8")
    return str(p)


def _cfg(tmax=None, solver="milp"):
    return config.cargar(None, {
        "pipeline": {"red": "haversine", "solver": solver},
        "tipos_vehiculo": {"leaf2013": {"bateria_kwh": 4.0}},
        "flota": [{"tipo": "leaf2013", "cantidad": 1}],
        "solver": {"tiempo_limite_s": 10},
        "carga": {"max_min_por_parada": tmax},
    })


def test_sin_tope_usa_el_cargador_mas_cercano(tmp_path):
    res = ejecutar(_instancia(tmp_path), _cfg(None), None)
    k = res["kpis"]
    assert k["factible"] and k["entregas"] == 1
    assert "CAC" in res["rutas"]["1"] and "CDC" not in res["rutas"]["1"]
    # Carga completa en AC 6,6 kW: el tiempo se informa aunque no limite.
    assert k["carga"]["max_min_por_parada"] is None
    assert k["por_vehiculo"]["1"]["tiempo_carga_min"] > 20


@pytest.mark.parametrize("solver", ["milp", "heuristica"])
def test_tope_de_5_min_obliga_a_cargar_en_dc(tmp_path, solver):
    res = ejecutar(_instancia(tmp_path), _cfg(5, solver), None)
    k = res["kpis"]
    assert k["factible"] and k["entregas"] == 1
    assert "CDC" in res["rutas"]["1"]
    paradas = [p for p in res["detalle"]["1"] if p["tipo"] == "cargador"]
    assert all(p["carga_kwh"] <= 50 * 5 / 60 + 1e-6 for p in paradas)
    assert all(p["tiempo_carga_min"] <= 5 + 1e-6 for p in paradas)
    assert any(p["potencia_kw"] == 50.0 for p in paradas)
    assert 0 < k["carga"]["tiempo_total_min"] <= 5 * len(paradas) + 1e-6


def test_tope_muy_corto_deja_cliente_sin_atender(tmp_path):
    k = ejecutar(_instancia(tmp_path), _cfg(1), None)["kpis"]
    assert k["factible"] and k["entregas"] == 0 and k["no_atendidos"] == ["V1"]


def test_tope_enorme_equivale_a_carga_completa(tmp_path):
    a = ejecutar(_instancia(tmp_path), _cfg(None), None)["kpis"]["energia_total_kwh"]
    b = ejecutar(_instancia(tmp_path), _cfg(10_000), None)["kpis"]["energia_total_kwh"]
    assert abs(a - b) < 1e-6


def test_validador_rechaza_ruta_que_supone_carga_completa(tmp_path):
    ruta = {"1": ["BASE", "CAC", "V1", "CAC", "BASE"]}
    for tmax, factible in [(None, True), (5, False)]:
        cfg = _cfg(tmax)
        nodos = cargar_nodos(_instancia(tmp_path))
        red = RedHaversine(1.3)
        red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
        v = validar(construir(nodos, red, cfg), ruta, {"1": "leaf2013"})
        assert v["factible"] is factible


@pytest.mark.parametrize("extra", [
    {"carga": {"max_min_por_parada": 0}},
    {"carga": {"max_min_por_parada": 10}, "solver": {"formulacion": "completa"}},
    {"tipos_vehiculo": {"leaf2013": {"potencia_dc_kw": -1}}},
])
def test_config_de_carga_invalida(extra):
    with pytest.raises(ValueError):
        config.cargar(None, extra)


def test_tope_sin_potencia_del_vehiculo_falla_claro(tmp_path):
    cfg = config.cargar(None, {"pipeline": {"red": "haversine"}, "carga": {"max_min_por_parada": 10},
                               "tipos_vehiculo": {"leaf2013": {"potencia_dc_kw": None}}})
    with pytest.raises(ValueError, match="potencia_dc_kw"):
        ejecutar(_instancia(tmp_path), cfg, None)
