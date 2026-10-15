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
