"""Pruebas rapidas de la arena. Sin red ni subprocesos: instancias diminutas con red
haversine (linea recta). Verifican el validador neutral, el adaptador in-process de
evrp, la competencia de solvers sobre MPS y la carga del esquema/escenarios.
"""
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

import sys
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

CABECERA = ("node_id,node_type,latitude,longitude,address,network,total_ports,"
            "dc_fast_ports,level2_ports,connector_types,max_power_kw\n")


def _csv(tmp_path, filas):
    p = tmp_path / "nodos.csv"
    p.write_text(CABECERA + "\n".join(filas) + "\n", encoding="utf-8")
    return str(p)


def _instancia_min(tmp_path):
    """Base + 2 clientes + 1 cargador compatible, cerca entre si (haversine corta)."""
    filas = [
        "BASE,base,42.2800,-83.7400,,,,,,,",
        "V1,visit,42.2820,-83.7420,,,,,,,",
        "V2,visit,42.2790,-83.7380,,,,,,,",
        "C1,charger,42.2810,-83.7410,,,2,0,2,J1772,6.6",
    ]
    return _csv(tmp_path, filas)


def _sup(**over):
    from arena.supuestos import SupuestosComunes
    base = dict(bateria_kwh=24.0, reserva_kwh=2.4, soc_inicial=0.6, consumo_kwh_km=0.1567712473,
                conectores=("CHADEMO", "J1772"), red="haversine", pendiente=False,
                max_acceso_m=None, perfil="ev_routing")
    base.update(over)
    return SupuestosComunes(**base)


# ---------------------------------------------------------------- esquema
def test_esquema_y_escenarios_cargan():
    esquema = json.loads((RAIZ / "arena" / "esquema_escenario.json").read_text(encoding="utf-8"))
    assert esquema["type"] == "object"
    for nombre in ("smoke", "escala_clientes", "flota"):
        esc = json.loads((RAIZ / "arena" / "escenarios" / f"{nombre}.json").read_text(encoding="utf-8"))
        assert esc["nombre"]
        assert esc["instancias"]
        assert esc["motores"]


def test_resolver_supuestos_perfil():
    from arena.supuestos import resolver
    sup = resolver({"supuestos": {"perfil": "eved"}})
    assert sup.bateria_kwh == 16.0 and sup.reserva_kwh == 1.6
    sup2 = resolver({"supuestos": {"perfil": "ev_routing", "bateria_kwh": 30.0}})
    assert sup2.bateria_kwh == 30.0 and sup2.reserva_kwh == 2.4


# ------------------------------------------------------- validador neutral
def test_validador_neutral_ruta_factible(tmp_path):
    from arena.validador_neutral import Supuestos, ValidadorNeutral
    csv = _instancia_min(tmp_path)
    vsup = Supuestos(24.0, 2.4, 0.6, 0.1567712473, {"CHADEMO", "J1772"})
    v = ValidadorNeutral(csv, vsup, red="haversine")
    out = v.validar_clave({"1": ["BASE", "V1", "V2", "BASE"], "2": ["BASE", "BASE"]})
    assert out.factible
    assert out.entregas == 2 and out.clientes == 2
    assert out.energia_total_kwh > 0 and out.km_total > 0


def test_validador_neutral_detecta_cliente_repetido(tmp_path):
    from arena.validador_neutral import Supuestos, ValidadorNeutral
    csv = _instancia_min(tmp_path)
    vsup = Supuestos(24.0, 2.4, 0.6, 0.1567712473, {"CHADEMO", "J1772"})
    v = ValidadorNeutral(csv, vsup, red="haversine")
    out = v.validar_clave({"1": ["BASE", "V1", "BASE"], "2": ["BASE", "V1", "BASE"]})
    assert not out.factible
    assert any("repetido" in e for e in out.errores)


def test_validador_neutral_detecta_no_inicia_en_base(tmp_path):
    from arena.validador_neutral import Supuestos, ValidadorNeutral
    csv = _instancia_min(tmp_path)
    vsup = Supuestos(24.0, 2.4, 0.6, 0.1567712473, {"CHADEMO", "J1772"})
    v = ValidadorNeutral(csv, vsup, red="haversine")
    out = v.validar_clave({"1": ["V1", "V2", "BASE"]})
    assert not out.factible
    assert any("BASE" in e for e in out.errores)


