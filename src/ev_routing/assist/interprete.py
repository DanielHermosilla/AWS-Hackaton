"""Interprete local de mensajes (sin LLM).

Fallback determinista para cuando Bedrock no esta disponible o falla: entiende
los pedidos habituales del chat ("que sean 3 autos", "al 70 %", "20 segundos",
"sin GPT", "calcula", "explica") y los traduce a claves de la lista blanca.
No inventa valores: lo que no reconoce, no lo cambia.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

_NUMEROS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}
_VEHICULO = r"(?:vehiculos?|autos?|coches?|carros?|camion(?:es)?|camionetas?|furgon(?:es)?|moviles?|leafs?)"
_NUM = r"\b(\d+(?:[.,]\d+)?|" + "|".join(_NUMEROS) + r")"

_CALCULAR = re.compile(
    r"\b(calcula\w*|resuelv\w*|resolver|optimiz\w*|planific\w*|corre(?:r|lo)?|ejecut\w*|"
    r"dale|procede\w*|hazlo|adelante|recalcul\w*|arma\w*)\b"
)
_AFIRMACION = re.compile(r"^\s*(si|ok|okay|listo|de acuerdo|perfecto|vamos)\b[\s!.]*$")
_REINICIAR = re.compile(
    r"\b(reinici\w*|reset\w*|valores? (?:iniciales|estandar|por defecto)|"
    r"configuracion(?:es)? (?:estandar|inicial(?:es)?|por defecto)|como estaba)\b"
)
_EXPLICAR = re.compile(r"\b(explica\w*|por ?que|resum\w*|que hizo|detall\w*|cuentame)\b")
_SALUDO = re.compile(r"^\s*(hola|buenas|buen dia|buenos dias|buenas tardes|hey|que tal)\b")
_CONFIG = re.compile(r"\b(configuracion|parametros|con que|que (?:valores|supuestos))\b")


@dataclass
class Interpretacion:
    ajustes: dict[str, Any] = field(default_factory=dict)
    calcular: bool = False
    reiniciar: bool = False
    explicar: bool = False
    saludo: bool = False
    ver_config: bool = False
    # Caso de la hackaton pedido: {"dataset", "clientes"?, "cargadores"?, "semilla"?}
    caso: dict[str, Any] | None = None


def _caso(t: str) -> dict[str, Any] | None:
    if re.search(r"\bevaluac|\bevaluation\b", t):
        caso: dict[str, Any] = {"dataset": "evaluation"}
    elif re.search(r"\bcompeten|\bcompetic|\bcompetition\b|\bhackat|\bcaso oficial\b|\bdatos oficiales\b", t):
        caso = {"dataset": "competition"}
    else:
        return None
    if re.search(r"\bsimul", t):
        m = re.search(r"(\d+)\s*(?:clientes|destinos|entregas|locales)", t)
        if m:
            caso["clientes"] = int(m.group(1))
        m = re.search(r"(\d+)\s*cargadores", t)
        if m:
            caso["cargadores"] = int(m.group(1))
        m = re.search(r"semilla\s*(\d+)", t)
        if m:
            caso["semilla"] = int(m.group(1))
    return caso


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower().strip()


def _numero(token: str) -> float:
    token = token.replace(",", ".")
    return float(_NUMEROS.get(token, token))


def interpretar(texto: str) -> Interpretacion:
    t = _normalizar(texto)
    r = Interpretacion()
    m = re.search(_NUM + r"\s*" + _VEHICULO, t)
    if m:
        r.ajustes["vehiculos"] = _numero(m.group(1))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", t) or re.search(
        r"\b(?:al|soc(?: de| inicial(?: de)?)?|carga(?: inicial)?(?: de| al)?)\s+(\d+(?:[.,]\d+)?)\b", t
    )
    if m:
        valor = _numero(m.group(1))
        r.ajustes["soc_inicial"] = valor / 100 if valor > 1 else valor
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:s|seg|segs|segundos?)\b", t)
    if m:
        r.ajustes["tiempo_limite_s"] = _numero(m.group(1))
    m = re.search(r"(?:bateria|capacidad)\s*(?:de)?\s*(\d+(?:[.,]\d+)?)\s*kwh", t)
    if m:
        r.ajustes["capacidad_kwh"] = _numero(m.group(1))
    m = re.search(r"reserva\s*(?:de|minima de)?\s*(\d+(?:[.,]\d+)?)\s*kwh", t)
    if m:
        r.ajustes["reserva_kwh"] = _numero(m.group(1))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kwh\s*(?:/|por)\s*km", t)
    if m:
        r.ajustes["consumo_kwh_km"] = _numero(m.group(1))
    # "estandar" a secas significa "valores por defecto" (ver _REINICIAR), no la
    # politica de busqueda; solo "busqueda/politica estandar" la cambia.
    if re.search(r"\bsin (?:gpt|llm|bedrock|ia)\b|\b(?:busqueda|politica) estandar\b|\bdetermin", t):
        r.ajustes["busqueda"] = "deterministic" if "determin" in t else "standard"
    elif re.search(r"\bcon (?:gpt|llm|bedrock|ia)\b|\badaptativ", t):
        r.ajustes["busqueda"] = "adaptive"
    if re.search(r"\bgeodesic|\bhaversine\b|\blinea recta\b", t):
        r.ajustes["red"] = "haversine"
    elif re.search(r"\bcalles\b|\bred vial\b|\bcalles reales\b", t):
        r.ajustes["red"] = "road"
    r.reiniciar = bool(_REINICIAR.search(t))
    r.calcular = bool(_CALCULAR.search(t) or _AFIRMACION.match(t))
    r.explicar = bool(_EXPLICAR.search(t))
    r.saludo = bool(_SALUDO.search(t))
    r.ver_config = bool(_CONFIG.search(t))
    r.caso = _caso(t)
    return r
