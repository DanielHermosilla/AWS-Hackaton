"""Contexto→parámetros: del texto de contexto a ajustes del motor, calibrados con datos.

Dos capas, claramente separadas:
- `calibracion`: a partir de `eVED_EV.csv` estima el consumo (kWh/km) por banda de
  temperatura (y de velocidad) con intervalos. 100 % determinista, sin LLM.
- `ajustador`: `ajustar(contexto_texto)` donde el LLM SOLO extrae variables
  (temperatura, nieve/lluvia, tráfico, carga) de una lista blanca, y el factor de
  consumo lo calcula una función calibrada (rangos acotados). El motor nunca depende
  del LLM: sin cliente, se usa un extractor de reglas determinista.

El resultado de `ajustar` encaja con las claves que el motor ya acepta
(`tipos_vehiculo.*.consumo_kwh_km`, `reserva_kwh`) vía el `consumo_factor`.
"""
from __future__ import annotations

from .calibracion import (
    CalibracionTemperatura,
    calibrar_por_temperatura,
    cargar_calibracion,
    guardar_calibracion,
)
from .ajustador import (
    VARIABLES_PERMITIDAS,
    ajustar,
    factor_desde_variables,
    extraer_variables_reglas,
)

__all__ = [
    "ajustar",
    "factor_desde_variables",
    "extraer_variables_reglas",
    "VARIABLES_PERMITIDAS",
    "CalibracionTemperatura",
    "calibrar_por_temperatura",
    "cargar_calibracion",
    "guardar_calibracion",
]
