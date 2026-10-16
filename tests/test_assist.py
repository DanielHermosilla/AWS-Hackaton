"""Tests del paquete assist sin red (dobles de Bedrock y del solver).

No requieren boto3 ni credenciales: validan la lista blanca, la sesion con
snapshot inicial, la extraccion de hechos, el verificador anti-alucinacion y la
explicacion por plantilla.
"""

from __future__ import annotations

import pytest

from ev_routing.assist.explainer import explicar
from ev_routing.assist.facts import extraer_hechos
from ev_routing.assist.tools import ErrorParametro, parametros_schema, validar_parametro
from ev_routing.assist.verifier import verificar


# --- lista blanca ----------------------------------------------------------
def test_parametro_desconocido_se_rechaza():
    with pytest.raises(ErrorParametro):
        validar_parametro("inexistente", 1)


def test_flota_maxima_es_veinte():
    spec, valor = validar_parametro("vehiculos", 20)
    assert valor == 20
    assert spec.importante is True
    with pytest.raises(ErrorParametro):
        validar_parametro("vehiculos", 21)


def test_valor_fuera_de_rango_se_rechaza():
    with pytest.raises(ErrorParametro):
        validar_parametro("soc_inicial", 1.5)


# --- esquema para el frontend ---------------------------------------------
def test_schema_expone_rangos_y_flota_veinte():
    schema = parametros_schema()
    assert schema["schema_version"]
    params = schema["parametros"]
    assert set(params) >= {"vehiculos", "soc_inicial", "tiempo_limite_s"}
    flota = params["vehiculos"]
    assert flota["tipo"] == "int"
    assert flota["min"] == 1 and flota["max"] == 20
    assert flota["importante"] is True
    assert flota["destino"] == "vehicle_count"


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


# --- confirmacion de cambios importantes (estado en la sesion) -------------
class _ClienteFlota:
    """Cliente Bedrock falso: siempre pide cambiar la flota a 3."""

    def conversar(self, mensajes, *, sistema, tool_config=None):
        return {"output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t", "name": "cambiar_parametro",
                         "input": {"clave": "vehiculos", "valor": 3}}}]}}}


def test_confirmacion_pendiente_vive_en_la_sesion():
    """Un cambio importante queda pendiente en la Sesion y se confirma aunque el
    segundo turno use una instancia de Asistente distinta (backend sin estado).

    'aplicar' solo valida y registra el override; no materializa la instancia,
    asi que el test no necesita un ProblemInstance real.
    """
    from ev_routing.assist import Asistente, Sesion

    ses = Sesion(instancia_base=object(), config_base=object())
    a1 = Asistente(ses, _ClienteFlota())
    r1 = a1.turno("usa 3 vehiculos")
    assert r1.acciones and r1.acciones[0].confirmacion_requerida is True
    assert ses.confirmacion_pendiente == ("vehiculos", 3)

    # Segundo turno con OTRA instancia de asistente sobre la MISMA sesion.
    a2 = Asistente(ses, _ClienteFlota())
    r2 = a2.turno("si, confirmo")
    assert "Aplicado" in r2.respuesta
    assert ses.confirmacion_pendiente is None
    assert ses._overrides.get("vehiculos") == 3


# --- interprete local (sin LLM) ----------------------------------------------
@pytest.mark.parametrize("texto, esperado", [
    ("dale con 5 autos, 20 segundos", {"vehiculos": 5, "tiempo_limite_s": 20}),
    ("4 AUTOS", {"vehiculos": 4}),
    ("salimos al 70%", {"soc_inicial": 0.7}),
    ("calcula sin GPT", {"busqueda": "standard"}),
    ("usa la red geodésica", {"red": "haversine"}),
    ("Hola", {}),
])
def test_interprete_extrae_ajustes(texto, esperado):
    from ev_routing.assist import interpretar

    assert interpretar(texto).ajustes == esperado


def test_interprete_intenciones():
    from ev_routing.assist import interpretar

    assert interpretar("Hola, qué tal").saludo and not interpretar("Hola").calcular
    r = interpretar("resuelve con 4 autos y las configuraciones estandar")
    assert r.calcular and r.reiniciar and r.ajustes == {"vehiculos": 4}
    assert interpretar("explícame las rutas").explicar


# --- turno local: el pedido queda pendiente hasta que llegan los datos --------
def test_turno_local_saludo_no_pide_formularios():
    from ev_routing.assist import Asistente, Sesion

    r = Asistente(Sesion()).turno("hola")
    assert r.modo == "local" and not r.necesita_datos and not r.resolvio
    assert "archivo" in r.respuesta


