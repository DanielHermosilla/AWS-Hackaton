"""Orquestador de `explicar`: LLM → verificar → reintentar → plantilla.

Contrato:
    explicar(resultado, estilo='operador'|'gerencia', idioma='es', cliente=None)
      -> {
           "texto": str,
           "hechos_citados": [{"campo": str, "valor": num|str}, ...],
           "advertencias": [str, ...],
           "uso": {"origen": "llm"|"plantilla", "intentos": int,
                   "modelo": str|None, "tokens_entrada": int, "tokens_salida": int,
                   "latencia_s": float, "verificado": bool}
         }

Garantía: el `texto` devuelto SIEMPRE pasa el verificador (cero cifras inventadas),
porque si el LLM no lo logra en dos intentos se devuelve la plantilla determinista.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .hechos import extraer_hechos, normalizar_resultado, resumen_para_llm
from .plantilla import explicar_plantilla
from .verificador import hechos_citados_en, verificar_texto

log = logging.getLogger(__name__)

_ESTILOS = {
    "operador": (
        "Escribe para un operador de flota: concreto y accionable. Describe qué hace "
        "cada vehículo, dónde recarga y por qué, el margen mínimo de batería y qué "
        "entregas quedan pendientes."
    ),
    "gerencia": (
        "Escribe para gerencia: resumen ejecutivo breve. Enfatiza entregas cumplidas, "
        "energía total, vehículos usados y pendientes, con una recomendación."
    ),
}


def _sistema(estilo: str, idioma: str) -> str:
    enfoque = _ESTILOS.get(estilo, _ESTILOS["operador"])
    return (
        "Eres el asistente de una jefa de flota de vehículos eléctricos. "
        f"{enfoque} "
        f"Responde en {_nombre_idioma(idioma)}. "
        "REGLA ABSOLUTA: usa EXCLUSIVAMENTE los números e identificadores (BASE, V#, C#) "
        "que aparecen en el JSON de datos. NO inventes, estimes ni redondees de forma "
        "que cambie un valor; si un dato no está en el JSON, no lo menciones. "
        "No incluyas porcentajes ni cálculos derivados que no estén en el JSON. "
        "Devuelve solo el texto de la explicación, sin listas de metadatos."
    )


def _nombre_idioma(idioma: str) -> str:
    return {"es": "español", "en": "inglés", "pt": "portugués"}.get(idioma, "español")


def _instruccion(resumen: dict) -> str:
    return (
        "Explica esta solución de ruteo. Datos (única fuente de cifras):\n"
        + json.dumps(resumen, ensure_ascii=False)
    )


def explicar(
    resultado: Any,
    estilo: str = "operador",
    idioma: str = "es",
    *,
    cliente: Any | None = None,
    max_tokens: int = 500,
    abs_tol: float = 0.05,
    rel_tol: float = 0.01,
) -> dict:
    """Explica un `Resultado`/dict. Si `cliente` es None, usa solo la plantilla.

    `cliente` es un `evrp.ia.ClienteBedrock` (o doble con `.preguntar`).
    """
    normalizar_resultado(resultado)  # valida forma temprano
    hechos = extraer_hechos(resultado)
    advertencias: list[str] = []

    if cliente is None:
        texto = explicar_plantilla(resultado, estilo, idioma)
        return _empaquetar(texto, hechos, advertencias, origen="plantilla",
                           intentos=0, modelo=None, tokens_in=0, tokens_out=0,
                           latencia=0.0, verificado=True, abs_tol=abs_tol, rel_tol=rel_tol)

    resumen = resumen_para_llm(resultado)
    sistema = _sistema(estilo, idioma)
    tokens_in = tokens_out = 0
    latencia = 0.0
    modelo = getattr(cliente, "modelo", None)

    mensaje = _instruccion(resumen)
    ultimos_errores: list[str] = []
    for intento in range(1, 3):  # 1 intento + 1 reintento
        try:
            resp = cliente.preguntar(mensaje, sistema=sistema, max_tokens=max_tokens)
        except Exception as exc:  # degradación segura
            log.warning("Explicador LLM no disponible (%s); se usa plantilla", exc)
            advertencias.append(f"LLM no disponible: {type(exc).__name__}")
            texto = explicar_plantilla(resultado, estilo, idioma)
            return _empaquetar(texto, hechos, advertencias, origen="plantilla",
                               intentos=intento - 1, modelo=modelo, tokens_in=tokens_in,
                               tokens_out=tokens_out, latencia=latencia, verificado=True,
                               abs_tol=abs_tol, rel_tol=rel_tol)

        tokens_in += getattr(resp, "tokens_entrada", 0)
        tokens_out += getattr(resp, "tokens_salida", 0)
        latencia += getattr(resp, "latencia_s", 0.0)
        texto = (getattr(resp, "texto", "") or "").strip()

        ver = verificar_texto(texto, hechos, abs_tol=abs_tol, rel_tol=rel_tol)
        if ver.ok:
            return _empaquetar(texto, hechos, advertencias, origen="llm",
                               intentos=intento, modelo=modelo, tokens_in=tokens_in,
                               tokens_out=tokens_out, latencia=latencia, verificado=True,
                               abs_tol=abs_tol, rel_tol=rel_tol)

        ultimos_errores = ver.errores
        log.info("Verificador rechazó intento %d: %s", intento, ver.errores)
        if intento == 1:
            # Reintento: le damos la lista de errores para que corrija.
            mensaje = (
                _instruccion(resumen)
                + "\n\nTu respuesta anterior contenía cifras no verificables:\n- "
                + "\n- ".join(ver.errores)
                + "\n\nReescribe la explicación usando SOLO cifras presentes en el JSON."
            )

    # Dos fallos del verificador → plantilla determinista.
    advertencias.append(
        "El LLM no superó la verificación anti-alucinación; se usó la plantilla "
        f"determinista. Errores: {'; '.join(ultimos_errores[:3])}"
    )
    texto = explicar_plantilla(resultado, estilo, idioma)
    return _empaquetar(texto, hechos, advertencias, origen="plantilla",
                       intentos=2, modelo=modelo, tokens_in=tokens_in,
                       tokens_out=tokens_out, latencia=latencia, verificado=True,
                       abs_tol=abs_tol, rel_tol=rel_tol)


def _empaquetar(texto, hechos, advertencias, *, origen, intentos, modelo,
                tokens_in, tokens_out, latencia, verificado,
                abs_tol, rel_tol) -> dict:
    citados = hechos_citados_en(texto, hechos, abs_tol=abs_tol, rel_tol=rel_tol)
    return {
        "texto": texto,
        "hechos_citados": citados,
        "advertencias": advertencias,
        "uso": {
            "origen": origen,
            "intentos": intentos,
            "modelo": modelo,
            "tokens_entrada": tokens_in,
            "tokens_salida": tokens_out,
            "tokens_total": tokens_in + tokens_out,
            "latencia_s": round(latencia, 3),
            "verificado": verificado,
        },
    }
