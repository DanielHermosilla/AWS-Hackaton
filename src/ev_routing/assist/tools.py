"""Herramientas (toolConfig de Bedrock) y lista blanca de parametros.

El modelo NUNCA produce rutas ni edita libremente la configuracion: solo invoca
estas herramientas. ``cambiar_parametro`` acepta exclusivamente las claves de
``PARAMETROS``, cada una con tipo, rango u opciones y su VALOR ESTANDAR. Nada se
aplica en silencio: claves o valores invalidos devuelven un error accionable.

La lista blanca es la fuente unica de verdad para: el chat, el schema que
consume el frontend (``parametros_schema``) y los valores por defecto.

Estandar del escenario (README.md, AGENTS.md, diccionario.md): dos Nissan Leaf
2013 al 60 %, bateria anunciada de 24 kWh. Consumo de referencia EPA del Leaf
2013: ~30 kWh/100 mi (~0,18 kWh/km). El resto son supuestos de demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Tipo = Literal["float", "int", "opcion"]


@dataclass(frozen=True)
class ParametroSpec:
    """Parametro editable por el usuario via el asistente.

    ``web`` es la clave en la configuracion de la app (peticiones /prepare y
    /solve). ``destino`` es el campo del contrato nativo cuando el parametro se
    aplica directamente sobre una ProblemInstance (``seccion``):
      - "parametros": ProblemInstance.parameters (ModelParameters)
      - "solver":     SolverConfig
      - "preparacion": solo existe al preparar desde nodos (p. ej. consumo, red)
    ``importante`` marca cambios de alto impacto (la libreria puede pedir
    confirmacion; el chat web trata la instruccion explicita como confirmacion).
    """

    clave: str
    web: str
    seccion: Literal["parametros", "solver", "preparacion"]
    destino: str | None
    tipo: Tipo
    estandar: Any
    descripcion: str
    minimo: float | None = None
    maximo: float | None = None
    opciones: tuple[str, ...] = ()
    importante: bool = False


PARAMETROS: dict[str, ParametroSpec] = {
    "vehiculos": ParametroSpec(
        "vehiculos", "num_vehicles", "parametros", "vehicle_count", "int", 2,
        "Numero de vehiculos de la flota.", 1, 20, importante=True,
    ),
    "soc_inicial": ParametroSpec(
        "soc_inicial", "initial_soc", "parametros", "initial_soc", "float", 0.6,
        "Carga inicial de bateria como fraccion (0.6 = 60 %).", 0.01, 1.0,
    ),
    "capacidad_kwh": ParametroSpec(
        "capacidad_kwh", "battery_capacity_kwh", "parametros", "battery_capacity_kwh",
        "float", 24.0, "Capacidad util de bateria por vehiculo en kWh.", 1.0, 200.0,
        importante=True,
    ),
    "reserva_kwh": ParametroSpec(
        "reserva_kwh", "reserve_kwh", "parametros", "reserve_kwh", "float", 2.0,
        "Reserva minima de energia en kWh.", 0.001, 100.0,
    ),
    "consumo_kwh_km": ParametroSpec(
        "consumo_kwh_km", "consumption_kwh_km", "preparacion", None, "float", 0.18,
        "Consumo supuesto en kWh/km (solo al preparar desde nodos).", 0.01, 5.0,
    ),
    "tiempo_limite_s": ParametroSpec(
        "tiempo_limite_s", "time_limit_seconds", "solver", "time_limit_seconds", "float",
        10.0, "Presupuesto de tiempo del solver en segundos.", 1.0, 120.0,
    ),
    "busqueda": ParametroSpec(
        "busqueda", "search_policy", "solver", None, "opcion", "adaptive",
        "Politica de busqueda: adaptive (GPT via Bedrock), standard o deterministic.",
        opciones=("adaptive", "standard", "deterministic"),
    ),
    "red": ParametroSpec(
        "red", "network_mode", "preparacion", None, "opcion", "road",
        "Red: road (calles del servidor) o haversine (geodesica sintetica).",
        opciones=("road", "haversine"),
    ),
}

# Clave web -> clave de la lista blanca (para leer configuraciones existentes).
POR_CLAVE_WEB = {spec.web: spec.clave for spec in PARAMETROS.values()}


class ErrorParametro(ValueError):
    """Parametro desconocido, de tipo invalido o fuera de rango."""


def validar_parametro(clave: str, valor: Any) -> tuple[ParametroSpec, Any]:
    """Valida (clave, valor) contra la lista blanca. Devuelve (spec, valor_tipado)."""
    spec = PARAMETROS.get(clave)
    if spec is None:
        permitidas = ", ".join(sorted(PARAMETROS))
        raise ErrorParametro(f"Parametro '{clave}' no permitido. Editables: {permitidas}.")
    if spec.tipo == "opcion":
        texto = str(valor).strip().lower()
        if texto not in spec.opciones:
            raise ErrorParametro(
                f"'{clave}' admite: {', '.join(spec.opciones)}; recibido {valor!r}."
            )
        return spec, texto
    if isinstance(valor, bool):
        raise ErrorParametro(f"'{clave}' espera un numero; recibido {valor!r}.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ErrorParametro(f"'{clave}' espera un numero; recibido {valor!r}.") from exc
    if spec.tipo == "int":
        if not numero.is_integer():
            raise ErrorParametro(f"'{clave}' espera un entero; recibido {valor!r}.")
        tipado: Any = int(numero)
    else:
        tipado = numero
    if not (spec.minimo <= tipado <= spec.maximo):
        raise ErrorParametro(
            f"'{clave}' fuera de rango [{spec.minimo:g}, {spec.maximo:g}]: {tipado}."
        )
    return spec, tipado


def valores_estandar() -> dict[str, Any]:
    """Configuracion estandar del escenario, por clave de la lista blanca."""
    return {clave: spec.estandar for clave, spec in PARAMETROS.items()}


# --- casos precargados ----------------------------------------------------------
# Nombre visible para el usuario -> dataset interno de backend/scenarios.py.
# "CASE" es el nombre del caso de la hackaton; asi se puede pedir
# "corre el caso CASE". Los nombres internos siguen aceptandose por compatibilidad.
CASOS: dict[str, dict[str, str]] = {
    "CASE": {"dataset": "competition", "nombre": "caso CASE"},
    "CASE-evaluacion": {"dataset": "evaluation", "nombre": "caso CASE de evaluación"},
}
_ALIAS_CASO = {"competition": "CASE", "evaluation": "CASE-evaluacion",
               "case": "CASE", "case-evaluacion": "CASE-evaluacion"}


def resolver_caso(entrada: dict) -> str:
    """Clave de ``CASOS`` pedida en ``entrada`` ({"caso"} o el legado {"dataset"})."""
    valor = str(entrada.get("caso") or entrada.get("dataset") or "CASE").strip()
    clave = valor if valor in CASOS else _ALIAS_CASO.get(valor.lower())
    if clave is None:
        raise ErrorParametro(f"Caso desconocido: {valor}. Disponibles: {', '.join(CASOS)}.")
    return clave


def tool_specs(*, casos: bool = False) -> dict:
    """toolConfig de Bedrock. Ninguna herramienta produce rutas por si misma.

    ``casos``: incluir ``usar_caso`` (solo si quien expone el chat puede cargar los
    casos precargados de ``CASOS``, p. ej. el servidor web).
    """
    vacio = {"json": {"type": "object", "properties": {}}}
    descripcion_claves = "; ".join(
        f"{s.clave}: {s.descripcion}" for s in PARAMETROS.values()
    )
    herramientas = [
            {"toolSpec": {
                "name": "resolver",
                "description": (
                    "Calcula el plan con el motor usando los datos de la sesion y la "
                    "configuracion vigente. Unica fuente de rutas. Si faltan datos, "
                    "devuelve necesita_archivo=true."
                ),
                "inputSchema": vacio,
            }},
            {"toolSpec": {
                "name": "consultar_resultado",
                "description": "Resume el ultimo plan calculado (entregas, recargas, energia).",
                "inputSchema": vacio,
            }},
            {"toolSpec": {
                "name": "cambiar_parametro",
                "description": "Cambia un parametro de la lista blanca. " + descripcion_claves,
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "clave": {"type": "string", "enum": sorted(PARAMETROS)},
                        "valor": {"description": "Numero, o texto para busqueda/red."},
                    },
                    "required": ["clave", "valor"],
                }},
            }},
            {"toolSpec": {
                "name": "reiniciar_config",
                "description": "Vuelve a la configuracion inicial de la sesion.",
                "inputSchema": vacio,
            }},
            {"toolSpec": {
                "name": "mostrar_config",
                "description": "Muestra la configuracion inicial, la vigente y los cambios.",
                "inputSchema": vacio,
            }},
    ]
    if casos:
        herramientas.append({"toolSpec": {
            "name": "usar_caso",
            "description": (
                "Carga como datos el caso precargado, sin pedir archivo: 'CASE' (el caso de "
                "la hackaton en Ann Arbor) o 'CASE-evaluacion' (su variante de evaluacion), "
                "con consumo historico real si esta disponible. Opcional: simular otra "
                "cantidad de clientes/cargadores."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "caso": {"type": "string", "enum": list(CASOS)},
                    "clientes": {"type": "integer", "minimum": 1, "maximum": 199},
                    "cargadores": {"type": "integer", "minimum": 0, "maximum": 198},
                    "semilla": {"type": "integer", "minimum": 0},
                },
                "required": ["caso"],
            }},
        }})
    return {"tools": herramientas}


# --- esquema para el frontend ---------------------------------------------
SCHEMA_VERSION = "1.1"


def parametros_schema() -> dict:
    """Serializa la lista blanca (tipos, rangos/opciones y estandar) para la UI."""
    parametros = {}
    for spec in PARAMETROS.values():
        entrada = {
            "tipo": spec.tipo,
            "estandar": spec.estandar,
            "clave_web": spec.web,
            "seccion": spec.seccion,
            "destino": spec.destino,
            "importante": spec.importante,
            "descripcion": spec.descripcion,
        }
        if spec.tipo == "opcion":
            entrada["opciones"] = list(spec.opciones)
        else:
            entrada["min"], entrada["max"] = spec.minimo, spec.maximo
        parametros[spec.clave] = entrada
    return {"schema_version": SCHEMA_VERSION, "parametros": parametros}
