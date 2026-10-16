"""Servicio del asistente conversacional sobre el pipeline web (API 3.0).

Capa fina entre el transporte HTTP (``local_server``) y ``ev_routing.assist``.
El chat gestiona TODO el envio de datos al motor: con los nodos de la sesion y
la configuracion conversada arma /prepare (calles del servidor o geodesica) y
/solve, y publica el resultado en el mismo ``RunStore`` que usa la UI, de modo
que la pagina Plan lo dibuja por ``run_id``.

Fuentes de datos de una sesion:
- un archivo adjuntado en el chat (CSV de nodos, ProblemInstance nativa o
  ejecucion exportada), o
- el plan vigente de la UI (``run_id``): se recuperan los nodos y supuestos
  originales de la preparacion para poder recalcular con otros parametros.

No modifica el nucleo del solver ni las rutas /prepare y /solve: las reutiliza.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from . import service

API_ASSIST = "assist-1.0"
_MAX_SESIONES = 8
_TIPOS_NODO = {"base", "visit", "charger"}
_CAMPOS_PAYLOAD = {"session_id", "message", "run_id", "fuente", "archivo"}

_sesiones: OrderedDict[str, _SesionWeb] = OrderedDict()
_lock = threading.Lock()
_cliente_cache: list[Any] = []  # cliente Bedrock reutilizable (si se pudo crear)


class AssistRequestError(service.SolveRequestError):
    """Error de validacion accionable en la frontera del chat."""


@dataclass
class _SesionWeb:
    sesion: Any
    run_id: str | None = None
    ultima: dict | None = None  # ultima respuesta /solve publicada


@contextmanager
def _ocupar(lock: threading.Lock | None):
    """Comparte el candado del solver con /solve sin bloquear el chat."""
    if lock is None:
        yield
        return
    if not lock.acquire(blocking=False):
        raise service.ProviderError(
            "Hay un calculo en curso; espera a que termine.", "solver_busy", 409
        )
    try:
        yield
    finally:
        lock.release()


# --- utilidades de datos ------------------------------------------------------
def _nodos_csv(nodos: list[dict]) -> list[dict]:
    """Nodos nativos -> filas con el formato CSV de /prepare."""
    filas = []
    for nodo in nodos or []:
        if not isinstance(nodo, dict) or nodo.get("node_type") not in _TIPOS_NODO:
            continue
        fila = {k: v for k, v in nodo.items() if k in service.CSV_FIELDS and v is not None}
        conectores = fila.get("connector_types")
        if isinstance(conectores, list):
            fila["connector_types"] = ";".join(conectores)
        filas.append(fila)
    return filas


def _resumen_nodos(nodos: list[dict]) -> str:
    destinos = sum(1 for n in nodos if n.get("node_type") == "visit")
    cargadores = sum(1 for n in nodos if n.get("node_type") == "charger")
    return f"{destinos} destinos, {cargadores} cargadores"


def _config_desde_fleet(fleet: dict) -> dict[str, Any]:
    pares = (("vehiculos", "num_vehicles"), ("soc_inicial", "initial_soc"),
             ("capacidad_kwh", "battery_capacity_kwh"), ("reserva_kwh", "reserve_kwh"),
             ("consumo_kwh_km", "consumption_kwh_km"))
    return {clave: fleet[web] for clave, web in pares if fleet.get(web) is not None}


def _hacer_resolutor(web: _SesionWeb, fuente: dict, *, runtime, runs, lock):
    """Resolutor de la sesion: (config efectiva) -> resultado nativo del motor."""
    from ev_routing.assist import PARAMETROS

    opciones = {"runtime": runtime} if runtime is not None else {}

    def resolver(cfg: dict[str, Any]) -> dict:
        with _ocupar(lock):
            if "nodes" in fuente:
                fleet = {
                    "num_vehicles": cfg["vehiculos"],
                    "battery_capacity_kwh": cfg["capacidad_kwh"],
                    "reserve_kwh": cfg["reserva_kwh"],
                    "initial_soc": cfg["soc_inicial"],
                    "consumption_kwh_km": cfg["consumo_kwh_km"],
                }
                if fuente.get("connectors"):
                    fleet["vehicle_connector_types"] = list(fuente["connectors"])
                pedido = {"api_version": service.API_VERSION, "nodes": fuente["nodes"],
                          "network_mode": cfg["red"], "fleet": fleet}
                if fuente.get("operations"):
                    pedido["operations"] = copy.deepcopy(fuente["operations"])
                extra = copy.deepcopy(fuente.get("extra") or {})
                if cfg["red"] != "road":
                    extra.pop("energy_profile_id", None)  # el historico es por calle
                pedido.update(extra)
                preparada = service.prepare(pedido, **opciones)
                instancia = preparada["instance"]
                preparada_id = preparada.get("prepared_instance_id")
            else:
                instancia = copy.deepcopy(fuente["instance"])
                instancia["parameters"] = {
                    **(instancia.get("parameters") or {}),
                    **{s.destino: cfg[k] for k, s in PARAMETROS.items()
                       if s.seccion == "parametros"},
                }
                preparada_id = None
            pedido_solve = {"api_version": service.API_VERSION, "instance": instancia,
                            "solver": {"time_limit_seconds": cfg["tiempo_limite_s"],
                                       "search_policy": cfg["busqueda"]}}
            if preparada_id:
                pedido_solve["prepared_instance_id"] = preparada_id
            respuesta = service.solve(pedido_solve, **opciones)
        run_id = respuesta["result"]["run_id"]
        if runs is not None:
            runs.put(run_id, service.json_bytes(respuesta))
        web.run_id, web.ultima = run_id, respuesta
        return respuesta["result"]["raw"]["result"]

    return resolver


def _cargar_archivo(web: _SesionWeb, fuente: Any, nombre: str, **entorno) -> None:
    """Carga en la sesion los datos de un archivo adjuntado en el chat."""
    from ev_routing.assist import PARAMETROS
    from ev_routing.assist.session import config_desde_instancia

    if not isinstance(fuente, dict):
        raise AssistRequestError("'fuente' debe ser un objeto con 'nodes' o 'instance'.")
    if isinstance(fuente.get("instance"), dict) and not fuente.get("nodes"):
        modelo = service._native_instance(fuente["instance"])
        datos = {"instance": fuente["instance"]}
        config = config_desde_instancia(modelo)
        descripcion = f"{nombre} ({len(modelo.customer_ids)} destinos, instancia nativa)"
        no_aplicables = frozenset(k for k, s in PARAMETROS.items() if s.seccion == "preparacion")
    else:
        nodos = fuente.get("nodes")
        if not isinstance(nodos, list) or not nodos:
            raise AssistRequestError("El archivo no contiene nodos.")
        if len(nodos) > service.MAX_PREPARE_NODES:
            raise AssistRequestError(
                f"El chat admite hasta {service.MAX_PREPARE_NODES} nodos por archivo."
            )
        preparacion = fuente.get("prepare") if isinstance(fuente.get("prepare"), dict) else {}
        fleet = preparacion.get("fleet") or {}
        config = _config_desde_fleet(fleet)
        if preparacion.get("network_mode") in ("road", "haversine"):
            config["red"] = preparacion["network_mode"]
        datos = {"nodes": nodos, "operations": preparacion.get("operations"),
                 "connectors": fleet.get("vehicle_connector_types")}
        descripcion = f"{nombre} ({_resumen_nodos(nodos)})"
        no_aplicables = frozenset()
    web.sesion.cargar_datos(
        _hacer_resolutor(web, datos, **entorno), descripcion=descripcion,
        config=config, no_aplicables=no_aplicables,
    )
    web.run_id = web.ultima = None


def _cargar_caso(web: _SesionWeb, entrada: dict, *, runtime, runs, lock) -> str:
    """Carga el caso oficial de la hackaton como datos de la sesion.

    Mismo origen que la UI (``scenarios.hackathon_scenario`` / ``simulate_hackathon``)
    y, si esta disponible, el historico electrico de ejemplo (eVED) para la
    energia por calle. Devuelve la descripcion de los datos cargados.
    """
    from .scenarios import hackathon_scenario, simulate_hackathon

    if not isinstance(entrada, dict):
        raise AssistRequestError("Indica el dataset del caso de la hackaton.")
    dataset = entrada.get("dataset") or "competition"
    escenario = hackathon_scenario(dataset)
    base = escenario["nodes"]
    destinos = sum(1 for n in base if n.get("node_type") == "visit")
    cargadores = sum(1 for n in base if n.get("node_type") == "charger")
    simulacion = None
    if entrada.get("clientes") is not None or entrada.get("cargadores") is not None:
        simulacion = {
            "customers": entrada.get("clientes") or destinos,
            "chargers": cargadores if entrada.get("cargadores") is None else entrada["cargadores"],
            "seed": entrada.get("semilla") or 0,
        }
        if runtime is None:
            raise AssistRequestError("La simulacion de ubicaciones requiere el servidor web.")
        escenario = simulate_hackathon(escenario, simulacion, runtime)
    perfil = None
    historiales = getattr(runtime, "histories", None)
    if historiales is not None:
        try:
            perfil = historiales.load_example()
            if perfil.get("status") != "ready":
                perfil = None
        except Exception:  # sin historico de ejemplo: energia por consumo supuesto
            perfil = None
    extra: dict[str, Any] = {"scenario": escenario["scenario"]}
    if perfil is not None:
        extra["energy_profile_id"] = perfil["profile_id"]
    nodos = escenario["nodes"]
    etiqueta = "evaluacion" if dataset == "evaluation" else "competencia"
    descripcion = f"caso de la hackaton · {etiqueta}{' simulado' if simulacion else ''} ({_resumen_nodos(nodos)}"
    descripcion += ", con historico electrico eVED)" if perfil else ")"
    datos = {"nodes": nodos, "operations": None, "connectors": None, "extra": extra}
    web.sesion.cargar_datos(
        _hacer_resolutor(web, datos, runtime=runtime, runs=runs, lock=lock),
        descripcion=descripcion, config={"red": "road"},
    )
    web.run_id = web.ultima = None
    return descripcion


def _cargar_desde_run(web: _SesionWeb, run_id: str, *, runtime, runs, lock) -> bool:
    """Toma como datos de la sesion el plan vigente de la UI. False si no se pudo."""
    from ev_routing.assist import PARAMETROS

    guardado = runs.get(run_id) if runs is not None and isinstance(run_id, str) else None
    if guardado is None:
        return False
    respuesta = json.loads(guardado)
    resultado = respuesta.get("result") or {}
    raw = resultado.get("raw") or {}
    entrada = raw.get("input") or {}
    instancia = raw.get("instance") or entrada.get("instance") or {}
    procedencia = instancia.get("provenance") or {}
    flota = resultado.get("fleet") or []

    config: dict[str, Any] = {}
    if flota:
        config["vehiculos"] = len(flota)
        config.update(_config_desde_fleet({k: flota[0].get(k) for k in
                                           ("initial_soc", "battery_capacity_kwh", "reserve_kwh")}))
    solver = entrada.get("solver") or {}
    if solver.get("time_limit_seconds"):
        config["tiempo_limite_s"] = solver["time_limit_seconds"]
    config["busqueda"] = solver.get("search_policy", "standard")

    preparada_id = entrada.get("prepared_instance_id")
    contexto = runtime.contexts.get(preparada_id) if (preparada_id and runtime) else None
    sintetica = (procedencia.get("kind") == "synthetic"
                 and (procedencia.get("network") or {}).get("kind") == "haversine")
    no_aplicables: frozenset[str] = frozenset()
    if contexto is not None:
        pedido = contexto[1].request
        datos = {"nodes": pedido["nodes"], "operations": pedido.get("operations"),
                 "connectors": (pedido.get("fleet") or {}).get("vehicle_connector_types"),
                 # escenario de la hackaton y perfil historico de energia, si los hubo
                 "extra": {k: pedido[k] for k in ("scenario", "energy_profile_id") if k in pedido}}
        config.update(_config_desde_fleet(pedido.get("fleet") or {}))
        config["red"] = pedido.get("network_mode", "road")
    elif preparada_id or sintetica:
        nodos = resultado.get("nodes") if preparada_id else instancia.get("nodes")
        consumo = (procedencia.get("consumption_kwh_km")
                   or (procedencia.get("energy_model") or {}).get("kwh_per_km"))
        if consumo:
            config["consumo_kwh_km"] = consumo
        datos = {"nodes": _nodos_csv(nodos), "operations": instancia.get("operations"),
                 "connectors": (instancia.get("parameters") or {}).get("vehicle_connector_types")}
        config["red"] = "road" if preparada_id else "haversine"
    else:
        datos = {"instance": entrada.get("instance") or instancia}
        no_aplicables = frozenset(k for k, s in PARAMETROS.items() if s.seccion == "preparacion")
    if "nodes" in datos and not datos["nodes"]:
        return False
    descripcion = "plan vigente"
    if "nodes" in datos:
        descripcion += f" ({_resumen_nodos(datos['nodes'])})"
    web.sesion.cargar_datos(
        _hacer_resolutor(web, datos, runtime=runtime, runs=runs, lock=lock),
        descripcion=descripcion, config=config, no_aplicables=no_aplicables,
    )
    web.sesion.ultimo_resultado = raw.get("result")
    web.run_id, web.ultima = run_id, respuesta
    return True


CHAT_TIMEOUT_S = 30
CHAT_MAX_TOKENS = 1200


def _cliente_bedrock(runtime=None):
    """Cliente Bedrock para el chat, o None (el chat sigue en modo local).

    Con servidor: reutiliza ``runtime.bedrock``, la misma conexion que la UI
    gestiona en /bedrock/session (credenciales temporales o perfil del servidor),
    con su modelo y region. Sin servidor (tests, CLI): entorno del proceso.
    """
    try:
        from ev_routing.assist import ClienteBedrock, ConfigBedrock, ModeloNoDisponible
        from ev_routing.assist.bedrock_chat import ErrorBedrock
    except Exception:
        return None
    conexion = getattr(runtime, "bedrock", None)
    if conexion is not None:
        try:
            from ev_routing.search_policy import BedrockConfig

            estado = conexion.status()  # publico, no inicializa SDK
            config = conexion.settings(BedrockConfig(
                model_id=estado["model_id"], region=estado["region"],
                profile=estado.get("profile"),
                timeout_seconds=CHAT_TIMEOUT_S, max_output_tokens=CHAT_MAX_TOKENS,
            ))
            if not config.model_id:
                return None
            # API interna de BedrockSession: cliente cacheado por (region, timeout)
            # e invalidado al desconectar (epoch). Ver docs/assist/integracion.md.
            epoch = conexion._epoch
            cliente = conexion._client(config, epoch)
        except Exception:  # desconectado, vencido o sin credenciales
            return None

        class ClienteSesion(ClienteBedrock):
            def conversar(self, mensajes, *, sistema, tool_config=None):
                # Share the same guard as tuning/history for every Converse
                # round; a captured SDK client cannot outlive its session.
                if not conexion._request_lock.acquire(blocking=False):
                    raise ErrorBedrock("Hay una consulta a AWS en curso. Espera a que termine.")
                try:
                    self._cliente = conexion._client(config, epoch)
                    return super().conversar(
                        mensajes, sistema=sistema, tool_config=tool_config,
                    )
                except ErrorBedrock:
                    raise
                except Exception as error:
                    raise ErrorBedrock(
                        "La conexion de AWS cambio o vencio. Vuelve a conectar para continuar."
                    ) from error
                finally:
                    conexion._request_lock.release()

        return ClienteSesion(
            ConfigBedrock(model_id=config.model_id, region=config.region,
                          max_tokens=CHAT_MAX_TOKENS),
            cliente=cliente,
        )
    if _cliente_cache:
        return _cliente_cache[0]
    cliente = ClienteBedrock()
    try:
        cliente._asegurar_cliente()
    except ModeloNoDisponible:
        return None
    _cliente_cache.append(cliente)
    return cliente


# --- endpoints ----------------------------------------------------------------
def schema(**_: Any) -> dict:
    """GET /assist/schema: lista blanca (tipos, rangos, estandar) para la UI."""
    from ev_routing.assist.tools import parametros_schema

    return parametros_schema()


def chat(payload: dict, *, solve_lock=None, runtime=None, runs=None) -> dict:
    """POST /assist/chat.

    payload: {session_id?, message?, run_id?, fuente?: {nodes|instance, prepare?}, archivo?}
    """
    from ev_routing.assist import Asistente, Sesion

    if not isinstance(payload, dict):
        raise AssistRequestError("La peticion debe ser un objeto JSON.")
    extras = set(payload) - _CAMPOS_PAYLOAD
    if extras:
        raise AssistRequestError(f"Campos no admitidos: {', '.join(sorted(extras))}.")
    mensaje = payload.get("message") or ""
    if not isinstance(mensaje, str):
        raise AssistRequestError("'message' debe ser texto.")
    fuente = payload.get("fuente")
    if not mensaje.strip() and fuente is None:
        raise AssistRequestError("Escribe un mensaje o adjunta un archivo.")
    entorno = {"runtime": runtime, "runs": runs, "lock": solve_lock}

    session_id = payload.get("session_id")
    with _lock:
        web = _sesiones.get(session_id) if isinstance(session_id, str) else None
        nueva = web is None
        if nueva:
            session_id = uuid.uuid4().hex
            web = _SesionWeb(Sesion())
            _sesiones[session_id] = web
            while len(_sesiones) > _MAX_SESIONES:
                _sesiones.popitem(last=False)
        else:
            _sesiones.move_to_end(session_id)

    # El caso de la hackaton siempre esta disponible como fuente desde el servidor.
    web.sesion.cargar_caso = lambda entrada: _cargar_caso(web, entrada, **entorno)

    if fuente is not None:
        nombre = str(payload.get("archivo") or "archivo")[:120]
        _cargar_archivo(web, fuente, nombre, **entorno)
        nota = f"[Adjunte {web.sesion.descripcion_datos}.]"
        if web.sesion.pendiente_calcular:
            nota += " Calcula ahora con lo que te pedi."
        mensaje = f"{mensaje} {nota}".strip()
    elif not web.sesion.tiene_datos and payload.get("run_id"):
        _cargar_desde_run(web, payload["run_id"], **entorno)

    turno = Asistente(web.sesion, _cliente_bedrock(runtime), confirmar_importantes=False).turno(mensaje)

    respuesta: dict[str, Any] = {
        "api_version": API_ASSIST,
        "session_id": session_id,
        "sesion_nueva": nueva,
        "respuesta": turno.respuesta,
        "modo": turno.modo,
        "acciones": [{"herramienta": a.herramienta, "entrada": a.entrada,
                      "confirmacion_requerida": a.confirmacion_requerida}
                     for a in turno.acciones],
        "necesita_archivo": turno.necesita_datos,
        "resolvio": turno.resolvio,
        "datos": web.sesion.descripcion_datos,
        "config": web.sesion.describir(),
        "error": turno.error,
    }
    if turno.resolvio and web.ultima is not None:
        res = web.ultima["result"]
        respuesta["run_id"] = web.run_id
        respuesta["resumen"] = {"entregas": res.get("served_count"),
                                "destinos": res.get("total_visits"),
                                "energia_kwh": res.get("total_energy_kwh")}
    return respuesta
