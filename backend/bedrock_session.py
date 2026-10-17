"""Local-only, ephemeral AWS connection shared by history analysis and tuning.

Credentials never enter a problem/search contract, file, environment variable
or response. The session owns SDK clients; an epoch prevents a provider captured
before disconnect/reconnect from starting another request.
"""

from __future__ import annotations

import threading
from time import monotonic
from typing import Callable, Literal

from pydantic import Field, SecretStr, ValidationError, model_validator

from ev_routing.contracts import Contract
from ev_routing.llm.bedrock import (
    BedrockPolicyClient, BedrockResponseError, create_bedrock_client, supports_high_reasoning,
)
from ev_routing.llm.history import (
    HISTORY_PROMPT, MAX_INPUT_BYTES, MAX_OUTPUT_TOKENS, analyze_history_profile,
)
from ev_routing.search_policy import BedrockConfig


class BedrockSessionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ConnectionRequest(Contract):
    mode: Literal["configured", "temporary"]
    region: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$", max_length=40)
    model_id: str | None = Field(default=None, min_length=1, max_length=2048)
    profile: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.@+-]+$", max_length=128)
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None
    session_token: SecretStr | None = None

    @model_validator(mode="after")
    def credentials_are_complete(self):
        values = (self.access_key_id, self.secret_access_key, self.session_token)
        if self.mode == "temporary":
            if self.profile is not None or any(value is None or not value.get_secret_value().strip()
                                               for value in values):
                raise ValueError("Temporary credentials require all three fields")
            if any(len(value.get_secret_value()) > 8192 for value in values):
                raise ValueError("Credential exceeds local limit")
        elif any(value is not None for value in values):
            raise ValueError("Configured mode never accepts credential fields")
        return self


def _safe_error(error: Exception) -> BedrockSessionError:
    if isinstance(error, BedrockSessionError):
        return error
    name = type(error).__name__
    # Never inspect or interpolate a provider's error message: it may contain
    # request details, credentials, or untrusted source values.
    code = getattr(error, "response", {}).get("Error", {}).get("Code", name)
    if code in {"NoCredentialsError", "PartialCredentialsError", "ProfileNotFound"}:
        return BedrockSessionError("missing_credentials", "Conecta AWS con un perfil válido o credenciales temporales.")
    if code in {"ExpiredTokenException", "ExpiredToken", "TokenRefreshRequired",
                "UnauthorizedSSOTokenError", "SSOTokenLoadError", "InvalidClientTokenId",
                "UnrecognizedClientException", "InvalidSignatureException"}:
        return BedrockSessionError("expired", "La sesión de AWS venció o no es válida. Vuelve a conectarla.")
    if code in {"AccessDeniedException", "AccessDenied"}:
        return BedrockSessionError("access_denied", "AWS no permite usar este modelo. Revisa sus permisos, región y acceso.")
    if code in {"ValidationException", "ResourceNotFoundException"}:
        return BedrockSessionError(
            "model_unavailable", "Este modelo o su configuración no está disponible en la región elegida.")
    if code in {"ThrottlingException", "ServiceQuotaExceededException"}:
        return BedrockSessionError("rate_limited", "AWS alcanzó el límite de uso. Espera un momento y vuelve a intentarlo.")
    if code in {"ConnectTimeoutError", "ReadTimeoutError", "EndpointConnectionError"}:
        return BedrockSessionError("connection_error", "No se pudo contactar con AWS. Revisa la conexión y la región.")
    return BedrockSessionError("connection_error", "No se pudo completar la conexión con AWS. Revisa sus datos y permisos.")


