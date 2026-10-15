"""Cliente central de Amazon Bedrock (API Converse).

Diseño:
- `boto3.Session` con `profile_name` configurable (o la cadena estándar de AWS).
- Cliente `bedrock-runtime` con timeouts (botocore `Config` connect/read) y
  reintentos acotados (modo "standard").
- `conversar(...)` registra latencia extremo a extremo y tokens (usage) y acepta
  system prompt, mensajes multi-turno, `toolConfig` (tool use) e imágenes.
- Ayudas de alto nivel: `preguntar` (texto→texto), `preguntar_json` (texto→dict
  validado) y `usar_herramienta` (fuerza una tool y devuelve sus argumentos).

Credenciales: NUNCA se imprimen ni registran. Los errores de modelo no disponible
(AccessDeniedException / ValidationException / ResourceNotFound) se normalizan a
`ModeloNoDisponible` para que el llamador decida (p. ej. degradar al asesor nulo).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Errores de botocore que significan "este modelo/perfil no es invocable aquí".
_CODIGOS_NO_DISPONIBLE = {
    "AccessDeniedException",
    "ValidationException",
    "ResourceNotFoundException",
}


class ErrorBedrock(RuntimeError):
    """Fallo genérico al invocar Bedrock."""


class ModeloNoDisponible(ErrorBedrock):
    """El modelo/perfil no está habilitado o no admite la operación.

    `codigo` guarda el código de error de botocore (AccessDeniedException, etc.).
    """

    def __init__(self, mensaje: str, codigo: str | None = None):
        super().__init__(mensaje)
        self.codigo = codigo


@dataclass
class RespuestaConverse:
    """Resultado normalizado de una llamada Converse."""

    texto: str
    bloques: list[dict] = field(default_factory=list)
    stop_reason: str | None = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    latencia_s: float = 0.0
    crudo: dict = field(default_factory=dict)

    @property
    def tokens_total(self) -> int:
        return self.tokens_entrada + self.tokens_salida

    def herramientas_usadas(self) -> list[dict]:
        """Bloques `toolUse` presentes en la respuesta: {toolUseId, name, input}."""
        return [b["toolUse"] for b in self.bloques if "toolUse" in b]


def extraer_json(texto: str) -> Any:
    """Extrae y parsea el primer objeto/array JSON de un texto.

    Tolera envoltorios habituales (``` ```json, prosa alrededor). Lanza
    `ValueError` si no hay JSON parseable.
    """
    if texto is None:
        raise ValueError("texto vacío")
    t = texto.strip()
    # Quitar vallas de código markdown.
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    # Intento directo.
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Buscar el primer { } o [ ] balanceado.
    for abre, cierra in (("{", "}"), ("[", "]")):
        ini = t.find(abre)
        fin = t.rfind(cierra)
        if 0 <= ini < fin:
            try:
                return json.loads(t[ini : fin + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no se encontró JSON válido en la respuesta")


def _bloque_imagen(datos: bytes, formato: str = "png") -> dict:
    """Construye un bloque de contenido de imagen para Converse."""
    return {"image": {"format": formato, "source": {"bytes": datos}}}


class ClienteBedrock:
    """Puerta única a `bedrock-runtime` Converse."""

    def __init__(
        self,
        region: str = "us-east-1",
        modelo: str = "us.anthropic.claude-sonnet-4-6",
        perfil: str | None = None,
        *,
        connect_timeout: float = 10.0,
        read_timeout: float = 60.0,
        max_reintentos: int = 2,
        cliente: Any | None = None,
    ):
        self.region = region
        self.modelo = modelo
        if cliente is not None:  # inyección para pruebas (fake / stubber)
            self.cliente = cliente
            return
        import boto3
        from botocore.config import Config

        cfg = Config(
            region_name=region,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            retries={"max_attempts": max_reintentos, "mode": "standard"},
        )
        sesion = boto3.Session(profile_name=perfil) if perfil else boto3.Session()
        self.cliente = sesion.client("bedrock-runtime", config=cfg)

    # ---- núcleo -----------------------------------------------------------
    def conversar(
        self,
        mensajes: list[dict],
        *,
        sistema: str | None = None,
        modelo: str | None = None,
        max_tokens: int = 1024,
        temperatura: float = 0.2,
        herramientas: list[dict] | None = None,
        forzar_herramienta: str | None = None,
    ) -> RespuestaConverse:
        """Invoca Converse. `mensajes` sigue el esquema Bedrock (role/content).

        Normaliza errores de disponibilidad a `ModeloNoDisponible` y el resto a
        `ErrorBedrock`. Registra latencia y tokens.
        """
        kwargs: dict[str, Any] = {
            "modelId": modelo or self.modelo,
            "messages": mensajes,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperatura},
        }
        if sistema:
            kwargs["system"] = [{"text": sistema}]
        if herramientas:
            tool_cfg: dict[str, Any] = {"tools": herramientas}
            if forzar_herramienta:
                tool_cfg["toolChoice"] = {"tool": {"name": forzar_herramienta}}
            kwargs["toolConfig"] = tool_cfg

        t0 = time.perf_counter()
        try:
            r = self.cliente.converse(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalizamos abajo
            codigo = _codigo_error(exc)
            latencia = time.perf_counter() - t0
            if codigo in _CODIGOS_NO_DISPONIBLE:
                raise ModeloNoDisponible(f"{codigo}: {exc}", codigo) from exc
            raise ErrorBedrock(f"Converse falló tras {latencia:.2f}s: {exc}") from exc
        latencia = time.perf_counter() - t0

        bloques = r.get("output", {}).get("message", {}).get("content", []) or []
        texto = "".join(b.get("text", "") for b in bloques if "text" in b)
        uso = r.get("usage", {}) or {}
        resp = RespuestaConverse(
            texto=texto,
            bloques=bloques,
            stop_reason=r.get("stopReason"),
            tokens_entrada=int(uso.get("inputTokens", 0)),
            tokens_salida=int(uso.get("outputTokens", 0)),
            latencia_s=latencia,
            crudo=r,
        )
        log.debug(
            "Bedrock %s: %.2fs, in=%d out=%d stop=%s",
            kwargs["modelId"], latencia, resp.tokens_entrada, resp.tokens_salida, resp.stop_reason,
        )
        return resp

    # ---- ayudas de alto nivel --------------------------------------------
    def preguntar(
        self,
        texto: str,
        *,
        sistema: str | None = None,
        imagenes: list[bytes] | None = None,
        formato_imagen: str = "png",
        **kw: Any,
    ) -> RespuestaConverse:
        """Un turno de usuario (texto + imágenes opcionales)."""
        contenido: list[dict] = []
        for img in imagenes or []:
            contenido.append(_bloque_imagen(img, formato_imagen))
        contenido.append({"text": texto})
        return self.conversar([{"role": "user", "content": contenido}], sistema=sistema, **kw)

    def preguntar_json(
        self,
        texto: str,
        *,
        sistema: str | None = None,
        imagenes: list[bytes] | None = None,
        **kw: Any,
    ) -> tuple[Any, RespuestaConverse]:
        """Pide salida JSON y la valida. Devuelve (objeto, respuesta).

        Lanza `ValueError` si el modelo no devuelve JSON parseable.
        """
        guia = ("Responde EXCLUSIVAMENTE con JSON válido, sin texto adicional "
                "ni vallas de código.")
        sis = f"{sistema}\n{guia}" if sistema else guia
        resp = self.preguntar(texto, sistema=sis, imagenes=imagenes, **kw)
        return extraer_json(resp.texto), resp

    def usar_herramienta(
        self,
        texto: str,
        herramienta: dict,
        *,
        sistema: str | None = None,
        **kw: Any,
    ) -> tuple[dict | None, RespuestaConverse]:
        """Fuerza una tool concreta y devuelve (argumentos, respuesta).

        `herramienta` es un `toolSpec` Bedrock: {toolSpec:{name, description,
        inputSchema:{json:{...}}}}. Devuelve los `input` de la primera llamada a
        la tool pedida, o None si el modelo no la invocó.
        """
        nombre = herramienta["toolSpec"]["name"]
        resp = self.preguntar(
            texto, sistema=sistema, herramientas=[herramienta], forzar_herramienta=nombre, **kw
        )
        for uso in resp.herramientas_usadas():
            if uso.get("name") == nombre:
                return uso.get("input"), resp
        return None, resp


def _codigo_error(exc: Exception) -> str | None:
    """Extrae el código de error de botocore sin importar botocore directamente."""
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        return resp.get("Error", {}).get("Code")
    return exc.__class__.__name__
