from pathlib import Path

import pytest

import evrp
from evrp import InstanciaPreparada
from evrp.cli import main as cli

RAIZ = Path(__file__).resolve().parents[1]
COMP = RAIZ / "data" / "competition_routing_nodes.csv"
CAB = "node_id,node_type,latitude,longitude,address,network,total_ports,dc_fast_ports,level2_ports,connector_types,max_power_kw\n"
HAV = {"pipeline": {"red": "haversine"}, "solver": {"tiempo_limite_s": 10, "presupuesto_total_s": 10}}


def _csv(tmp_path):
    p = tmp_path / "n.csv"
    p.write_text(CAB + "\n".join([
        "BASE,base,0,0,,,,,,,", "V1,visit,0,0.10,,,,,,,", "V2,visit,0,0.11,,,,,,,",
        "V3,visit,0.01,0.105,,,,,,,", "C1,charger,0,0.05,,,1,1,0,CHAdeMO,50",
        "C2,charger,0,0.051,,,1,1,0,CCS,350"]) + "\n", encoding="utf-8")
    return p


def _hav(**extra):
    return {**HAV, "tipos_vehiculo": {"leaf2013": {"bateria_kwh": 4.0}}, **extra}


@pytest.mark.parametrize("sufijo", [".json", ".json.gz"])
def test_ida_y_vuelta_identica(tmp_path, sufijo):
    csv = _csv(tmp_path)
    prep = evrp.preparar(csv, _hav(), geometria=True)
    ruta = prep.guardar(tmp_path / f"i{sufijo}")
    cargada = InstanciaPreparada.cargar(ruta)
    assert cargada.tramos.keys() == prep.tramos.keys()
    assert [n.id for n in cargada.nodos] == [n.id for n in prep.nodos]
    assert cargada.nodos[4].conectores == frozenset({"CHADEMO"})
    a = evrp.resolver(csv, _hav())
    b = evrp.resolver_preparada(cargada, _hav())
    assert a.rutas == b.rutas and abs(a.kpis["energia_total_kwh"] - b.kpis["energia_total_kwh"]) < 1e-9


def test_misma_preparacion_distinta_bateria_y_flota(tmp_path):
    prep = evrp.preparar(_csv(tmp_path), _hav())
    r1 = evrp.resolver_preparada(prep, _hav())
    r2 = evrp.resolver_preparada(prep, {**HAV, "flota": [{"tipo": "leaf2013", "cantidad": 3}],
                                        "tipos_vehiculo": {"leaf2013": {"bateria_kwh": 40.0}}})
    assert r1.kpis["factible"] and r2.kpis["factible"]
    assert len(r2.rutas) == 3
    # con batería grande no hace falta pasar por el cargador
    assert not any("C1" in r for r in r2.rutas.values())


def test_excluir_nodos(tmp_path):
    prep = evrp.preparar(_csv(tmp_path), _hav())
    r = evrp.resolver_preparada(prep, _hav(), excluir=["V3"])
    assert r.kpis["clientes"] == 2 and "V3" not in sum(r.rutas.values(), [])
    with pytest.raises(ValueError):
        evrp.resolver_preparada(prep, _hav(), excluir=["BASE"])


def test_pendiente_incompatible(tmp_path):
    prep = evrp.preparar(_csv(tmp_path), _hav())
    with pytest.raises(ValueError, match="pipeline.energia"):
        evrp.resolver_preparada(prep, {**_hav(), "pipeline": {"red": "haversine", "energia": "pendiente"}})


def test_esquema_desconocido():
    with pytest.raises(ValueError, match="Esquema"):
        InstanciaPreparada.desde_dict({"esquema": "otro/9"})


def test_cli_preparar_y_resolver(tmp_path, capsys):
    csv = _csv(tmp_path)
    inst = tmp_path / "i.json.gz"
    assert cli(["preparar", "--nodes", str(csv), "--red", "haversine", "--out", str(inst)]) == 0
    assert inst.exists()
    cfg = tmp_path / "c.yaml"
    cfg.write_text("tipos_vehiculo:\n  leaf2013:\n    bateria_kwh: 4.0\n", encoding="utf-8")
    codigo = cli(["resolver", "--instancia", str(inst), "--config", str(cfg), "--tiempo", "10",
                  "--out", str(tmp_path / "res")])
    assert codigo == 0 and (tmp_path / "res" / "routes.json").exists()


@pytest.mark.skipif(not COMP.exists(), reason="sin datos del desafío")
def test_competencia_osm_preparada():
    prep = evrp.preparar(COMP, {"red": {"osm_permitir_descarga": False}}, ["eved"])
    assert prep.red["vial"] and len(prep.tramos) == 81 * 80
    r = evrp.resolver_preparada(prep, None, ["eved"])
    assert r.kpis["entregas"] == 20 and r.kpis["factible"] and r.kpis["red"]["vial"]