def test_validador_neutral_modo_calle(tmp_path):
    from arena.validador_neutral import Supuestos, ValidadorNeutral
    csv = _instancia_min(tmp_path)
    vsup = Supuestos(24.0, 2.4, 0.6, 0.1567712473, {"CHADEMO", "J1772"})
    v = ValidadorNeutral(csv, vsup, red="haversine")
    # Tramos explicitos (km, desnivel) por paso, como entregaria un motor calle a calle.
    entrada = {"1": {"nodos": ["BASE", "V1", "BASE"],
                     "tramos_por_paso": [[(0.5, 0.0)], [(0.5, 0.0)]]}}
    out = v.validar_calle(entrada)
    assert out.factible
    assert out.entregas == 1
    assert abs(out.km_total - 1.0) < 1e-6


# -------------------------------------------------- adaptador evrp in-process
def test_adaptador_evrp_haversine(tmp_path):
    from arena.adaptadores import evrp_adaptador
    from arena.validador_neutral import Supuestos, ValidadorNeutral
    csv = _instancia_min(tmp_path)
    sup = _sup()
    res = evrp_adaptador.resolver(csv, sup, 2, 15, 1, {"formulacion": "compacta"})
    assert res["estado"] == "ok"
    assert res["entregas"] == 2
    assert res["tipo_rutas"] == "clave"
    v = ValidadorNeutral(csv, Supuestos(24.0, 2.4, 0.6, 0.1567712473, {"CHADEMO", "J1772"}),
                         red="haversine")
    out = v.validar_clave(res["rutas"])
    assert out.factible and out.entregas == 2


# -------------------------------------------- competencia de solvers (MPS)
def test_competencia_solvers_mps(tmp_path):
    from arena import solvers
    csv = _instancia_min(tmp_path)
    sup = _sup()
    mps = tmp_path / "m.mps"
    meta = solvers.construir_mps_evrp(csv, sup, 2, str(tmp_path / "osm"), mps, "entregas")
    assert meta["columnas"] > 0 and meta["filas"] > 0
    assert mps.exists()
    salidas = {s["solver"]: s for s in solvers.competir(str(mps), ["highs", "scip", "cbc"], 10, 1)}
    assert salidas["highs"]["objetivo"] == 2.0
    assert salidas["scip"]["objetivo"] == 2.0
    # cbc puede no estar disponible (pulp 4.0.1 sin ejecutable): se registra, no falla.
    assert salidas["cbc"]["estado"] in ("no_disponible", "Optimal", "error")


def test_materializar_subconjunto(tmp_path):
    from arena.instancias import materializar
    filas = [
        "BASE,base,42.28,-83.74,,,,,,,",
        "V1,visit,42.282,-83.742,,,,,,,",
        "V2,visit,42.279,-83.738,,,,,,,",
        "V3,visit,42.277,-83.736,,,,,,,",
        "C1,charger,42.281,-83.741,,,2,0,2,J1772,6.6",
    ]
    csv = _csv(tmp_path, filas)
    out = materializar({"nombre": "sub", "csv": csv, "max_clientes": 2}, tmp_path / "mat")
    texto = Path(out).read_text(encoding="utf-8")
    assert "V1" in texto and "V2" in texto and "V3" not in texto
    assert "C1" in texto and "BASE" in texto


def test_materializar_cargadores_cercanos(tmp_path):
    from arena.instancias import materializar
    filas = [
        "BASE,base,42.280,-83.740,,,,,,,",
        "V1,visit,42.281,-83.741,,,,,,,",
        "C1,charger,42.2805,-83.7405,,,2,0,2,J1772,6.6",  # muy cerca
        "C2,charger,42.350,-83.900,,,2,0,2,J1772,6.6",     # lejos
    ]
    csv = _csv(tmp_path, filas)
    out = materializar({"nombre": "sub", "csv": csv, "max_cargadores": 1}, tmp_path / "mat")
    texto = Path(out).read_text(encoding="utf-8")
    assert "C1" in texto and "C2" not in texto


