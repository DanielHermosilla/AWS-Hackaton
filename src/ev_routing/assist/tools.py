"""Herramientas (toolConfig de Bedrock) y lista blanca de parametros.

El modelo NUNCA produce rutas ni edita libremente la configuracion: solo invoca
estas herramientas. ``cambiar_parametro`` acepta exclusivamente las claves de
``PARAMETROS``, cada una con tipo, rango y DESTINO en los contratos reales del
solver (``SolverConfig`` / ``Operations``). Cualquier otra clave se rechaza con
un mensaje claro; nada se aplica en silencio. Esto es lo que protege la
factibilidad frente a sugerencias del LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class ParametroSpec:
    """Especificacion de un parametro editable por el usuario via la IA.

    ``seccion`` indica a que contrato pertenece el destino:
      - "solver"      -> campos de ``SolverConfig``
      - "operations"  -> campos de ``Operations`` (parametros fisicos/operativos)
      - "instancia"   -> cantidades a nivel de instancia (p. ej. flota)

    ``importante`` marca cambios de alto impacto que requieren confirmacion
    explicita del usuario en el turno siguiente antes de aplicarse.
    """

    clave: str
    seccion: Literal["solver", "operations", "instancia"]
    destino: str                      # nombre del campo real en el contrato
    tipo: Literal["float", "int"]
    minimo: float
    maximo: float
    descripcion: str
    importante: bool = False
    validar_extra: Callable[[float], str | None] | None = None


# --- lista blanca: unicas claves que el LLM puede tocar --------------------
PARAMETROS: dict[str, ParametroSpec] = {
    "soc_inicial": ParametroSpec(
        "soc_inicial", "operations", "final_reserve_soc", "float", 0.0, 1.0,
        "Estado de carga inicial de la bateria (fraccion 0..1).",
    ),
    "vehiculos": ParametroSpec(
        # Flota: maximo 10 por ahora (decision de alcance de la demo).
        "vehiculos", "instancia", "fleet_size", "int", 1, 10,
        "Numero de vehiculos de la flota (1..10).", importante=True,
    ),
    "reserva_final_soc": ParametroSpec(
        "reserva_final_soc", "operations", "final_reserve_soc", "float", 0.0, 1.0,
        "Reserva minima de carga al terminar la ruta (fraccion 0..1).",
    ),
    "margen_energia": ParametroSpec(
        "margen_energia", "operations", "energy_margin_fraction", "float", 0.0, 0.5,
        "Margen de seguridad sobre el consumo estimado por arco (fraccion).",
    ),
    "tiempo_limite_s": ParametroSpec(
        "tiempo_limite_s", "solver", "time_limit_seconds", "float", 1.0, 600.0,
        "Presupuesto de tiempo del solver en segundos.",
    ),
    "gap_energia": ParametroSpec(
        "gap_energia", "solver", "energy_relative_gap", "float", 0.0, 1.0,
        "Tolerancia relativa de la fase de energia (0 = exacto).",
    ),
    "max_ruta_s": ParametroSpec(
        "max_ruta_s", "operations", "max_route_seconds", "float", 1.0, 86400.0,
        "Duracion maxima de una ruta en segundos.", importante=True,
    ),
}


class ErrorParametro(ValueError):
    """Parametro desconocido o fuera de rango."""


def validar_parametro(clave: str, valor: Any) -> tuple[ParametroSpec, float | int]:
    """Valida (clave, valor) contra la lista blanca.

    Devuelve ``(spec, valor_tipado)`` o lanza ``ErrorParametro`` con mensaje
    claro si la clave no esta permitida o el valor es invalido/fuera de rango.
    """
    spec = PARAMETROS.get(clave)
    if spec is None:
        permitidas = ", ".join(sorted(PARAMETROS))
        raise ErrorParametro(
            f"Parametro '{clave}' no permitido. Editables: {permitidas}."
        )
    try:
        tipado: float | int = int(valor) if spec.tipo == "int" else float(valor)
    except (TypeError, ValueError) as exc:
        raise ErrorParametro(
            f"'{clave}' espera un {spec.tipo}; recibido {valor!r}."
        ) from exc
    if not (spec.minimo <= tipado <= spec.maximo):
        raise ErrorParametro(
            f"'{clave}' fuera de rango [{spec.minimo}, {spec.maximo}]: {tipado}."
        )
    if spec.validar_extra is not None:
        problema = spec.validar_extra(tipado)
        if problema:
            raise ErrorParametro(f"'{clave}': {problema}")
    return spec, tipado


def tool_specs() -> dict:
    """toolConfig de Bedrock: herramientas que el modelo puede invocar.

    Ninguna herramienta produce rutas por si misma; 'resolver' delega el calculo
    real a ``pipeline.run_instance`` + validacion independiente.
    """
    claves = sorted(PARAMETROS)
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "resolver",
                    "description": (
                        "Resuelve la instancia actual con la configuracion vigente "
                        "usando el solver determinista. Unica fuente de rutas."
                    ),
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "consultar_resultado",
                    "description": (
                        "Devuelve el ultimo resultado resuelto (rutas, entregas, "
                        "clientes sin atender, energia). No resuelve de nuevo."
                    ),
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "cambiar_parametro",
                    "description": (
                        "Cambia un parametro de configuracion de la lista blanca. "
                        "Cambios importantes requieren confirmacion del usuario."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "clave": {"type": "string", "enum": claves},
                                "valor": {"type": "number"},
                            },
                            "required": ["clave", "valor"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "reiniciar_config",
                    "description": (
                        "Restaura la configuracion y la instancia a su estado "
                        "inicial (deshace todos los cambios de la sesion)."
                    ),
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "mostrar_config",
                    "description": (
                        "Muestra la configuracion inicial y la vigente, y los "
                        "cambios aplicados en la sesion."
                    ),
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
        ]
    }
