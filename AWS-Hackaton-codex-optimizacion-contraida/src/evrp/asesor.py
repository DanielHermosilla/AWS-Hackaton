"""Capa opcional de IA generativa (asesor).

El motor nunca depende del asesor: el asesor nulo es el valor por defecto, y todo lo
que proponga un LLM se filtra (lista blanca de claves) y pasa por el validador.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

# Únicas claves de configuración que el asesor puede modificar, con sus valores válidos.
AJUSTES_PERMITIDOS = {
    ("pipeline", "cargadores"): {"todos", "dominancia", "top_r"},
    ("cargadores", "top_r"): range(1, 11),
    ("solver", "tiempo_limite_s"): range(1, 601),
}


class Asesor(ABC):
    nombre = "abstracto"

    @abstractmethod
    def sugerir_config(self, resumen_instancia: dict, cfg: dict) -> dict:
        """Devuelve ajustes {seccion: {clave: valor}}; vacío si no propone nada."""

    @abstractmethod
    def explicar(self, resultado: dict) -> str | None:
        """Texto en lenguaje natural que explica la solución, o None."""


class AsesorNulo(Asesor):
    nombre = "ninguno"

    def sugerir_config(self, resumen_instancia, cfg):
        return {}

    def explicar(self, resultado):
        return None


def filtrar_ajustes(propuesta: dict) -> dict:
    """Descarta cualquier ajuste fuera de la lista blanca."""
    limpio: dict = {}
    for (sec, clave), validos in AJUSTES_PERMITIDOS.items():
        v = (propuesta or {}).get(sec, {}).get(clave)
        if v is not None and v in validos:
            limpio.setdefault(sec, {})[clave] = v
    return limpio


class AsesorBedrock(Asesor):
    """Amazon Bedrock vía el cliente central `evrp.ia.ClienteBedrock` (extra "ia").

    Credenciales: la cadena estándar de AWS (perfil/SSO, variables de entorno o rol).
    El asesor nunca rompe el motor: cualquier fallo degrada a vacío/None.
    """

    nombre = "bedrock"

    def __init__(self, region: str, modelo: str, perfil: str | None = None, cliente=None):
        from .ia import ClienteBedrock  # dependencia opcional (extra "ia")

        self.cliente = cliente or ClienteBedrock(region=region, modelo=modelo, perfil=perfil)
        self.modelo = modelo

    def sugerir_config(self, resumen_instancia, cfg):
        sistema = ("Eres un experto en ruteo de vehículos eléctricos y MILP. Responde SOLO con un objeto "
                   "JSON con ajustes de configuración, usando únicamente estas claves: "
                   + json.dumps([f"{s}.{k}" for s, k in AJUSTES_PERMITIDOS]))
        texto = json.dumps({"instancia": resumen_instancia, "config_actual": {
            "pipeline": cfg["pipeline"], "cargadores": cfg["cargadores"], "solver": cfg["solver"]}},
            ensure_ascii=False)
        try:
            propuesta, _ = self.cliente.preguntar_json(texto, sistema=sistema, max_tokens=300)
            return filtrar_ajustes(propuesta if isinstance(propuesta, dict) else {})
        except Exception as exc:  # el asesor nunca debe romper el motor
            log.warning("Asesor Bedrock no disponible para sugerir: %s", exc)
            return {}

    def explicar(self, resultado):
        sistema = ("Eres el asistente de una jefa de flota. Explica en español, breve y claro, qué hace "
                   "cada vehículo, dónde recarga y por qué, y qué entregas quedan pendientes. No inventes "
                   "datos: usa solo el JSON entregado.")
        try:
            resp = self.cliente.preguntar(json.dumps(resultado, ensure_ascii=False), sistema=sistema)
            return resp.texto or None
        except Exception as exc:
            log.warning("Asesor Bedrock no disponible para explicar: %s", exc)
            return None


def crear_asesor(cfg: dict) -> Asesor:
    a = cfg["asesor"]
    if a["tipo"] == "bedrock":
        try:
            return AsesorBedrock(a["region"], a["modelo"], a.get("perfil_aws"))
        except Exception as exc:
            log.warning("No se pudo crear el asesor Bedrock (%s); se usa el nulo", exc)
    return AsesorNulo()