# -------------------------------------------------- validador neutral OSM
def _graphml_minimo(tmp_path):
    """GraphML dirigido con una cadena de 3 intersecciones y una recta de ~0.5 km/arco."""
    import networkx as nx
    g = nx.MultiDiGraph()
    g.graph["crs"] = "epsg:4326"
    # 3 nodos en linea; ~0.0045 deg lat ~ 500 m.
    puntos = {"n0": (42.2800, -83.7400), "n1": (42.2845, -83.7400),
              "n2": (42.2890, -83.7400)}
    for nid, (y, x) in puntos.items():
        g.add_node(nid, y=y, x=x)
    # Arcos bidireccionales con length en metros.
    for a, b in [("n0", "n1"), ("n1", "n2")]:
        g.add_edge(a, b, length=500.0)
        g.add_edge(b, a, length=500.0)
    p = tmp_path / "mini.graphml"
    nx.write_graphml(g, str(p))
    return str(p)


def _csv_osm(tmp_path):
    """BASE en n0, V1 en n2, cargador C1 en n1 (todos pegados a una interseccion)."""
    filas = [
        "BASE,base,42.2800,-83.7400,,,,,,,",
        "V1,visit,42.2890,-83.7400,,,,,,,",
        "C1,charger,42.2845,-83.7400,,,2,0,2,J1772,6.6",
    ]
    return _csv(tmp_path, filas)


def test_validador_osm_ruta_factible(tmp_path):
    from arena.validador_osm import ValidadorOSM
    gml = _graphml_minimo(tmp_path)
    csv = _csv_osm(tmp_path)
    v = ValidadorOSM(csv, gml, bateria_kwh=24.0, reserva_kwh=2.4, soc_inicial=0.6,
                     consumo_kwh_km=0.1567712473, conectores_vehiculo={"J1772"},
                     max_snap_distance_m=100.0)
    out = v.validar_clave({"veh1": ["BASE", "V1", "BASE"], "veh2": ["BASE", "BASE"]})
    assert out.factible, out.errores
    assert out.entregas == 1 and out.clientes == 1
    # BASE->V1->BASE son 4 arcos de 500 m = 2 km.
    assert abs(out.km_total - 2.0) < 1e-3
    assert out.energia_total_kwh > 0


def test_validador_osm_cliente_repetido(tmp_path):
    from arena.validador_osm import ValidadorOSM
    gml = _graphml_minimo(tmp_path)
    csv = _csv_osm(tmp_path)
    v = ValidadorOSM(csv, gml, bateria_kwh=24.0, reserva_kwh=2.4, soc_inicial=0.6,
                     consumo_kwh_km=0.1567712473, conectores_vehiculo={"J1772"})
    out = v.validar_clave({"a": ["BASE", "V1", "BASE"], "b": ["BASE", "V1", "BASE"]})
    assert not out.factible
    assert any("repetido" in e for e in out.errores)


def test_validador_osm_cargador_incompatible(tmp_path):
    from arena.validador_osm import ValidadorOSM
    gml = _graphml_minimo(tmp_path)
    csv = _csv_osm(tmp_path)
    # Vehiculo solo CHAdeMO; C1 es J1772 -> incompatible.
    v = ValidadorOSM(csv, gml, bateria_kwh=24.0, reserva_kwh=2.4, soc_inicial=0.6,
                     consumo_kwh_km=0.1567712473, conectores_vehiculo={"CHADEMO"})
    out = v.validar_clave({"a": ["BASE", "C1", "V1", "BASE"]})
    assert not out.factible
    assert any("incompatible" in e for e in out.errores)


def test_validador_osm_no_inicia_en_base(tmp_path):
    from arena.validador_osm import ValidadorOSM
    gml = _graphml_minimo(tmp_path)
    csv = _csv_osm(tmp_path)
    v = ValidadorOSM(csv, gml, bateria_kwh=24.0, reserva_kwh=2.4, soc_inicial=0.6,
                     consumo_kwh_km=0.1567712473, conectores_vehiculo={"J1772"})
    out = v.validar_clave({"a": ["V1", "BASE"]})
    assert not out.factible
    assert any("BASE" in e for e in out.errores)


def test_scip_arena_importa_y_expone_api():
    from arena import scip_arena
    assert scip_arena.H_SWEEP == [30, 60, 100]
    assert set(scip_arena.CLIENTES) == {"c1", "c2", "c3", "c5"}
    assert scip_arena.SCIP_BIN.name == "bin"
    # El runner existe y acepta el flujo del companero.
    runner = (RAIZ / "arena" / "adaptadores" / "ev_routing_runner.py").read_text(encoding="utf-8")
    assert "--flujo-companero" in runner
    assert "solve_instance" in runner
