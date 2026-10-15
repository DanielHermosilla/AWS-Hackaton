"""Pruebas de la explicación de rutas (Idea C).

Sin red por defecto: se usa la plantilla determinista y dobles del cliente Bedrock
(`.preguntar` programado). Un único test `@pytest.mark.bedrock` hace una llamada real
y se salta si no hay credenciales.
"""
from __future__ import annotations

import os

import pytest

from evrp.ia.explicacion import (
    explicar,
    explicar_plantilla,
    extraer_hechos,
    verificar_texto,
)
from evrp.ia.explicacion.hechos import resumen_para_llm


# --------------------------------------------------------------- resultado de ejemplo
def _resultado():
    return {
        "rutas": {"1": ["BASE", "V1", "V2", "C9", "V3", "BASE"], "2": ["BASE", "BASE"]},
        "kpis": {
            "entregas": 3, "clientes": 4, "no_atendidos": ["V4"],
            "energia_total_kwh": 11.2203, "energia_efectiva_kwh": 11.2203,
            "km_total": 71.925,
            "por_vehiculo": {
                "1": {"tipo": "leaf2013", "energia_kwh": 11.2203, "km": 71.925,
                      "bateria_min_kwh": 1.6425, "bateria_final_kwh": 12.7372,
                      "recargas": 1, "vuelve_a_base": True},
                "2": {"tipo": "leaf2013", "energia_kwh": 0.0, "km": 0.0,
                      "bateria_min_kwh": 9.6, "bateria_final_kwh": 9.6,
                      "recargas": 0, "vuelve_a_base": True},
            },
        },
        "detalle": {},
    }


# --------------------------------------------------------------- dobles
class FakeCliente:
    """Doble de ClienteBedrock: `.preguntar` devuelve textos programados en orden."""

    def __init__(self, textos, modelo="fake-model"):
        self._textos = list(textos)
        self.modelo = modelo
        self.llamadas = []

    def preguntar(self, texto, *, sistema=None, max_tokens=512, **kw):
        self.llamadas.append({"texto": texto, "sistema": sistema})
        salida = self._textos.pop(0)

        class _Resp:
            pass

        r = _Resp()
        r.texto = salida
        r.tokens_entrada = 100
        r.tokens_salida = 50
        r.tokens_total = 150
        r.latencia_s = 0.5
        return r


# --------------------------------------------------------------- hechos
def test_extraer_hechos_incluye_kpis_y_nodos():
    hechos = extraer_hechos(_resultado())
    campos = {h.campo for h in hechos}
    assert "kpis.entregas" in campos
    assert "kpis.energia_total_kwh" in campos
    valores_num = {h.valor for h in hechos if isinstance(h.valor, (int, float))}
    assert 11.2203 in valores_num
    # IDs de nodos presentes como hechos string.
    valores_id = {h.valor for h in hechos if isinstance(h.valor, str)}
    assert {"BASE", "V1", "C9", "V4"} <= valores_id


def test_resumen_para_llm_omite_vehiculos_sin_uso():
    res = resumen_para_llm(_resultado())
    assert "1" in res["vehiculos"]
    assert "2" not in res["vehiculos"]  # km 0 → no aparece
    assert res["vehiculos"]["1"]["cargadores_usados"] == ["C9"]


# --------------------------------------------------------------- verificador
def test_verificador_acepta_cifras_reales_con_redondeo():
    hechos = extraer_hechos(_resultado())
    # "11.22" es redondeo de 11.2203; "72 km" ~ 71.925 (tolerancia); V1/C9 válidos.
    texto = "Se atendieron 3 de 4 clientes con 11.22 kWh. El vehículo 1 pasa por V1 y C9."
    assert verificar_texto(texto, hechos).ok


def test_verificador_rechaza_numero_inventado():
    hechos = extraer_hechos(_resultado())
    ver = verificar_texto("Se gastaron 999.9 kWh.", hechos)
    assert not ver.ok
    assert any("999.9" in e for e in ver.errores)


def test_verificador_rechaza_id_inventado():
    hechos = extraer_hechos(_resultado())
    ver = verificar_texto("El vehículo visita V99.", hechos)
    assert not ver.ok
    assert any("V99" in e for e in ver.errores)