def test_turno_local_calcular_sin_datos_y_luego_con_datos():
    from ev_routing.assist import Asistente, Sesion

    ses = Sesion()
    r1 = Asistente(ses, confirmar_importantes=False).turno("calcula con 3 autos")
    assert r1.necesita_datos and ses.pendiente_calcular
    assert ses.overrides == {"vehiculos": 3}

    recibido = {}

    def resolutor(cfg):
        recibido.update(cfg)
        return RESULTADO

    ses.cargar_datos(resolutor, descripcion="nodos.csv (2 destinos)")
    r2 = Asistente(ses, confirmar_importantes=False).turno(
        "[Adjunte nodos.csv.] Calcula ahora con lo que te pedi.")
    assert r2.resolvio and not ses.pendiente_calcular
    assert recibido["vehiculos"] == 3 and recibido["soc_inicial"] == 0.6  # estandar
    assert "2 entregas" in r2.respuesta


# --- turno con LLM (cliente falso): herramientas e historial en la sesion ----
class _ClienteGuion:
    """Turno 1: cambia flota y resuelve; luego responde. Registra lo enviado."""

    def __init__(self):
        self.llamadas = []

    def conversar(self, mensajes, *, sistema, tool_config=None):
        self.llamadas.append((len(mensajes), sistema))
        ultimo = mensajes[-1]["content"]
        if any("toolResult" in b for b in ultimo):
            return {"output": {"message": {"role": "assistant", "content": [
                {"text": "Listo: 2 entregas con 3 vehiculos."}]}}}
        return {"output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "a", "name": "cambiar_parametro",
                         "input": {"clave": "vehiculos", "valor": 3}}},
            {"toolUse": {"toolUseId": "b", "name": "resolver", "input": {}}}]}}}


def test_turno_llm_aplica_y_resuelve_con_historial_en_sesion():
    from ev_routing.assist import Asistente, Sesion

    ses = Sesion(resolutor=lambda cfg: RESULTADO, descripcion_datos="nodos.csv")
    cliente = _ClienteGuion()
    r = Asistente(ses, cliente, confirmar_importantes=False).turno("calcula con 3 autos")
    assert r.resolvio and r.modo == "llm"
    assert ses.overrides == {"vehiculos": 3}
    assert "Datos: nodos.csv" in cliente.llamadas[0][1]  # estado en el prompt
    n = len(ses.mensajes)
    Asistente(ses, cliente, confirmar_importantes=False).turno("gracias")
    assert len(ses.mensajes) > n  # otra instancia continua el mismo historial


def test_turno_llm_cae_a_local_si_bedrock_falla():
    from ev_routing.assist import Asistente, ErrorBedrock, Sesion

    class _Roto:
        def conversar(self, *a, **k):
            raise ErrorBedrock("sin red")

    ses = Sesion()
    r = Asistente(ses, _Roto()).turno("hola")
    assert r.modo == "local" and r.respuesta
    assert ses.mensajes == []  # no queda historial a medias


# --- caso de la hackaton como fuente de datos (sin archivo) -------------------
@pytest.mark.parametrize("texto, caso", [
    ("Puedes correr sobre los datos de competencia?", {"dataset": "competition"}),
    ("usa el caso de evaluación", {"dataset": "evaluation"}),
    ("simula 50 clientes y 10 cargadores con la hackatón",
     {"dataset": "competition", "clientes": 50, "cargadores": 10}),
    ("que sean 3 autos", None),
])
def test_interprete_detecta_caso(texto, caso):
    from ev_routing.assist import interpretar

    assert interpretar(texto).caso == caso


def test_turno_local_usa_caso_y_calcula_sin_pedir_archivo():
    from ev_routing.assist import Asistente, Sesion

    ses = Sesion()
    pedidos = []

    def cargar_caso(entrada):
        pedidos.append(entrada)
        ses.cargar_datos(lambda cfg: RESULTADO, descripcion="caso de la hackaton · competencia")
        return "caso de la hackaton · competencia"

    ses.cargar_caso = cargar_caso
    r = Asistente(ses, confirmar_importantes=False).turno(
        "Puedes correr sobre los datos de competencia?")
    assert pedidos == [{"dataset": "competition"}]
    assert r.resolvio and not r.necesita_datos
    assert "competencia" in r.respuesta and "2 entregas" in r.respuesta


def test_herramienta_caso_solo_si_esta_disponible():
    from ev_routing.assist.tools import tool_specs

    nombres = lambda specs: {t["toolSpec"]["name"] for t in specs["tools"]}  # noqa: E731
    assert "usar_caso_hackaton" not in nombres(tool_specs())
    assert "usar_caso_hackaton" in nombres(tool_specs(casos=True))
