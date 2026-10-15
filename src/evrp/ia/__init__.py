"""Subpaquete de IA generativa: cliente central de Amazon Bedrock.

El cliente (`ClienteBedrock`) es la única puerta a `bedrock-runtime` Converse:
system prompt, salida JSON validada, tool use (toolConfig), imágenes y registro
de latencia/tokens. El resto del paquete (p. ej. `evrp.asesor`) lo reutiliza.
"""
from __future__ import annotations

from .bedrock import (
    ClienteBedrock,
    ErrorBedrock,
    EventoStream,
    ModeloNoDisponible,
    RespuestaConverse,
    extraer_json,
)

__all__ = [
    "ClienteBedrock",
    "ErrorBedrock",
    "EventoStream",
    "ModeloNoDisponible",
    "RespuestaConverse",
    "extraer_json",
]
