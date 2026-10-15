"""Pruebas de evrp.ia.tuning (IDEA E: ajuste del solver estilo LLM4MIP).

Lógica pura (lista blanca, validación, perfil, prompt/tool) con dobles; sin red.
Un único test marcado `@pytest.mark.bedrock` hace una llamada real a Bedrock y se
salta si no hay credenciales.
"""
from __future__ import annotations

import os
import random

import pytest

from evrp.ia.tuning import whitelist as wl
from evrp.ia.tuning import llm as llmmod
from evrp.ia.tuning.perfil import PerfilMILP


# --------------------------------------------------------------- lista blanca
def test_validar_descarta_desconocidos_y_fuera_de_dominio():
    propuesta = {
        "mip_heuristic_effort": 0.5,      # válido
        "presolve": "on",                 # válido
        "k_vecinos": 7,                   # válido
        "cargadores_por_arco": 3,         # válido
        "mip_rel_gap": 0.1,               # fijo: NO en lista blanca
        "threads": 4,                     # fijo: NO en lista blanca
        "presolve_malo": "x",             # desconocido
        "mip_heuristic_effort_malo": 5.0, # desconocido
    }
    saneada = wl.validar_propuesta(propuesta)
    assert saneada == {"mip_heuristic_effort": 0.5, "presolve": "on",
                       "k_vecinos": 7, "cargadores_por_arco": 3}


def test_validar_rechaza_valores_fuera_de_rango():
    assert wl.validar_propuesta({"mip_heuristic_effort": 1.5}) == {}
    assert wl.validar_propuesta({"mip_heuristic_effort": -0.1}) == {}
    assert wl.validar_propuesta({"k_vecinos": -1}) == {}
    assert wl.validar_propuesta({"k_vecinos": 999}) == {}
    assert wl.validar_propuesta({"cargadores_por_arco": 0}) == {}
    assert wl.validar_propuesta({"presolve": "quizas"}) == {}


def test_validar_coerciona_entero_flotante():
    assert wl.validar_propuesta({"k_vecinos": 5.0}) == {"k_vecinos": 5}
    # un float no entero no se coerciona
    assert wl.validar_propuesta({"k_vecinos": 5.5}) == {}


def test_validar_tolera_none_y_vacio():
    assert wl.validar_propuesta(None) == {}
    assert wl.validar_propuesta({}) == {}
    # booleanos no cuentan como enteros/reales
    assert wl.validar_propuesta({"k_vecinos": True}) == {}


def test_aplicar_overrides_respeta_rutas():
    propuesta = {"mip_heuristic_effort": 0.7, "presolve": "off",
                 "k_vecinos": 4, "cargadores_por_arco": 5}
    ov = wl.aplicar_overrides({}, propuesta)
    assert ov["solver"]["cargadores_por_arco"] == 5           # ruta solver
    assert ov["solver"]["escala"]["mip_heuristic_effort"] == 0.7
    assert ov["solver"]["escala"]["presolve"] == "off"
    assert ov["solver"]["escala"]["k_vecinos"] == 4


def test_aplicar_overrides_no_muta_entrada():
    base = {"solver": {"gap_relativo": 0.0}}
    ov = wl.aplicar_overrides(base, {"k_vecinos": 3})
    assert base == {"solver": {"gap_relativo": 0.0}}          # intacto
    assert ov["solver"]["gap_relativo"] == 0.0                # preservado
    assert ov["solver"]["escala"]["k_vecinos"] == 3


def test_muestra_aleatoria_siempre_valida_y_reproducible():
    rng = random.Random(42)
    for _ in range(200):
        m = wl.muestra_aleatoria(rng)
        assert set(m) == set(wl.LISTA_BLANCA)
        assert wl.validar_propuesta(m) == m                   # todo dentro de dominio
    # reproducible con la misma semilla
    assert wl.muestra_aleatoria(random.Random(1)) == wl.muestra_aleatoria(random.Random(1))


# --------------------------------------------------------------- perfil
def _perfil_demo(**kw):
    base = dict(columnas=100, filas=200, binarias=80, enteras=1, continuas=19,
                no_ceros=600, densidad=0.03, coef_abs_min=0.01, coef_abs_max=25.0,
                rango_coef_log10=3.4, clientes=20, vehiculos=2, cargadores_por_arco=3)
    base.update(kw)
    return PerfilMILP(**base)


def test_perfil_compacto_incluye_campos_clave():
    s = _perfil_demo(base_gap=0.07, base_tiempo_s=11.7).compacto()
    for frag in ("cols=100", "filas=200", "binarias=80", "clientes=20",
                 "vehiculos=2", "carg/arco=3", "base_gap=0.0700"):
        assert frag in s


def test_perfil_compacto_tolera_nd():
    s = _perfil_demo().compacto()
    assert "base_gap=n/d" in s and "base_tiempo=n/d" in s


# --------------------------------------------------------------- llm (dobles)
class _FakeCliente:
    """Imita ClienteBedrock.usar_herramienta."""

    def __init__(self, args, excepcion=None):
        self._args = args
        self._exc = excepcion
        self.modelo = "fake"

    def usar_herramienta(self, texto, herramienta, **kw):
        if self._exc:
            raise self._exc
        from evrp.ia.bedrock import RespuestaConverse
        resp = RespuestaConverse(texto="", tokens_entrada=120, tokens_salida=30,
                                 latencia_s=1.5)
        return self._args, resp


def test_tool_spec_cubre_toda_la_lista_blanca():
    spec = llmmod._tool_spec()
    props = spec["toolSpec"]["inputSchema"]["json"]["properties"]
    assert set(props) == set(wl.LISTA_BLANCA)
    assert props["presolve"]["enum"] == ["on", "off", "choose"]
    assert props["mip_heuristic_effort"]["type"] == "number"
    assert props["k_vecinos"]["type"] == "integer"


def test_proponer_sanea_respuesta_del_modelo():
    # El modelo devuelve algo mezclado: válido + inválido + prohibido.
    args = {"presolve": "on", "k_vecinos": 6, "threads": 8, "mip_rel_gap": 0.2}
    pr = llmmod.proponer(_FakeCliente(args), _perfil_demo(), modelo="m")
    assert pr.propuesta == {"presolve": "on", "k_vecinos": 6}
    assert pr.tokens_total == 150
    assert pr.error is None


def test_proponer_degrada_a_vacio_ante_error():
    pr = llmmod.proponer(_FakeCliente(None, excepcion=RuntimeError("boom")),
                         _perfil_demo(), modelo="m")
    assert pr.propuesta == {}
    assert pr.error and "boom" in pr.error
    assert pr.tokens_total == 0


# --------------------------------------------------------------- bedrock real
@pytest.mark.bedrock
def test_proponer_real_bedrock():
    if not (os.environ.get("AWS_PROFILE") or os.path.exists(os.path.expanduser("~/.aws/credentials"))):
        pytest.skip("sin credenciales AWS")
    from evrp.ia.bedrock import ClienteBedrock
    cliente = ClienteBedrock(region="us-east-1", perfil="hackathon")
    pr = llmmod.proponer(cliente, _perfil_demo(base_gap=0.07, base_tiempo_s=11.7),
                         modelo="us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert pr.error is None
    assert wl.validar_propuesta(pr.propuesta) == pr.propuesta
    assert pr.tokens_total > 0
