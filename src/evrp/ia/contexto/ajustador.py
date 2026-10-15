"""`ajustar(contexto_texto)` → ajustes del motor desde un texto de contexto.

Separación estricta de responsabilidades:
- El LLM (o el extractor de reglas, sin red) SOLO extrae **variables** de una lista
  blanca: temperatura (°C), precipitación (nieve/lluvia/seco), tráfico (bajo/medio/
  alto) y carga (fracción 0–1 de ocupación). No propone factores ni toca el motor.
- `factor_desde_variables` calcula el `consumo_factor` (y una `reserva_kwh` opcional)
  usando la calibración por temperatura y recargos acotados por rangos. Esto es
  determinista y auditable.

Contrato:
    ajustar(contexto_texto, calibracion=None, cliente=None)
      -> {
           "ajustes": {"consumo_factor": float, "reserva_kwh": float?},
           "justificacion": str,
           "supuestos": [str, ...],
           "variables": {...},      # lo que se extrajo
           "uso": {...}             # origen/modelo/tokens/latencia
         }

El motor nunca depende del LLM: sin `cliente` se usa el extractor de reglas.
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

# Lista blanca de variables y sus rangos/valores válidos.
VARIABLES_PERMITIDAS: dict[str, Any] = {
    "temperatura_c": (-40.0, 55.0),            # °C
    "precipitacion": {"seco", "lluvia", "nieve"},
    "trafico": {"bajo", "medio", "alto"},
    "carga_frac": (0.0, 1.0),                   # fracción de carga del vehículo
}

# Recargos acotados (multiplicadores sobre el factor de temperatura).
_RECARGO_PRECIP = {"seco": 1.0, "lluvia": 1.08, "nieve": 1.20}
_RECARGO_TRAFICO = {"bajo": 1.0, "medio": 1.05, "alto": 1.12}
# La carga añade hasta +8 % a plena ocupación (peso extra ≈ consumo extra).
_RECARGO_CARGA_MAX = 0.08
# Cota global del factor para no romper la factibilidad del motor.
FACTOR_MIN, FACTOR_MAX = 0.7, 2.0


def _banda_desde_temp(temp_c: float) -> str:
    from .calibracion import _banda_temp
    return _banda_temp(temp_c)


def factor_desde_variables(variables: dict, calibracion: dict | None = None) -> dict:
    """Calcula {consumo_factor, reserva_kwh?, componentes} desde variables validadas.

    `calibracion` es el dict de `CalibracionTemperatura.a_dict()` (opcional). Si no
    hay, se usan factores de temperatura por defecto conservadores.
    """
    v = validar_variables(variables)

    # 1) Factor por temperatura (desde calibración o por defecto).
    factor_temp = 1.0
    banda = None
    if v.get("temperatura_c") is not None:
        banda = _banda_desde_temp(v["temperatura_c"])
        if calibracion and banda in (calibracion.get("factores") or {}):
            factor_temp = float(calibracion["factores"][banda])
        else:
            factor_temp = _FACTOR_TEMP_DEFECTO.get(banda, 1.0)

    # 2) Recargos multiplicativos acotados.
    factor_precip = _RECARGO_PRECIP.get(v.get("precipitacion", "seco"), 1.0)
    factor_trafico = _RECARGO_TRAFICO.get(v.get("trafico", "bajo"), 1.0)
    carga = v.get("carga_frac")
    factor_carga = 1.0 + _RECARGO_CARGA_MAX * carga if carga is not None else 1.0

    factor = factor_temp * factor_precip * factor_trafico * factor_carga
    factor = round(min(FACTOR_MAX, max(FACTOR_MIN, factor)), 3)

    ajustes: dict[str, Any] = {"consumo_factor": factor}
    # Reserva extra en condiciones adversas (nieve o frío severo): colchón de seguridad.
    if v.get("precipitacion") == "nieve" or (v.get("temperatura_c") is not None
                                             and v["temperatura_c"] < 0):
        ajustes["reserva_kwh"] = 1.5

    return {
        "ajustes": ajustes,
        "componentes": {
            "banda_temperatura": banda,
            "factor_temperatura": round(factor_temp, 3),
            "factor_precipitacion": factor_precip,
            "factor_trafico": factor_trafico,
            "factor_carga": round(factor_carga, 3),
        },
        "variables": v,
    }


# Factores por defecto si no hay calibración (basados en literatura EV: calefacción
# en frío sube ~30–50 %, AC en calor ~10–20 %). Conservadores y acotados.
_FACTOR_TEMP_DEFECTO = {
    "<0": 1.4,
    "0-10": 1.2,
    "10-20": 1.05,
    "20-30": 1.0,
    ">30": 1.15,
}


def validar_variables(variables: dict) -> dict:
    """Filtra variables fuera de la lista blanca o de rango. Descarta lo inválido."""
    limpio: dict[str, Any] = {}
    for clave, dominio in VARIABLES_PERMITIDAS.items():
        if clave not in (variables or {}):
            continue
        val = variables[clave]
        if val is None:
            continue
        if isinstance(dominio, tuple):  # rango numérico
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if dominio[0] <= val <= dominio[1]:
                limpio[clave] = val
        elif isinstance(dominio, set):  # categórico
            if isinstance(val, str) and val.lower() in dominio:
                limpio[clave] = val.lower()
    return limpio


# --- Extractor de reglas (sin red): palabras clave + números ---

import re  # noqa: E402

_RE_TEMP = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(?:°|º)?\s*(?:c|grados)", re.IGNORECASE)


def extraer_variables_reglas(texto: str) -> dict:
    """Extracción determinista por palabras clave (respaldo sin LLM)."""
    t = (texto or "").lower()
    v: dict[str, Any] = {}

    m = _RE_TEMP.search(t)
    if m:
        try:
            v["temperatura_c"] = float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    # Pistas cualitativas de temperatura si no hay número.
    hay_nieve = ("niev" in t or "nev" in t or "helada" in t)
    if "temperatura_c" not in v:
        if hay_nieve or "gélid" in t or "muy frío" in t or "muy frio" in t:
            v["temperatura_c"] = -3.0
        elif "frío" in t or "frio" in t:
            v["temperatura_c"] = 5.0
        elif any(w in t for w in ("calor", "caluroso", "ola de calor")):
            v["temperatura_c"] = 33.0

    if hay_nieve:
        v["precipitacion"] = "nieve"
    elif "lluv" in t or "llov" in t or "llueve" in t:
        v["precipitacion"] = "lluvia"

    if "mucho tráfico" in t or "mucho trafico" in t or "tráfico alto" in t or "congest" in t:
        v["trafico"] = "alto"
    elif "tráfico medio" in t or "trafico medio" in t:
        v["trafico"] = "medio"
    elif "sin tráfico" in t or "poco tráfico" in t or "poco trafico" in t or "fluido" in t:
        v["trafico"] = "bajo"

    if "lleno" in t or "plena carga" in t or "cargado al máximo" in t or "a tope" in t:
        v["carga_frac"] = 1.0
    elif "media carga" in t or "medio lleno" in t:
        v["carga_frac"] = 0.5
    elif "vacío" in t or "vacio" in t or "sin carga" in t:
        v["carga_frac"] = 0.0

    return v


_HERRAMIENTA_EXTRAER = {
    "toolSpec": {
        "name": "registrar_variables",
        "description": ("Registra las variables de contexto operativo detectadas en el "
                        "texto. Solo extrae lo que esté EXPLÍCITO o claramente implícito; "
                        "omite lo que no se mencione. No calcules consumos ni factores."),
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "temperatura_c": {"type": "number",
                                  "description": "Temperatura ambiente en °C (-40 a 55)."},
                "precipitacion": {"type": "string", "enum": ["seco", "lluvia", "nieve"]},
                "trafico": {"type": "string", "enum": ["bajo", "medio", "alto"]},
                "carga_frac": {"type": "number",
                               "description": "Fracción de carga del vehículo, 0 a 1."},
            },
            "additionalProperties": False,
        }},
    }
}


def extraer_variables_llm(texto: str, cliente: Any) -> tuple[dict, Any]:
    """Fuerza la herramienta de extracción y devuelve (variables, respuesta)."""
    sistema = ("Eres un extractor de variables operativas para una flota de vehículos "
               "eléctricos. Devuelve solo variables presentes en el texto mediante la "
               "herramienta. No inventes ni calcules nada.")
    args, resp = cliente.usar_herramienta(texto, _HERRAMIENTA_EXTRAER, sistema=sistema,
                                          max_tokens=300)
    return (args or {}), resp


def ajustar(
    contexto_texto: str,
    *,
    calibracion: dict | None = None,
    cliente: Any | None = None,
) -> dict:
    """Convierte un texto de contexto en ajustes del motor (consumo_factor, reserva).

    Si `cliente` es None, usa el extractor de reglas (sin red). El factor SIEMPRE lo
    calcula `factor_desde_variables` (el LLM nunca lo decide).
    """
    uso = {"origen": "reglas", "modelo": None, "tokens_entrada": 0,
           "tokens_salida": 0, "tokens_total": 0, "latencia_s": 0.0}
    supuestos: list[str] = []

    variables_crudas: dict = {}
    if cliente is not None:
        try:
            variables_crudas, resp = extraer_variables_llm(contexto_texto, cliente)
            uso.update({
                "origen": "llm",
                "modelo": getattr(cliente, "modelo", None),
                "tokens_entrada": getattr(resp, "tokens_entrada", 0),
                "tokens_salida": getattr(resp, "tokens_salida", 0),
                "tokens_total": getattr(resp, "tokens_total", 0),
                "latencia_s": round(getattr(resp, "latencia_s", 0.0), 3),
            })
        except Exception as exc:  # degradación segura
            log.warning("Extractor LLM no disponible (%s); se usan reglas", exc)
            supuestos.append(f"LLM no disponible ({type(exc).__name__}); extracción por reglas.")
            variables_crudas = extraer_variables_reglas(contexto_texto)
    else:
        variables_crudas = extraer_variables_reglas(contexto_texto)

    calc = factor_desde_variables(variables_crudas, calibracion)
    v = calc["variables"]

    # Supuestos explícitos sobre lo no mencionado.
    if "temperatura_c" not in v:
        supuestos.append("Sin temperatura explícita: se asume clima templado (factor 1.0).")
    if "precipitacion" not in v:
        supuestos.append("Sin precipitación explícita: se asume seco.")
    if "trafico" not in v:
        supuestos.append("Sin tráfico explícito: se asume bajo.")
    if "carga_frac" not in v:
        supuestos.append("Sin nivel de carga explícito: no se aplica recargo por carga.")

    justificacion = _justificar(calc)

    return {
        "ajustes": calc["ajustes"],
        "justificacion": justificacion,
        "supuestos": supuestos,
        "variables": v,
        "componentes": calc["componentes"],
        "uso": uso,
    }


def _justificar(calc: dict) -> str:
    c = calc["componentes"]
    f = calc["ajustes"]["consumo_factor"]
    partes = [f"Factor de consumo {f}×."]
    if c["banda_temperatura"]:
        partes.append(f"Temperatura en banda {c['banda_temperatura']} °C "
                      f"(×{c['factor_temperatura']}).")
    if c["factor_precipitacion"] != 1.0:
        partes.append(f"Precipitación (×{c['factor_precipitacion']}).")
    if c["factor_trafico"] != 1.0:
        partes.append(f"Tráfico (×{c['factor_trafico']}).")
    if c["factor_carga"] != 1.0:
        partes.append(f"Carga del vehículo (×{c['factor_carga']}).")
    if "reserva_kwh" in calc["ajustes"]:
        partes.append(f"Reserva extra de {calc['ajustes']['reserva_kwh']} kWh por "
                      "condiciones adversas.")
    return " ".join(partes)
