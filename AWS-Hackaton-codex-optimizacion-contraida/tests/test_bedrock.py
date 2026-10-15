"""Pruebas del cliente central Bedrock y del AsesorBedrock.

Sin red por defecto: se inyecta un cliente falso (`FakeConverse`) que imita la
superficie usada de `bedrock-runtime` (método `converse`). Un único test marcado
`@pytest.mark.bedrock` hace una llamada real y se salta si no hay credenciales.
"""
from __future__ import annotations

import os

import pytest

from evrp.asesor import AsesorBedrock, AsesorNulo
from evrp.ia import ClienteBedrock, ModeloNoDisponible, RespuestaConverse, extraer_json


# --------------------------------------------------------------- dobles
class FakeConverse:
    """Cliente falso: devuelve respuestas programadas y registra la última llamada."""

    def __init__(self, respuesta=None, excepcion=None):
        self._respuesta = respuesta
        self._excepcion = excepcion
        self.ultima_llamada = None

    def converse(self, **kwargs):
        self.ultima_llamada = kwargs
        if self._excepcion is not None:
            raise self._excepcion
        return self._respuesta


def _resp_texto(texto, in_tok=10, out_tok=5, stop="end_turn"):
    return {
        "output": {"message": {"content": [{"text": texto}]}},
        "stopReason": stop,
        "usage": {"inputTokens": in_tok, "outputTokens": out_tok},
    }


class _ErrorCliente(Exception):
    """Imita botocore.ClientError: trae .response con Error.Code."""

    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo, "Message": codigo}}


# --------------------------------------------------------------- extraer_json
def test_extraer_json_directo():
    assert extraer_json('{"a": 1}') == {"a": 1}


def test_extraer_json_con_vallas_y_prosa():
    txt = "Claro:\n```json\n{\"nombre\": \"Ana\", \"lat\": 1.5}\n```\nlisto"
    assert extraer_json(txt) == {"nombre": "Ana", "lat": 1.5}


def test_extraer_json_array():
    assert extraer_json("salida: [1, 2, 3]") == [1, 2, 3]


def test_extraer_json_invalido():
    with pytest.raises(ValueError):
        extraer_json("sin json aquí")


# --------------------------------------------------------------- conversar
def test_conversar_registra_tokens_y_latencia():
    fake = FakeConverse(_resp_texto("OK", in_tok=12, out_tok=3))
    c = ClienteBedrock(cliente=fake)
    r = c.preguntar("hola", sistema="sé breve")
    assert isinstance(r, RespuestaConverse)
    assert r.texto == "OK"
    assert r.tokens_entrada == 12 and r.tokens_salida == 3 and r.tokens_total == 15
    assert r.latencia_s >= 0.0
    # system y mensaje llegaron bien formados.
    assert fake.ultima_llamada["system"] == [{"text": "sé breve"}]
    assert fake.ultima_llamada["messages"][0]["role"] == "user"


def test_preguntar_json_valida():
    fake = FakeConverse(_resp_texto('{"nombre": "Ana", "lat": 1.0, "lon": 2.0}'))
    c = ClienteBedrock(cliente=fake)
    obj, resp = c.preguntar_json("extrae datos", sistema="eres extractor")
    assert obj == {"nombre": "Ana", "lat": 1.0, "lon": 2.0}
    assert resp.tokens_total > 0


def test_imagen_se_envia_como_bytes():
    fake = FakeConverse(_resp_texto("vista"))
    c = ClienteBedrock(cliente=fake)
    c.preguntar("describe", imagenes=[b"\x89PNG123"], formato_imagen="png")
    contenido = fake.ultima_llamada["messages"][0]["content"]
    bloque_img = next(b for b in contenido if "image" in b)
    assert bloque_img["image"]["format"] == "png"
    assert bloque_img["image"]["source"]["bytes"] == b"\x89PNG123"


