"""Tests del servicio de chat del backend (sin Bedrock ni red vial).

El cliente Bedrock se fuerza a None (modo local determinista) y se usa la red
geodesica o instancias nativas, asi que no requieren credenciales ni GraphML.
Los marcados ``solver`` corren el motor real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import assist_service

_CLIENTE_REAL = assist_service._cliente_bedrock
ROOT = Path(__file__).resolve().parents[1]
TOY = json.loads((ROOT / "examples" / "toy_recharge.json").read_text(encoding="utf-8"))
SINTETICO = json.loads(
    (ROOT / "backend" / "fixtures" / "synthetic-prepare-request.json").read_text(encoding="utf-8")
)


class _Runs:
    """Doble del RunStore del servidor."""

    def __init__(self):
        self.datos = {}

    def put(self, run_id, data):
        self.datos[run_id] = data

    def get(self, run_id):
        return self.datos.get(run_id)


@pytest.fixture(autouse=True)
def _sin_bedrock(monkeypatch):
    monkeypatch.setattr(assist_service, "_cliente_bedrock", lambda *a, **k: None)
    assist_service._sesiones.clear()
    yield
    assist_service._sesiones.clear()


def test_saludo_sin_datos_no_pide_formulario():
    r = assist_service.chat({"message": "hola"})
    assert r["session_id"] and not r["necesita_archivo"] and not r["resolvio"]
    assert "archivo" in r["respuesta"]


def test_pedir_calcular_sin_datos_ofrece_adjuntar():
    r = assist_service.chat({"message": "calcula con 3 autos"})
    assert r["necesita_archivo"] is True
    assert r["config"].startswith("3 vehiculo")


@pytest.mark.solver
def test_adjuntar_archivo_retoma_el_pedido_y_publica_el_plan():
    runs = _Runs()
    r1 = assist_service.chat({"message": "calcula con la red geodesica y sin gpt"}, runs=runs)
    assert r1["necesita_archivo"]
    r2 = assist_service.chat({"session_id": r1["session_id"], "archivo": "nodos.csv",
                              "fuente": {"nodes": SINTETICO["nodes"]}}, runs=runs)
    assert r2["resolvio"] is True, r2["respuesta"]
    assert r2["run_id"] in runs.datos  # la UI lo abre por run_id
    destinos = sum(1 for n in SINTETICO["nodes"] if n["node_type"] == "visit")
    assert r2["resumen"]["destinos"] == destinos


@pytest.mark.solver
def test_instancia_nativa_y_recalculo_desde_el_plan_vigente():
    runs = _Runs()
    r1 = assist_service.chat({"message": "calcula sin gpt", "archivo": "toy.json",
                              "fuente": {"instance": TOY}}, runs=runs)
    assert r1["resolvio"] and r1["resumen"]["entregas"] == 2
    # Otra sesion (p. ej. tras reiniciar el chat) parte del plan en pantalla.
    r2 = assist_service.chat({"message": "que sea 1 auto y calcula", "run_id": r1["run_id"]},
                             runs=runs)
    assert r2["datos"] == "plan vigente" and r2["resolvio"], r2["respuesta"]
    assert r2["config"].startswith("1 vehiculo")


def test_validaciones_de_frontera():
    with pytest.raises(assist_service.AssistRequestError):
        assist_service.chat({"message": ""})
    with pytest.raises(assist_service.AssistRequestError):
        assist_service.chat({"message": "hola", "ruta_local": "C:/x"})
    with pytest.raises(assist_service.AssistRequestError):
        assist_service.chat({"fuente": {"nodes": []}})


def test_schema_tiene_parametros_y_estandar():
    s = assist_service.schema()
    assert s["parametros"]["vehiculos"]["estandar"] == 2
    assert s["parametros"]["busqueda"]["opciones"] == ["adaptive", "standard", "deterministic"]


def test_chat_reutiliza_la_conexion_bedrock_del_servidor():
    real = _CLIENTE_REAL  # el fixture reemplaza la del modulo
    boto_falso = object()

    class _Conexion:
        _epoch = 3

        def __init__(self, conectado):
            self.conectado = conectado

        def status(self):
            return {"model_id": "us.openai.gpt-5.6-luna", "region": "us-east-1",
                    "profile": "hackathon"}

        def settings(self, base):
            # Como BedrockSession sin conexion explicita: conserva la identidad del base.
            return base.model_copy()

        def _client(self, config, epoch):
            if not self.conectado:
                raise ValueError("Conecta AWS de nuevo para continuar.")
            assert epoch == 3 and config.timeout_seconds == assist_service.CHAT_TIMEOUT_S
            return boto_falso

    class _Runtime:
        def __init__(self, conectado):
            self.bedrock = _Conexion(conectado)

    cliente = real(_Runtime(True))
    assert cliente._asegurar_cliente() is boto_falso
    assert cliente.config.model_id == "us.openai.gpt-5.6-luna"
    assert real(_Runtime(False)) is None


@pytest.mark.solver
@pytest.mark.real_data
def test_caso_de_competencia_sin_archivo():
    if not (ROOT / "data" / "competition_routing_nodes.csv").is_file():
        pytest.skip("faltan los CSV locales de la hackaton en data/")
    runs = _Runs()
    r = assist_service.chat(
        {"message": "corre el caso CASE con red geodesica y sin gpt"}, runs=runs)
    assert r["datos"].startswith("caso CASE ("), r["respuesta"]
    assert r["resolvio"] and r["run_id"] in runs.datos, r["respuesta"]
    assert r["resumen"]["destinos"] == 20
