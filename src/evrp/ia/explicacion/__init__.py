"""Explicación de rutas en lenguaje natural con verificación anti-alucinación.

`explicar(resultado, estilo, idioma)` devuelve un dict con el texto, los hechos
citados, advertencias y el uso de tokens/latencia. Garantía dura: **cero cifras
inventadas**. El texto producido por el LLM pasa por un verificador que extrae
todos los números e IDs y comprueba que existan en el resultado (con tolerancia
de redondeo). Si falla, se reintenta una vez con la lista de errores; si vuelve a
fallar, se cae a una explicación por plantilla determinista (sin LLM).

El motor nunca depende de este módulo: todo es opcional y degrada con seguridad.
"""
from __future__ import annotations

from .hechos import Hecho, extraer_hechos, normalizar_resultado
from .plantilla import explicar_plantilla
from .verificador import ResultadoVerificacion, verificar_texto
from .explicador import explicar

__all__ = [
    "explicar",
    "explicar_plantilla",
    "extraer_hechos",
    "normalizar_resultado",
    "verificar_texto",
    "Hecho",
    "ResultadoVerificacion",
]