def test_tool_use_fuerza_y_extrae_argumentos():
    tool = {
        "toolSpec": {
            "name": "resolver_rutas",
            "description": "Resuelve rutas E-VRP",
            "inputSchema": {"json": {"type": "object", "properties": {
                "agregar_cliente": {"type": "string"},
                "quitar_cargador": {"type": "string"},
            }}},
        }
    }
    resp_tool = {
        "output": {"message": {"content": [
            {"toolUse": {"toolUseId": "t1", "name": "resolver_rutas",
                         "input": {"agregar_cliente": "V21", "quitar_cargador": "C6"}}},
        ]}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": 20, "outputTokens": 8},
    }
    fake = FakeConverse(resp_tool)
    c = ClienteBedrock(cliente=fake)
    args, resp = c.usar_herramienta("agrega V21 y quita C6", tool)
    assert args == {"agregar_cliente": "V21", "quitar_cargador": "C6"}
    assert resp.stop_reason == "tool_use"
    # toolChoice forzó la herramienta correcta.
    assert fake.ultima_llamada["toolConfig"]["toolChoice"] == {"tool": {"name": "resolver_rutas"}}


def test_modelo_no_disponible_access_denied():
    fake = FakeConverse(excepcion=_ErrorCliente("AccessDeniedException"))
    c = ClienteBedrock(cliente=fake)
    with pytest.raises(ModeloNoDisponible) as ei:
        c.preguntar("hola")
    assert ei.value.codigo == "AccessDeniedException"


def test_modelo_no_disponible_validation():
    fake = FakeConverse(excepcion=_ErrorCliente("ValidationException"))
    c = ClienteBedrock(cliente=fake)
    with pytest.raises(ModeloNoDisponible):
        c.preguntar("hola")


# --------------------------------------------------------------- AsesorBedrock
def test_asesor_bedrock_sugerir_filtra_claves():
    # Propone una clave válida y otra prohibida; el filtro deja solo la válida.
    fake = FakeConverse(_resp_texto('{"cargadores": {"top_r": 5}, "flota": {"x": 1}}'))
    cliente = ClienteBedrock(cliente=fake)
    asesor = AsesorBedrock("us-east-1", "modelo-x", cliente=cliente)
    cfg = {"pipeline": {"cargadores": "top_r"}, "cargadores": {"top_r": 3},
           "solver": {"tiempo_limite_s": 60}}
    ajustes = asesor.sugerir_config({"clientes": 20}, cfg)
    assert ajustes == {"cargadores": {"top_r": 5}}


def test_asesor_bedrock_sugerir_tolera_fallo():
    fake = FakeConverse(excepcion=_ErrorCliente("ThrottlingException"))
    cliente = ClienteBedrock(cliente=fake)
    asesor = AsesorBedrock("us-east-1", "modelo-x", cliente=cliente)
    cfg = {"pipeline": {"cargadores": "top_r"}, "cargadores": {"top_r": 3},
           "solver": {"tiempo_limite_s": 60}}
    assert asesor.sugerir_config({}, cfg) == {}


def test_asesor_bedrock_explicar():
    fake = FakeConverse(_resp_texto("El vehículo 1 entrega V3 y recarga en C2."))
    cliente = ClienteBedrock(cliente=fake)
    asesor = AsesorBedrock("us-east-1", "modelo-x", cliente=cliente)
    txt = asesor.explicar({"rutas": {"1": ["BASE", "V3", "BASE"]}})
    assert "V3" in txt


def test_asesor_nulo_no_propone_nada():
    a = AsesorNulo()
    assert a.sugerir_config({}, {}) == {}
    assert a.explicar({}) is None


# --------------------------------------------------------------- real (opt-in)
@pytest.mark.bedrock
def test_bedrock_real_ping():
    """Llamada real a Bedrock; se salta si no hay credenciales/perfil."""
    perfil = os.environ.get("AWS_PROFILE") or "hackathon"
    modelo = os.environ.get("EVRP_BEDROCK_MODELO", "us.anthropic.claude-sonnet-4-6")
    try:
        c = ClienteBedrock(region="us-east-1", modelo=modelo, perfil=perfil)
        r = c.preguntar("Responde solo con la palabra OK.", max_tokens=10)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Bedrock no disponible ({type(exc).__name__}): {exc}")
    assert "OK" in r.texto.upper()
    assert r.tokens_total > 0
