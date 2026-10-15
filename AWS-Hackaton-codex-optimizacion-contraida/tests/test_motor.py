import json
import random
from pathlib import Path

import pytest

from evrp import config, heuristica
from evrp.asesor import AsesorNulo, filtrar_ajustes
from evrp.datos import cargar_nodos, compatible
from evrp.instancia import construir, estadisticos, tipos_desde_config
from evrp.pipeline import ejecutar
from evrp.red import RedHaversine
from evrp.validador import validar

RAIZ = Path(__file__).resolve().parents[1]
COMP = RAIZ / "data" / "competition_routing_nodes.csv"
EVAL = RAIZ / "data" / "evaluation_routing_nodes.csv"
CABECERA = "node_id,node_type,latitude,longitude,address,network,total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw\n"


def _csv(tmp_path, filas):
    p = tmp_path / "nodos.csv"
    p.write_text(CABECERA + "\n".join(filas) + "\n", encoding="utf-8")
    return p


def _cfg(**extra):
    # Instancias sintéticas (lat 0, lon 0) fuera del mapa empaquetado: línea recta explícita.
    extra.setdefault("pipeline", {"red": "haversine"})
    return config.cargar(None, extra)


# ----------------------------------------------------------------- datos
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
def test_carga_competencia():
    nodos = cargar_nodos(COMP)
    assert sum(n.tipo == "base" for n in nodos) == 1
    assert sum(n.tipo == "cliente" for n in nodos) == 20
    carg = [n for n in nodos if n.tipo == "cargador"]
    assert len(carg) == 60
    incompatibles = sorted(n.id for n in carg if not compatible(n, {"CHADEMO", "J1772"}))
    assert incompatibles == ["C1", "C11", "C14", "C2", "C4", "C5"]


def test_base_unica(tmp_path):
    p = _csv(tmp_path, ["B1,base,0,0,,,,,,,", "B2,base,0,0.01,,,,,,,"])
    with pytest.raises(ValueError):
        cargar_nodos(p)


# ---------------------------------------------------- lema de estadísticos
def test_estadisticos_vs_simulacion():
    rng = random.Random(7)
    B, bmin = 16.0, 1.6
    for _ in range(500):
        es = [rng.uniform(-1.5, 2.0) for _ in range(rng.randint(1, 12))]
        s = estadisticos(es)
        salida = rng.uniform(bmin, B)
        b, ok = salida, True
        for e in es:
            b = min(B, b - e)
            ok &= b >= bmin - 1e-12
        ok_lema = salida >= bmin + s.pi - 1e-12 and s.lam <= B - bmin + 1e-12
        assert ok == ok_lema
        if ok:
            assert abs(b - min(salida - s.e, B - s.sig)) < 1e-9


# ------------------------------------------------------ instancias sintéticas
def _instancia_carga(tmp_path):
    # Base en el origen; clientes a ~11 km al este; un cargador CHAdeMO en el camino
    # y uno CCS (incompatible). Con B=4 kWh no alcanza sin recargar.
    return _csv(tmp_path, [
        "BASE,base,0,0,,,,,,,",
        "V1,visit,0,0.10,,,,,,,",
        "V2,visit,0,0.11,,,,,,,",
        "V3,visit,0.01,0.105,,,,,,,",
        "C1,charger,0,0.05,,,1,1,0,CHAdeMO,50",
        "C2,charger,0,0.051,,,1,1,0,CCS,350",
    ])


def _cfg_chica(formulacion="compacta"):
    return _cfg(tipos_vehiculo={"leaf2013": {"bateria_kwh": 4.0}},
                solver={"tiempo_limite_s": 20, "formulacion": formulacion},
                flota=[{"tipo": "leaf2013", "cantidad": 2}])


@pytest.mark.parametrize("formulacion", ["compacta", "completa"])
def test_requiere_recarga(tmp_path, formulacion):
    res = ejecutar(str(_instancia_carga(tmp_path)), _cfg_chica(formulacion), None)
    k = res["kpis"]
    assert k["factible"] and k["entregas"] == 3
    usados = [r for r in res["rutas"].values() if len(r) > 2]
    assert all("C1" in r for r in usados)
    assert not any("C2" in r for r in res["rutas"].values())
    for r in res["rutas"].values():
        assert r[0] == "BASE" and r[-1] == "BASE"


def test_compacta_y_completa_coinciden(tmp_path):
    p = str(_instancia_carga(tmp_path))
    a = ejecutar(p, _cfg_chica("compacta"), None)["kpis"]["energia_total_kwh"]
    b = ejecutar(p, _cfg_chica("completa"), None)["kpis"]["energia_total_kwh"]
    assert abs(a - b) < 1e-4


def test_cliente_inalcanzable(tmp_path):
    p = _csv(tmp_path, [
        "BASE,base,0,0,,,,,,,",
        "V1,visit,0,0.01,,,,,,,",
        "V2,visit,0,1.5,,,,,,,",          # ~167 km, sin cargadores cerca
        "C1,charger,0,0.02,,,1,0,1,J1772,6.6",
    ])
    res = ejecutar(str(p), _cfg(solver={"tiempo_limite_s": 10}), None)
    k = res["kpis"]
    assert k["factible"]
    assert k["entregas"] == 1 and k["no_atendidos"] == ["V2"]


