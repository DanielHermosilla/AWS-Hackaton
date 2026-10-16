"""Asistente conversacional (A) y explicacion verificada (C) sobre el solver.

Paquete agregado SIN modificar el nucleo del solver. Consume solo su frontera
publica (``pipeline.run_instance`` y los contratos) o un ``resolutor`` inyectado
por quien expone el chat (el backend web corre /prepare + /solve).

Principio rector: el LLM nunca inventa rutas ni toca el modelo matematico. Solo
(A) traduce lenguaje natural a cambios VALIDADOS por lista blanca y dispara el
motor, y (C) explica resultados ANCLADOS a los numeros del solver.

Degradacion segura: sin Bedrock, un interprete local determinista atiende los
pedidos habituales; el motor nunca depende de la IA.
"""

from __future__ import annotations

from .assistant import Accion, Asistente, RespuestaTurno
from .bedrock_chat import ClienteBedrock, ConfigBedrock, ErrorBedrock, ModeloNoDisponible
from .explainer import Explicacion, explicar
from .facts import Hechos, extraer_hechos
from .interprete import Interpretacion, interpretar
from .session import ErrorSesion, NecesitaDatos, Sesion, describir_config
from .tools import (
    PARAMETROS,
    ErrorParametro,
    ParametroSpec,
    parametros_schema,
    validar_parametro,
    valores_estandar,
)
from .verifier import verificar

__all__ = [
    "Accion",
    "Asistente",
    "ClienteBedrock",
    "ConfigBedrock",
    "ErrorBedrock",
    "ErrorParametro",
    "ErrorSesion",
    "Explicacion",
    "Hechos",
    "Interpretacion",
    "ModeloNoDisponible",
    "NecesitaDatos",
    "PARAMETROS",
    "ParametroSpec",
    "RespuestaTurno",
    "Sesion",
    "describir_config",
    "explicar",
    "extraer_hechos",
    "interpretar",
    "parametros_schema",
    "validar_parametro",
    "valores_estandar",
    "verificar",
]
