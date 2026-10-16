"""Cliente Bedrock Converse para el asistente conversacional (eje A/C).

Separado a propósito de ``ev_routing.llm.bedrock`` (que solo emite decisiones
JSON para el tuning del solver). Aqui necesitamos el ciclo conversacional
completo con tool use y, opcionalmente, streaming.

Degradacion segura: cualquier fallo de red/credenciales/modelo se traduce en
una excepcion controlada (``ErrorBedrock`` o ``ModeloNoDisponible``). El motor
nunca depende de este modulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

# Modelo por defecto: Claude Sonnet via cross-region inference profile (prefijo
# "us."). Haiku/Nova para abaratar. Se puede sobrescribir por configuracion.
MODELO_POR_DEFECTO = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

# Limites explicitos (nunca implicitos): acotan costo y latencia de la demo.
MAX_TOKENS_CHAT = 800
TEMPERATURA = 0.2


class ErrorBedrock(RuntimeError):
    """Fallo recuperable al invocar Bedrock (red, throttling, respuesta mala)."""


class ModeloNoDisponible(ErrorBedrock):
    """El modelo/credenciales/region no permiten invocar (degradar sin romper)."""


@dataclass
class EventoStream:
    """Fragmento emitido durante ConverseStream."""

    tipo: str  # "texto" | "tool_use" | "fin" | "error"
    texto: str = ""
    datos: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfigBedrock:
    """Parametros de conexion; perfil/region opcionales (usa el entorno)."""

    model_id: str = MODELO_POR_DEFECTO
    region: str | None = None
    profile: str | None = None
    max_tokens: int = MAX_TOKENS_CHAT
    temperature: float = TEMPERATURA


class ClienteBedrock:
    """Envoltura delgada sobre bedrock-runtime (Converse / ConverseStream).

    No se construye el cliente boto3 hasta la primera llamada, para que importar
    este modulo no exija tener boto3 instalado ni credenciales configuradas.
    """

    def __init__(self, config: ConfigBedrock | None = None) -> None:
        self.config = config or ConfigBedrock()
        self._cliente = None  # perezoso

    def _asegurar_cliente(self) -> Any:
        if self._cliente is not None:
            return self._cliente
        try:
            import boto3  # import local: dependencia opcional (extra "assist")
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - entorno sin boto3
            raise ModeloNoDisponible(
                "boto3 no esta instalado; instala el extra 'assist' para el chat"
            ) from exc
        try:
            session = boto3.Session(
                profile_name=self.config.profile, region_name=self.config.region
            )
            self._cliente = session.client(
                "bedrock-runtime",
                config=Config(retries={"max_attempts": 2, "mode": "standard"}),
            )
        except Exception as exc:  # credenciales/region ausentes
            raise ModeloNoDisponible(str(exc)) from exc
        return self._cliente

    def conversar(
        self,
        mensajes: list[dict],
        *,
        sistema: str,
        tool_config: dict | None = None,
    ) -> dict:
        """Una vuelta de Converse. Devuelve la respuesta cruda de Bedrock."""
        cliente = self._asegurar_cliente()
        kwargs: dict[str, Any] = {
            "modelId": self.config.model_id,
            "messages": mensajes,
            "system": [{"text": sistema}],
            "inferenceConfig": {
                "maxTokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            },
        }
        if tool_config:
            kwargs["toolConfig"] = tool_config
        try:
            return cliente.converse(**kwargs)
        except Exception as exc:  # pragma: no cover - depende de red real
            raise ErrorBedrock(str(exc)) from exc

    def conversar_stream(
        self,
        mensajes: list[dict],
        *,
        sistema: str,
        tool_config: dict | None = None,
    ) -> Iterator[EventoStream]:
        """ConverseStream: emite EventoStream a medida que llega el texto."""
        cliente = self._asegurar_cliente()
        kwargs: dict[str, Any] = {
            "modelId": self.config.model_id,
            "messages": mensajes,
            "system": [{"text": sistema}],
            "inferenceConfig": {
                "maxTokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            },
        }
        if tool_config:
            kwargs["toolConfig"] = tool_config
        try:
            respuesta = cliente.converse_stream(**kwargs)
            for evento in respuesta.get("stream", []):
                if "contentBlockDelta" in evento:
                    delta = evento["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        yield EventoStream("texto", texto=delta["text"])
                elif "messageStop" in evento:
                    yield EventoStream("fin", datos=evento["messageStop"])
        except Exception as exc:  # pragma: no cover - depende de red real
            yield EventoStream("error", datos={"mensaje": str(exc)})