class BedrockSession:
    def __init__(
        self, config: BedrockConfig | None = None, *, ttl_seconds: float = 3600,
        session_factory: Callable | None = None, clock: Callable = monotonic,
    ):
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("ttl_seconds must be between 1 and 3600")
        self._base = config or BedrockConfig(profile=None)
        self._settings = self._base.model_copy()
        self._session_factory = session_factory
        self._clock, self._ttl = clock, ttl_seconds
        self._lock = threading.RLock()
        self._request_lock = threading.Lock()
        self._session = None
        self._clients = {}
        self._epoch = 0
        self._expires = None
        self._mode = "configured"
        self._state = "configured_unverified"
        self._message = "AWS está configurado; el acceso al modelo se comprobará al usarlo."
        self._connected = False
        self._explicit_connection = False

    def __repr__(self):
        return f"<BedrockSession state={self._state!r}>"

    def _expire(self):
        if self._expires is not None and self._clock() >= self._expires:
            self._clear("expired", "La conexión temporal venció. Vuelve a conectar AWS.")

    def _clear(self, state, message):
        self._epoch += 1
        self._session = None
        self._clients.clear()
        self._expires = None
        self._connected = False
        self._state, self._message = state, message

    def status(self) -> dict:
        """Read-only local status. Never initializes an SDK or makes a request."""
        with self._lock:
            self._expire()
            return {
                "state": self._state, "connected": self._connected, "mode": self._mode,
                "region": self._settings.region, "model_id": self._settings.model_id,
                "profile": self._settings.profile if self._mode == "configured" else None,
                "reasoning_effort": "high",
                "expires_in_seconds": (max(0, round(self._expires - self._clock()))
                                       if self._expires is not None else None),
                "message": self._message,
            }

    def settings(self, base_config: BedrockConfig | None = None, *, high=False) -> BedrockConfig:
        """Serializable non-secret settings. Connection identity overrides the caller."""
        with self._lock:
            self._expire()
            identity = self._settings if self._explicit_connection or base_config is None else base_config
            config = (base_config or self._base).model_copy(update={
                "region": identity.region, "model_id": identity.model_id,
                "profile": identity.profile if self._mode == "configured" else None,
            })
        if high:
            if not supports_high_reasoning(config.model_id):
                raise BedrockSessionError(
                    "unsupported_reasoning_model",
                    "Elige un modelo de Bedrock compatible con razonamiento HIGH para analizar históricos.",
                )
            config = config.model_copy(update={
                "reasoning_effort": "high", "max_output_tokens": MAX_OUTPUT_TOKENS,
                "max_input_bytes": MAX_INPUT_BYTES, "timeout_seconds": 60,
            })
        return config

    def _new_session(self, settings, request=None):
        factory = self._session_factory
        if factory is None:
            import boto3
            factory = boto3.Session
        kwargs = {"region_name": settings.region}
        if request is not None and request.mode == "temporary":
            kwargs.update(
                aws_access_key_id=request.access_key_id.get_secret_value(),
                aws_secret_access_key=request.secret_access_key.get_secret_value(),
                aws_session_token=request.session_token.get_secret_value(),
            )
        else:
            kwargs["profile_name"] = settings.profile
        return factory(**kwargs)

    def connect(self, payload: dict) -> dict:
        try:
            request = ConnectionRequest.model_validate(payload)
        except (ValidationError, TypeError, ValueError):
            raise BedrockSessionError(
                "invalid_connection",
                "Revisa la región, el modelo y los campos de conexión. Las credenciales temporales necesitan sus tres valores.",
            ) from None
        settings = self._base.model_copy(update={
            "region": request.region or self._base.region,
            "model_id": request.model_id or self._base.model_id,
            "profile": (request.profile or self._base.profile) if request.mode == "configured" else None,
            "reasoning_effort": "high", "max_output_tokens": 128, "timeout_seconds": 30,
        })
        if not supports_high_reasoning(settings.model_id):
            raise BedrockSessionError(
                "unsupported_reasoning_model",
                "Elige un modelo compatible con razonamiento HIGH. No se reducirá el nivel de análisis.",
            )
        if not self._request_lock.acquire(blocking=False):
            raise BedrockSessionError("bedrock_busy", "Hay una consulta a AWS en curso. Espera a que termine.")
        # Disconnect may run while the network request is in flight. Its epoch
        # must win; a late probe must not resurrect the session.
        with self._lock:
            epoch = self._epoch
        try:
            session = self._new_session(settings, request)
            client = create_bedrock_client(settings, session=session)
            probe = BedrockPolicyClient(
                settings, system_prompt='Return exactly {"connected":true}.',
            ).request_payload({"task": "connection_check"})
            response = client.converse(**probe)
            with self._lock:
                if epoch != self._epoch:
                    raise BedrockSessionError("disconnected", "Conecta AWS de nuevo para continuar.")
                self._clear("connected", "AWS conectado. El análisis histórico usará razonamiento HIGH.")
                self._session, self._settings, self._mode = session, settings, request.mode
                self._explicit_connection = True
                self._connected = True
                self._expires = self._clock() + self._ttl
                state = self.status()
                state["usage"] = _usage(response.get("usage"))
                return state
        except Exception as error:
            safe = _safe_error(error)
            with self._lock:
                if epoch == self._epoch:
                    self._clear(safe.code, str(safe))
            raise safe from None
        finally:
            self._request_lock.release()

    def disconnect(self) -> dict:
        with self._lock:
            self._clear("disconnected", "AWS desconectado. Puedes continuar con el consumo supuesto.")
            return self.status()

    def _client(self, config, epoch):
        with self._lock:
            self._expire()
            if self._epoch != epoch or self._state in {
                "expired", "disconnected", "access_denied", "missing_credentials",
                "model_unavailable", "connection_error", "rate_limited",
            }:
                raise BedrockSessionError("disconnected", "Conecta AWS de nuevo para continuar.")
            if self._session is None:
                self._session = self._new_session(config)
                self._settings = config.model_copy()
                self._expires = self._clock() + self._ttl
            key = (config.region, config.timeout_seconds)
            if key not in self._clients:
                self._clients[key] = create_bedrock_client(config, session=self._session)
            return self._clients[key]

    def _provider(self, config, system_prompt):
        with self._lock:
            self._expire()
            epoch = self._epoch

        def request(profile):
            if not self._request_lock.acquire(blocking=False):
                raise BedrockSessionError("bedrock_busy", "Hay una consulta a AWS en curso. Espera a que termine.")
            try:
                client = self._client(config, epoch)
                result = BedrockPolicyClient(
                    config, client=client, system_prompt=system_prompt,
                    trace_directory=None, show_trace=False,
                )(profile)
                with self._lock:
                    if self._epoch == epoch:
                        self._connected, self._state = True, "connected"
                        self._message = "AWS conectado. El análisis histórico usará razonamiento HIGH."
                return result
            except BedrockResponseError:
                # A malformed paid response still records its usage and stops
                # the extraction; it is not an authentication failure.
                raise
            except Exception as error:
                safe = _safe_error(error)
                with self._lock:
                    if self._epoch == epoch and safe.code != "bedrock_busy":
                        self._clear(safe.code, str(safe))
                raise safe from None
            finally:
                self._request_lock.release()
        return request

    def policy_provider(self, config: BedrockConfig | None = None):
        from ev_routing.route_policy import ROUTE_PROMPT

        return self._provider(self.settings(config), ROUTE_PROMPT)

    def history_provider(self, config: BedrockConfig | None = None):
        return self._provider(self.settings(config, high=True), HISTORY_PROMPT)

    def analyze(self, profile: dict) -> dict:
        settings = self.settings(high=True)
        return analyze_history_profile(profile, config=settings, provider=self.history_provider(settings))


def _usage(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("inputTokens", "outputTokens", "totalTokens",
                                       "cacheReadInputTokens", "cacheWriteInputTokens")
            if type(value.get(key)) is int and value[key] >= 0}
