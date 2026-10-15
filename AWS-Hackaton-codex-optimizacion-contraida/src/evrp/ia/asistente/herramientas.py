"""Definición de herramientas (toolConfig Bedrock) y validación de parámetros.

El modelo NUNCA produce rutas: solo invoca estas herramientas, que operan sobre
el estado de la sesión y delegan el cálculo real a `evrp.resolver` + validador.

Lista blanca de parámetros editables (`cambiar_parametro`): únicamente las claves
de `PARAMETROS` se aceptan, cada una con su rango/validador. Cualquier otra clave
se rechaza con un mensaje de error (no se aplica silenciosamente).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# --- lista blanca de parámetros -------------------------------------------


@dataclass(frozen=True)
class ParametroSpec:
    """Especificación de un parámetro editable por el usuario vía la IA.

    `destino` es la ruta (seccion, clave) dentro del dict de overrides que luego
    se traduce a config del motor. `importante` marca cambios que requieren
    confirmación explícita del usuario en el turno siguiente.
    """

    clave: str
    tipo: str                       # "float" | "int"
    minimo: float
    maximo: float
    descripcion: str
    importante: bool = False
    validar_extra: Callable[[float], str | None] | None = None


PARAMETROS: dict[str, ParametroSpec] = {
    "soc_inicial": ParametroSpec(
        "soc_inicial", "float", 0.0, 1.0,
        "Estado de carga inicial de la batería (fracción 0..1).",
    ),
    "vehiculos": ParametroSpec(
        "vehiculos", "int", 1, 50,
        "Número de vehículos de la flota.", importante=True,
    ),
    "reserva_kwh": ParametroSpec(
        "reserva_kwh", "float", 0.0, 100.0,
        "Reserva mínima de energía en kWh (no se consume por debajo de ella).",
    ),
    "bateria_kwh": ParametroSpec(
        "bateria_kwh", "float", 1.0, 200.0,
        "Capacidad de batería en kWh.", importante=True,
    ),
    "presupuesto_s": ParametroSpec(
        "presupuesto_s", "float", 1.0, 600.0,
        "Presupuesto de tiempo del solver en segundos.",
    ),
}


class ErrorParametro(ValueError):
    """Parámetro desconocido o fuera de rango."""


def validar_parametro(clave: str, valor: Any) -> tuple[str, float]:
    """Valida (clave, valor) contra la lista blanca. Devuelve (clave, valor_tipado).

    Lanza `ErrorParametro` con mensaje claro si la clave no está permitida o el
    valor está fuera de rango / no es numérico.
    """
    spec = PARAMETROS.get(clave)
    if spec is None:
        permitidas = ", ".join(sorted(PARAMETROS))
        raise ErrorParametro(
            f"parámetro '{clave}' no permitido; solo: {permitidas}")
    try:
        v = int(valor) if spec.tipo == "int" else float(valor)
    except (TypeError, ValueError) as exc:
        raise ErrorParametro(f"'{clave}' espera un {spec.tipo}, no {valor!r}") from exc
    if not (spec.minimo <= v <= spec.maximo):
        raise ErrorParametro(
            f"'{clave}'={v} fuera de rango [{spec.minimo}, {spec.maximo}]")
    if spec.validar_extra is not None:
        msg = spec.validar_extra(v)
        if msg:
            raise ErrorParametro(msg)
    return clave, v


def es_importante(clave: str) -> bool:
    spec = PARAMETROS.get(clave)
    return bool(spec and spec.importante)


# --- toolConfig (toolSpec Bedrock) ----------------------------------------

def _obj(propiedades: dict, requeridos: list[str] | None = None) -> dict:
    esquema: dict[str, Any] = {"type": "object", "properties": propiedades}
    if requeridos:
        esquema["required"] = requeridos
    return esquema


def tool_specs() -> list[dict]:
    """Lista de toolSpec para `toolConfig.tools` de Bedrock Converse."""
    enum_param = sorted(PARAMETROS)
    return [
        {"toolSpec": {
            "name": "cargar_instancia",
            "description": "Carga una instancia (lista de nodos) desde un archivo CSV del "
                           "directorio de datos del proyecto. Reemplaza la instancia actual.",
            "inputSchema": {"json": _obj(
                {"ruta_csv": {"type": "string", "maxLength": 200,
                              "description": "Nombre del CSV dentro del directorio de datos "
                                             "(p. ej. 'competition_routing_nodes.csv'); "
                                             "no se aceptan rutas absolutas."}},
                ["ruta_csv"])},
        }},
        {"toolSpec": {
            "name": "agregar_cliente",
            "description": "Agrega un nodo cliente (punto de entrega) a la instancia actual.",
            "inputSchema": {"json": _obj({
                "id": {"type": "string"},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
            }, ["id", "lat", "lon"])},
        }},
        {"toolSpec": {
            "name": "quitar_nodo",
            "description": "Quita un nodo (cliente o cargador) por id de la instancia actual.",
            "inputSchema": {"json": _obj({"id": {"type": "string"}}, ["id"])},
        }},
        {"toolSpec": {
            "name": "desactivar_cargador",
            "description": "Desactiva un cargador por id (lo marca con 0 puertos; no se usará).",
            "inputSchema": {"json": _obj({"id": {"type": "string"}}, ["id"])},
        }},
        {"toolSpec": {
            "name": "cambiar_parametro",
            "description": "Cambia un parámetro de configuración. SOLO claves permitidas: "
                           + ", ".join(enum_param),
            "inputSchema": {"json": _obj({
                "clave": {"type": "string", "enum": enum_param},
                "valor": {"type": "number"},
            }, ["clave", "valor"])},
        }},
        {"toolSpec": {
            "name": "resolver",
            "description": "Resuelve el E-VRP con la instancia y parámetros actuales. "
                           "Produce rutas reales validadas por el motor (nunca inventadas).",
            "inputSchema": {"json": _obj({})},
        }},
        {"toolSpec": {
            "name": "consultar_resultado",
            "description": "Consulta un campo del último resultado (p.ej. 'entregas', "
                           "'energia_total_kwh', 'rutas', 'por_vehiculo', 'resumen').",
            "inputSchema": {"json": _obj(
                {"campo": {"type": "string"}}, ["campo"])},
        }},
        {"toolSpec": {
            "name": "extraer_pedidos",
            "description": "Extrae pedidos/clientes desde texto libre (gancho opcional de "
                           "ingesta). Devuelve 'no disponible' si el módulo no está instalado.",
            "inputSchema": {"json": _obj(
                {"texto": {"type": "string"}}, ["texto"])},
        }},
        {"toolSpec": {
            "name": "explicar",
            "description": "Explica en lenguaje natural el último resultado (gancho opcional). "
                           "Devuelve 'no disponible' si el módulo no está instalado.",
            "inputSchema": {"json": _obj({})},
        }},
    ]


# Herramientas destructivas o que cambian parámetros importantes: requieren que
# el usuario confirme en el turno siguiente antes de ejecutarse.
HERRAMIENTAS_DESTRUCTIVAS = {"quitar_nodo", "desactivar_cargador", "cargar_instancia"}
