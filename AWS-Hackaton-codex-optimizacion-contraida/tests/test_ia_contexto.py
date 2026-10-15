"""Pruebas de contexto→parámetros (Idea D).

Sin red por defecto: extractor de reglas y dobles del cliente Bedrock
(`.usar_herramienta` programado). Un único test `@pytest.mark.bedrock` real.
"""
from __future__ import annotations

import os

import pytest

from evrp.ia.contexto import (
    VARIABLES_PERMITIDAS,
    ajustar,
    extraer_variables_reglas,
    factor_desde_variables,
)
from evrp.ia.contexto.ajustador import FACTOR_MAX, FACTOR_MIN, validar_variables


# Calibración de ejemplo (coherente con la real: frío sube consumo).
CAL = {"factores": {"<0": 1.8, "0-10": 1.28, "10-20": 1.04, "20-30": 1.0, ">30": 1.1}}


# --------------------------------------------------------------- lista blanca
def test_validar_variables_descarta_fuera_de_rango():
    v = validar_variables({"temperatura_c": 200, "trafico": "altisimo",
                           "precipitacion": "lluvia", "carga_frac": 0.5, "ruido": 1})
    assert "temperatura_c" not in v   # 200 fuera de rango
    assert "trafico" not in v         # no está en el enum
    assert v["precipitacion"] == "lluvia"
    assert v["carga_frac"] == 0.5
    assert "ruido" not in v           # clave no permitida


def test_factor_frio_mayor_que_templado():
    f_frio = factor_desde_variables({"temperatura_c": -5}, CAL)["ajustes"]["consumo_factor"]
    f_tpl = factor_desde_variables({"temperatura_c": 25}, CAL)["ajustes"]["consumo_factor"]
    assert f_frio > f_tpl
    assert f_tpl == 1.0


def test_factor_acotado():
    # Nieve + frío extremo + tráfico alto + carga plena no debe exceder el tope.
    f = factor_desde_variables(
        {"temperatura_c": -20, "precipitacion": "nieve", "trafico": "alto", "carga_frac": 1.0},
        CAL)["ajustes"]["consumo_factor"]
    assert FACTOR_MIN <= f <= FACTOR_MAX


def test_reserva_extra_en_nieve():
    aj = factor_desde_variables({"temperatura_c": -5, "precipitacion": "nieve"}, CAL)["ajustes"]
    assert aj.get("reserva_kwh") == 1.5


def test_factor_recargos_multiplicativos():
    base = factor_desde_variables({"temperatura_c": 25}, CAL)["ajustes"]["consumo_factor"]
    con_lluvia = factor_desde_variables(
        {"temperatura_c": 25, "precipitacion": "lluvia"}, CAL)["ajustes"]["consumo_factor"]
    assert con_lluvia > base


# --------------------------------------------------------------- extractor de reglas
def test_reglas_detectan_nieve_frio_trafico_carga():
    v = extraer_variables_reglas("Hoy nieva, hace -5 grados, mucho tráfico y el camión va lleno.")
    assert v["temperatura_c"] == -5.0
    assert v["precipitacion"] == "nieve"
    assert v["trafico"] == "alto"
    assert v["carga_frac"] == 1.0


def test_reglas_temperatura_cualitativa():
    v = extraer_variables_reglas("Día caluroso de verano.")
    assert v["temperatura_c"] == 33.0


def test_reglas_texto_vacio():
    assert extraer_variables_reglas("") == {}


# --------------------------------------------------------------- ajustar sin cliente
def test_ajustar_sin_cliente_usa_reglas():
    out = ajustar("Hace -5 grados con nieve.", calibracion=CAL)
    assert out["uso"]["origen"] == "reglas"
    assert out["ajustes"]["consumo_factor"] > 1.0
    assert out["variables"]["temperatura_c"] == -5.0
    assert out["supuestos"]  # declara lo que asumió


def test_ajustar_sin_variables_factor_neutro():
    out = ajustar("Operación normal, sin novedades.", calibracion=CAL)
    assert out["ajustes"]["consumo_factor"] == 1.0


# --------------------------------------------------------------- ajustar con doble LLM
class FakeClienteTool:
    """Doble: `usar_herramienta` devuelve variables programadas."""

    def __init__(self, variables, modelo="fake"):
        self._variables = variables
        self.modelo = modelo
        self.llamadas = []

    def usar_herramienta(self, texto, herramienta, *, sistema=None, max_tokens=300, **kw):
        self.llamadas.append(texto)

        class _Resp:
            tokens_entrada = 200
            tokens_salida = 20
            tokens_total = 220
            latencia_s = 0.4

        return dict(self._variables), _Resp()


def test_ajustar_con_llm_extrae_y_calcula_factor():
    # El LLM "extrae" variables; el factor lo calcula nuestra función (no el LLM).
    cli = FakeClienteTool({"temperatura_c": -8, "precipitacion": "nieve", "trafico": "alto"})
    out = ajustar("Tormenta de nieve, calles congeladas y congestión.", calibracion=CAL,
                  cliente=cli)
    assert out["uso"]["origen"] == "llm"
    assert out["uso"]["tokens_total"] == 220
    assert out["ajustes"]["consumo_factor"] > 1.3
    assert out["ajustes"].get("reserva_kwh") == 1.5
    assert out["variables"]["temperatura_c"] == -8


def test_ajustar_llm_ignora_variables_fuera_de_lista_blanca():
    cli = FakeClienteTool({"temperatura_c": 25, "consumo_factor": 5.0, "inventado": "x"})
    out = ajustar("Texto cualquiera.", calibracion=CAL, cliente=cli)
    # Aunque el LLM "sugiera" consumo_factor=5, se ignora: el nuestro manda.
    assert out["ajustes"]["consumo_factor"] == 1.0


def test_ajustar_llm_excepcion_degrada_a_reglas():
    class ClienteRoto:
        modelo = "roto"

        def usar_herramienta(self, *a, **k):
            raise RuntimeError("sin red")

    out = ajustar("Hace -5 grados con nieve.", calibracion=CAL, cliente=ClienteRoto())
    assert out["uso"]["origen"] == "reglas"
    assert out["ajustes"]["consumo_factor"] > 1.0


# --------------------------------------------------------------- bedrock real
@pytest.mark.bedrock
def test_ajustar_bedrock_real_extrae_variables():
    """Llamada real: el LLM extrae variables; el factor lo calcula la fórmula."""
    from evrp.ia import ClienteBedrock

    perfil = os.environ.get("AWS_PROFILE")
    cli = ClienteBedrock(region="us-east-1",
                         modelo="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                         perfil=perfil)
    out = ajustar("Está nevando, la temperatura es de -6 grados y hay mucho tráfico.",
                  calibracion=CAL, cliente=cli)
    # Degrada a reglas si el modelo no está disponible; en ambos casos hay factor válido.
    assert FACTOR_MIN <= out["ajustes"]["consumo_factor"] <= FACTOR_MAX
    if out["uso"]["origen"] == "llm":
        assert out["variables"].get("temperatura_c") is not None
        assert out["ajustes"]["consumo_factor"] > 1.0  # frío + nieve suben el consumo
