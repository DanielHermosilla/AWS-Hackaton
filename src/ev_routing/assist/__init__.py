"""Asistente conversacional (A) y explicacion verificada (C) sobre el solver.

Este paquete se agrega SIN modificar el nucleo del solver. Solo consume la
frontera publica estable:

  - ``ev_routing.pipeline.run_instance`` como herramienta ``resolver``.
  - Los contratos ``ProblemInstance``, ``SolverConfig``, ``Operations`` y el
    ``dict`` serializado de ``SolveResult`` que devuelve ``run_instance``.

Principio rector (igual que el resto del repo): el LLM nunca inventa rutas ni
toca el modelo matematico. Solo (A) traduce lenguaje natural a cambios de
configuracion VALIDADOS por lista blanca, y (C) explica resultados ANCLADOS a
los numeros reales del solver (con verificador anti-alucinacion).

Degradacion segura: si Bedrock no esta disponible, el asistente devuelve un
error controlado; el solver y la webapp siguen funcionando sin IA.
"""

from __future__ import annotations

from .assistant import Accion, Asistente, RespuestaTurno
from .bedrock_chat import ClienteBedrock, ConfigBedrock, ErrorBedrock, ModeloNoDisponible
from .explainer import Explicacion, explicar
from .facts import Hechos, extraer_hechos
from .session import Sesion
from .tools import PARAMETROS, ErrorParametro, ParametroSpec, parametros_schema, validar_parametro
from .verifier import verificar

__all__ = [
    "Asistente",
    "RespuestaTurno",
    "Accion",
    "Sesion",
    "ClienteBedrock",
    "ConfigBedrock",
    "ErrorBedrock",
    "ModeloNoDisponible",
    "explicar",
    "Explicacion",
    "extraer_hechos",
    "Hechos",
    "verificar",
    "PARAMETROS",
    "ParametroSpec",
    "parametros_schema",
    "ErrorParametro",
    "validar_parametro",
]