# --------------------------------------------------------------- plantilla
def test_plantilla_operador_pasa_verificador():
    res = _resultado()
    texto = explicar_plantilla(res, "operador")
    assert verificar_texto(texto, extraer_hechos(res)).ok
    assert "V4" in texto  # menciona el pendiente


def test_plantilla_gerencia_breve_y_fiel():
    res = _resultado()
    texto = explicar_plantilla(res, "gerencia")
    assert verificar_texto(texto, extraer_hechos(res)).ok
    assert "pendiente" in texto.lower()


# --------------------------------------------------------------- explicar (orquestador)
def test_explicar_sin_cliente_usa_plantilla():
    out = explicar(_resultado(), "operador")
    assert out["uso"]["origen"] == "plantilla"
    assert out["uso"]["verificado"] is True
    assert out["hechos_citados"]
    assert verificar_texto(out["texto"], extraer_hechos(_resultado())).ok


def test_explicar_llm_valido_al_primer_intento():
    texto_bueno = ("Se atendieron 3 de 4 clientes con 11.22 kWh en 71.9 km. "
                   "El vehículo 1 recarga en C9 para no agotar la batería "
                   "(mínimo 1.64 kWh). Queda pendiente V4.")
    cli = FakeCliente([texto_bueno])
    out = explicar(_resultado(), "operador", cliente=cli)
    assert out["uso"]["origen"] == "llm"
    assert out["uso"]["intentos"] == 1
    assert out["uso"]["tokens_total"] == 150


def test_explicar_llm_reintenta_y_corrige():
    texto_malo = "Se gastaron 500.0 kWh y se visitó V77."
    texto_bueno = "Se atendieron 3 de 4 clientes con 11.22 kWh. Pendiente V4."
    cli = FakeCliente([texto_malo, texto_bueno])
    out = explicar(_resultado(), "operador", cliente=cli)
    assert out["uso"]["origen"] == "llm"
    assert out["uso"]["intentos"] == 2
    assert len(cli.llamadas) == 2
    # El segundo prompt incluye la lista de errores del verificador.
    assert "no verificables" in cli.llamadas[1]["texto"] or "999" in cli.llamadas[1]["texto"] \
        or "500" in cli.llamadas[1]["texto"]


def test_explicar_llm_falla_dos_veces_cae_a_plantilla():
    malo1 = "Se gastaron 500.0 kWh."
    malo2 = "Ahora fueron 600.0 kWh."
    cli = FakeCliente([malo1, malo2])
    out = explicar(_resultado(), "operador", cliente=cli)
    assert out["uso"]["origen"] == "plantilla"
    assert out["uso"]["verificado"] is True  # la plantilla siempre es fiel
    assert out["advertencias"]
    assert verificar_texto(out["texto"], extraer_hechos(_resultado())).ok


def test_explicar_llm_excepcion_degrada_a_plantilla():
    class ClienteRoto:
        modelo = "roto"

        def preguntar(self, *a, **k):
            raise RuntimeError("sin red")

    out = explicar(_resultado(), "gerencia", cliente=ClienteRoto())
    assert out["uso"]["origen"] == "plantilla"
    assert out["advertencias"]


def test_explicar_acepta_dataclass_resultado():
    import evrp

    r = evrp.Resultado(**{
        "rutas": _resultado()["rutas"],
        "rutas_indices": {},
        "kpis": _resultado()["kpis"],
        "detalle": {},
    })
    out = explicar(r, "operador")
    assert out["texto"]
    assert out["uso"]["verificado"] is True


# --------------------------------------------------------------- bedrock real
@pytest.mark.bedrock
def test_explicar_bedrock_real_es_fiel():
    """Llamada real: el texto del LLM debe pasar el verificador (o degradar a plantilla)."""
    from evrp.ia import ClienteBedrock

    perfil = os.environ.get("AWS_PROFILE")
    cli = ClienteBedrock(region="us-east-1",
                         modelo="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                         perfil=perfil)
    out = explicar(_resultado(), "operador", cliente=cli)
    # Garantía dura: el texto devuelto SIEMPRE pasa el verificador.
    assert verificar_texto(out["texto"], extraer_hechos(_resultado())).ok
    assert out["uso"]["origen"] in {"llm", "plantilla"}
    assert out["uso"]["verificado"] is True
