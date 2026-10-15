"""Ajuste del solver estilo LLM4MIP.

Un LLM recibe un *perfil estructural compacto* del MILP (nº de columnas, filas,
binarias, densidad, rangos de coeficientes, clientes, vehículos, gap y tiempo de
la corrida base) y propone parámetros de HiGHS de una LISTA BLANCA en JSON
validado. Nunca cambia datos, objetivo ni tolerancias (gap/hilos fijos).

Módulos:
- `perfil`: extrae el perfil estructural del modelo construido.
- `whitelist`: define la lista blanca, valida propuestas y genera un control
  (búsqueda aleatoria sobre la misma lista blanca).
- `llm`: construye el prompt y pide la propuesta a Bedrock (Haiku 4.5 / Sonnet 4.6).
"""
from __future__ import annotations

from .perfil import PerfilMILP, perfil_desde_modelo
from .whitelist import (
    LISTA_BLANCA,
    aplicar_overrides,
    muestra_aleatoria,
    validar_propuesta,
)

__all__ = [
    "PerfilMILP",
    "perfil_desde_modelo",
    "LISTA_BLANCA",
    "aplicar_overrides",
    "muestra_aleatoria",
    "validar_propuesta",
]
