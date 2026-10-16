"""Tests del paquete assist sin red (dobles de Bedrock y del solver).

No requieren boto3 ni credenciales: validan la lista blanca, la sesion con
snapshot inicial, la extraccion de hechos, el verificador anti-alucinacion y la
explicacion por plantilla.
"""

from __future__ import annotations

import pytest

from ev_routing.assist.explainer import explicar
from ev_routing.assist.facts import extraer_hechos
from ev_routing.assist.tools import ErrorParametro, validar_parametro
from ev_routing.assist.verifier import verificar


# --- lista blanca ----------------------------------------------------------
def test_parametro_desconocido_se_rechaza():
    with pytest.raises(ErrorParametro):
        validar_parametro("inexistente", 1)


def test_flota_maxima_es_diez():
    spec, valor = validar_parametro("vehiculos", 10)
    assert valor == 10
    assert spec.importante is True
    with pytest.raises(ErrorParametro):
        validar_parametro("vehiculos", 11)


def test_valor_fuera_de_rango_se_rechaza():
    with pytest.raises(ErrorParametro):
        validar_parametro("soc_inicial", 1.5)


# --- hechos y resultado de muestra ----------------------------------------
RESULTADO = {
    "status": "ok",
    "solve": {
        "status": "optimal",
        "lexicographic_optimal": True,
        "phases": [{"name": "deliveries", "relative_gap": 0.0}],
        "solution": {
            "served_visit_ids": ["C1", "C2"],
            "unserved_visit_ids": ["C3"],
            "net_energy_kwh": 12.5,
            "routes": [
                {
                    "vehicle_id": "V1",
                    "net_energy_kwh": 12.5,
                    "duration_seconds": 3600,
                    "steps": [
                        {"node_id": "C1", "delivered_visit_ids": ["C1"],
                         "charged_to_battery_kwh": 0.0},
                        {"node_id": "CH1", "delivered_visit_ids": [],
                         "charged_to_battery_kwh": 8.0},
                        {"node_id": "C2", "delivered_visit_ids": ["C2"],
                         "charged_to_battery_kwh": 0.0},
                    ],
                }
            ],
        },
    },
    "validation": {"feasible": True},
}


def test_extraer_hechos_mapea_rutas_y_carga():
    hechos = extraer_hechos(RESULTADO)
    assert hechos.entregados == ["C1", "C2"]
    assert hechos.sin_atender == ["C3"]
    assert hechos.optimo_lexicografico is True
    assert len(hechos.rutas) == 1
    ruta = hechos.rutas[0]
    assert ruta.vehiculo == "V1"
    assert ruta.entregas == ["C1", "C2"]
    assert ruta.paradas_carga == ["CH1"]


def test_extraer_hechos_tolera_solucion_vacia():
    hechos = extraer_hechos({"status": "infeasible", "solve": {}})
    assert hechos.entregados == []
    assert hechos.rutas == []


# --- verificador -----------------------------------------------------------
def test_verificador_detecta_id_inventado():
    hechos = extraer_hechos(RESULTADO)
    rep = verificar("El vehiculo V9 entrega a C7.", hechos)
    assert rep.confiable is False
    assert "V9" in rep.ids_desconocidos or "C7" in rep.ids_desconocidos


def test_verificador_detecta_contradiccion_todos():
    hechos = extraer_hechos(RESULTADO)
    rep = verificar("Se atienden todos los clientes.", hechos)
    assert rep.confiable is False
    assert rep.afirmaciones_no_respaldadas


def test_verificador_acepta_texto_consistente():
    hechos = extraer_hechos(RESULTADO)
    rep = verificar("V1 entrega a C1 y C2, y recarga en CH1.", hechos)
    assert rep.confiable is True


# --- explicacion por plantilla (sin LLM) -----------------------------------
def test_explicacion_plantilla_sin_cliente():
    exp = explicar(RESULTADO, cliente=None)
    assert exp.fuente == "plantilla"
    assert "V1" in exp.texto
    assert exp.verificacion.confiable is True
