"""Asistente conversacional E-VRP con herramientas y streaming (backend).

Expone:
  - `Asistente`: clase con `enviar(mensaje, sesion)` y `enviar_stream(...)`.
  - `Sesion`: estado de la conversación (instancia, overrides, último resultado).
  - `tool_specs`, `PARAMETROS`: herramientas y lista blanca de parámetros.

La IA es opcional y degrada de forma segura: el motor E-VRP nunca depende de ella
y las rutas SOLO las produce `evrp.resolver` + validador (el modelo nunca las
inventa).
"""
from __future__ import annotations

from .asistente import Accion, Asistente, RespuestaTurno, SISTEMA
from .herramientas import PARAMETROS, ErrorParametro, tool_specs, validar_parametro
from .sesion import NodoSesion, Sesion, ejecutar_herramienta

__all__ = [
    "Asistente",
    "Accion",
    "RespuestaTurno",
    "SISTEMA",
    "Sesion",
    "NodoSesion",
    "ejecutar_herramienta",
    "tool_specs",
    "validar_parametro",
    "PARAMETROS",
    "ErrorParametro",
]
