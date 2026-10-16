"""Cliente Bedrock Converse para el asistente conversacional.

Separado de ``ev_routing.llm.bedrock`` (que solo emite decisiones JSON para el
tuning del solver), pero con la MISMA politica de modelo y parametros:

- Modelo: ``ASSIST_MODEL_ID`` > ``BEDROCK_MODEL_ID`` > el modelo permitido del
  proyecto (``search_policy.DEFAULT_BEDROCK_MODEL``).
- Modelos GPT de razonamiento: sin ``temperature`` y con
  ``additionalModelRequestFields.reasoning.effort`` (igual que el motor).
- Credenciales: las del entorno del servidor (``AWS_PROFILE``, region en
  ``AWS_DEFAULT_REGION``). Nunca vienen del navegador.

Degradacion segura: cualquier fallo se traduce en ``ErrorBedrock`` o
``ModeloNoDisponible``; quien llama decide el fallback. El motor nunca depende
de este modulo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:  # misma constante que usa el motor; fallback si se importa aislado
    from ev_routing.search_policy import DEFAULT_BEDROCK_MODEL as _MODELO_PROYECTO
except Exception:  # pragma: no cover - entorno sin el nucleo
    _MODELO_PROYECTO = "us.openai.gpt-5.6-luna"

MAX_TOKENS_CHAT = 1200
TEMPERATURA = 0.2
ESFUERZO_RAZONAMIENTO = "low"
TIMEOUT_LECTURA_S = 25
TIMEOUT_CONEXION_S = 3


class ErrorBedrock(RuntimeError):
    """Fallo recuperable al invocar Bedrock (red, throttling, respuesta mala)."""


class ModeloNoDisponible(ErrorBedrock):
    """Sin boto3, credenciales o region: degradar sin romper."""


def _modelo_por_defecto() -> str:
    return os.getenv("ASSIST_MODEL_ID") or os.getenv("BEDROCK_MODEL_ID") or _MODELO_PROYECTO


def es_gpt_razonamiento(model_id: str) -> bool:
    """Misma regla que ``BedrockConfig.is_openai_reasoning_model``."""
    return "openai.gpt-" in model_id and "openai.gpt-oss-" not in model_id


@dataclass
class ConfigBedrock:
    model_id: str = field(default_factory=_modelo_por_defecto)
    region: str | None = field(default_factory=lambda: os.getenv("AWS_DEFAULT_REGION"))
    profile: str | None = None  # None: boto3 usa AWS_PROFILE del entorno
    max_tokens: int = MAX_TOKENS_CHAT
    temperature: float = TEMPERATURA


class ClienteBedrock:
    """Envoltura delgada de bedrock-runtime Converse.

    El cliente boto3 se crea en la primera llamada: importar este modulo no
    exige boto3 ni credenciales.
    """

    def __init__(self, config: ConfigBedrock | None = None) -> None:
        self.config = config or ConfigBedrock()
        self._cliente = None

    def _asegurar_cliente(self) -> Any:
        if self._cliente is not None:
            return self._cliente
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - entorno sin boto3
            raise ModeloNoDisponible("boto3 no esta instalado (extra 'assist' o 'dw').") from exc
        try:
            session = boto3.Session(
                profile_name=self.config.profile, region_name=self.config.region
            )
            if session.get_credentials() is None:
                raise ModeloNoDisponible("No hay credenciales AWS en el servidor.")
            self._cliente = session.client(
                "bedrock-runtime",
                region_name=self.config.region or session.region_name or "us-east-1",
                config=Config(
                    connect_timeout=TIMEOUT_CONEXION_S,
                    read_timeout=TIMEOUT_LECTURA_S,
                    retries={"total_max_attempts": 2, "mode": "standard"},
                ),
            )
        except ModeloNoDisponible:
            raise
        except Exception as exc:
            raise ModeloNoDisponible(str(exc)) from exc
        return self._cliente

    def _payload(self, mensajes: list[dict], sistema: str, tool_config: dict | None) -> dict:
        inferencia: dict[str, Any] = {"maxTokens": self.config.max_tokens}
        payload: dict[str, Any] = {
            "modelId": self.config.model_id,
            "messages": mensajes,
            "system": [{"text": sistema}],
            "inferenceConfig": inferencia,
        }
        if es_gpt_razonamiento(self.config.model_id):
            payload["additionalModelRequestFields"] = {
                "reasoning": {"effort": ESFUERZO_RAZONAMIENTO}
            }
        else:
            inferencia["temperature"] = self.config.temperature
        if tool_config:
            payload["toolConfig"] = tool_config
        return payload

    def conversar(
        self, mensajes: list[dict], *, sistema: str, tool_config: dict | None = None
    ) -> dict:
        """Una vuelta de Converse. Devuelve la respuesta cruda de Bedrock."""
        cliente = self._asegurar_cliente()
        try:
            return cliente.converse(**self._payload(mensajes, sistema, tool_config))
        except Exception as exc:  # pragma: no cover - depende de red real
            raise ErrorBedrock(str(exc)) from exc