def test_cadena_de_cargadores(tmp_path):
    # V1 solo es alcanzable encadenando C1→C2 (la compacta no lo cubre; el pipeline
    # cae a la formulación completa). Energía ≈ 0.2254 kWh por 0.01° de longitud.
    p = _csv(tmp_path, [
        "BASE,base,0,0,,,,,,,",
        "C1,charger,0,0.08,,,1,1,0,CHAdeMO,50",
        "C2,charger,0,0.213,,,1,1,0,CHAdeMO,50",
        "V1,visit,0,0.28,,,,,,,",
    ])
    cfg = _cfg(tipos_vehiculo={"leaf2013": {"bateria_kwh": 4.0}}, solver={"tiempo_limite_s": 20})
    res = ejecutar(str(p), cfg, None)
    k = res["kpis"]
    assert k["factible"] and k["entregas"] == 1
    ruta = next(r for r in res["rutas"].values() if "V1" in r)
    assert ruta[:4] == ["BASE", "C1", "C2", "V1"]


def test_usar_todos_vehiculos(tmp_path):
    p = _csv(tmp_path, ["BASE,base,0,0,,,,,,,", "V1,visit,0,0.01,,,,,,,", "V2,visit,0,0.011,,,,,,,",
                        "C1,charger,0,0.02,,,1,0,1,J1772,6.6"])
    res = ejecutar(str(p), _cfg(solver={"usar_todos_vehiculos": True, "tiempo_limite_s": 10}), None)
    assert all(len(r) > 2 for r in res["rutas"].values())
    assert res["kpis"]["todas_entregadas"]


def test_validador_detecta_bateria(tmp_path):
    cfg = _cfg_chica()
    nodos = cargar_nodos(_instancia_carga(tmp_path))
    red = RedHaversine(1.3)
    red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
    inst = construir(nodos, red, cfg)
    v = validar(inst, {"1": ["BASE", "V1", "V2", "V3", "BASE"]}, {"1": "leaf2013"})
    assert not v["factible"]
    assert any("reserva" in e for e in v["errores"])


# -------------------------------------------------------------- extremo a extremo
@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
@pytest.mark.parametrize("archivo", [COMP, EVAL])
@pytest.mark.parametrize("perfil", ["eved", "ev_routing"])
def test_instancias_oficiales_osm(tmp_path, archivo, perfil):
    """Red vial OSM empaquetada (sin internet) con ambos perfiles de supuestos."""
    res = ejecutar(str(archivo), config.cargar(None, {"red": {"osm_permitir_descarga": False},
                                                      "solver": {"tiempo_limite_s": 30}}, [perfil]), tmp_path)
    k = res["kpis"]
    assert k["factible"] and k["entregas"] == 20
    assert k["red"]["vial"] and k["red"]["tipo"] == "osm"
    assert k["tiempo_computo_s"] < 60
    rutas = json.loads((tmp_path / "routes.json").read_text(encoding="utf-8"))
    assert set(rutas) == {"1", "2"}
    assert (tmp_path / "kpis.json").exists() and (tmp_path / "ledger.jsonl").exists()


@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
def test_milp_no_peor_que_heuristica():
    nodos = cargar_nodos(COMP)
    cfg = _cfg(solver={"tiempo_limite_s": 30})
    k = ejecutar(str(COMP), cfg, None)["kpis"]
    red = RedHaversine(1.3)
    red.preparar(nodos, tipos_desde_config(cfg)[0].energia)
    h = heuristica.resolver(construir(nodos, red, cfg))
    assert k["energia_total_kwh"] <= h.energia + 1e-6


def test_sin_respaldo_linea_recta_falla(tmp_path):
    """Nodos fuera del mapa, sin descarga y sin respaldo: error claro (no inventa una red)."""
    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False}, "solver": {"tiempo_limite_s": 5}})
    with pytest.raises(RuntimeError):
        ejecutar(str(_instancia_carga(tmp_path)), cfg, None)


def test_respaldo_linea_recta_explicito(tmp_path):
    cfg = config.cargar(None, {"red": {"osm_permitir_descarga": False, "respaldo_linea_recta": True},
                               "solver": {"tiempo_limite_s": 10},
                               "tipos_vehiculo": {"leaf2013": {"bateria_kwh": 4.0, "reserva_kwh": None}}})
    res = ejecutar(str(_instancia_carga(tmp_path)), cfg, None)
    assert "red_respaldo" in [e["paso"] for e in res["bitacora"]]
    assert res["kpis"]["factible"] and not res["kpis"]["red"]["vial"]


def test_perfiles():
    a = config.cargar(None, None, ["ev_routing"])["tipos_vehiculo"]["leaf2013"]
    assert a["bateria_kwh"] == 24.0 and config.reserva_kwh(a) == 2.4
    b = config.cargar(None, None, ["eved"])["tipos_vehiculo"]["leaf2013"]
    assert b["bateria_kwh"] == 16.0 and config.reserva_kwh(b) == 1.6
    with pytest.raises(ValueError):
        config.cargar(None, None, ["no_existe"])


def test_motor_abstracto():
    from evrp import MotorEvrp

    if not COMP.exists():
        pytest.skip("sin datos")
    out = MotorEvrp().resolver({"nodos_csv": str(COMP), "presupuesto_s": 30,
                                "supuestos": {"bateria_kwh": 24, "reserva_kwh": 2.4, "red": "osm"},
                                "flota": {"vehiculos": 3}})
    assert out["estado"] == "ok" and out["entregas"] == 20 and len(out["rutas"]) == 3


# ------------------------------------------------------------------ asesor
def test_asesor_lista_blanca():
    propuesta = {"pipeline": {"cargadores": "todos", "red": "osm"},
                 "solver": {"tiempo_limite_s": 9999}, "cargadores": {"top_r": 4}}
    assert filtrar_ajustes(propuesta) == {"pipeline": {"cargadores": "todos"}, "cargadores": {"top_r": 4}}
    assert AsesorNulo().sugerir_config({}, {}) == {} and AsesorNulo().explicar({}) is None


def test_config_invalida():
    with pytest.raises(ValueError):
        config.cargar(None, {"pipeline": {"solver": "magia"}})
