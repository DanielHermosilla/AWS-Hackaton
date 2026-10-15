"""Políticas de búsqueda acotadas: seleccionar acciones, nunca certificar."""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from time import monotonic
from typing import Any, Callable, Literal

from pydantic import Field, field_validator, model_validator

from ev_routing.contracts import Contract


class SearchPolicy(Contract):
    decomposition: Literal["vehicle", "vehicle_routing"] = "vehicle"
    cut_family: Literal["native", "original", "original_basis"] = "native"
    cut_selection: Literal["native", "efficacy", "sparse"] = "native"
    max_selected_cuts: int = Field(default=50, ge=1, le=200, strict=True)
    pricing: Literal["native", "heuristic_then_exact", "exact"] = "native"
    columns_per_round: int = Field(default=100, ge=1, le=500, strict=True)
    pricing_heuristic_nodes: int = Field(default=1000, ge=10, le=10000, strict=True)
    stabilization: bool = Field(default=True, strict=True)
    rationale: str = Field(default="", max_length=1500)


class BedrockConfig(Contract):
    model_id: str | None = Field(default=None, min_length=1)
    region: str = Field(default="us-east-1", min_length=1)
    profile: str | None = "hackathon"
    timeout_seconds: float = Field(default=8, gt=0, le=60)
    max_output_tokens: int = Field(default=700, ge=128, le=4096)

    @field_validator("model_id", mode="before")
    @classmethod
    def normalize_model_id(cls, value: Any) -> Any:
        # Una variable de shell sin definir se expande a "" al pasarla entre comillas.
        if isinstance(value, str):
            return value.strip() or None
        return value


class SearchConfig(Contract):
    policy: Literal["standard", "deterministic", "adaptive"] = "standard"
    bedrock: BedrockConfig = Field(default_factory=BedrockConfig)
    max_llm_calls: int = Field(default=4, ge=1, le=20, strict=True)
    decision_interval_seconds: float = Field(default=15, ge=0)
    min_pricing_calls_between_decisions: int = Field(default=10, ge=1, strict=True)
    llm_time_fraction: float = Field(default=.25, gt=0, le=.5)
    # Ruta local de logs; no se transmite al LLM.
    log_directory: str | None = None
    show_llm_trace: bool = False

    @model_validator(mode="after")
    def adaptive_requires_model(self):
        if self.policy == "adaptive" and not self.bedrock.model_id:
            raise ValueError(
                "Falta el modelo de Bedrock: --bedrock-model o BEDROCK_MODEL_ID "
                "está vacío o no definido. Indica --bedrock-model ID_MODELO_O_PERFIL "
                "o ejecuta export BEDROCK_MODEL_ID='ID_MODELO_O_PERFIL' antes del comando."
            )
        return self


def deterministic_policy(profile: dict[str, Any]) -> SearchPolicy:
    """Referencia explícita y reproducible, sin aprender de evaluation."""
    return SearchPolicy(
        decomposition="vehicle",
        cut_family="original",
        cut_selection="sparse",
        max_selected_cuts=20,
        pricing="heuristic_then_exact",
        columns_per_round=50,
        pricing_heuristic_nodes=500,
        rationale="Bloques completos por vehículo; limitar densidad y esfuerzo heurístico.",
    )


# El proveedor recibe exclusivamente un snapshot JSON sin objetos SCIP.
PolicyProvider = Callable[[dict[str, Any]], dict[str, Any]]


class SearchController:
    """Las llamadas remotas usan un trabajador; SCIP solo se toca en su hilo."""

    def __init__(self, config: SearchConfig, deadline: float, provider: PolicyProvider | None = None):
        self.config, self.deadline = config, deadline
        self.provider = provider
        self.policy = SearchPolicy()
        self.active_policy = "standard"
        self.started = monotonic()
        self.records: list[dict[str, Any]] = []
        self.calls = 0
        self.pricing_calls = 0
        self.cut_calls = 0
        self.candidate_cuts = 0
        self.selected_cuts = 0
        self.last_request = self.started
        self.last_pricing_request = 0
        self.phase = ""
        self.profile: dict[str, Any] = {}
        self.locked_decomposition: str | None = None
        self.pending: Future | None = None
        self.pool: ThreadPoolExecutor | None = None
        self.revision = 0
        if config.policy == "adaptive" and provider is None:
            from ev_routing.llm.bedrock import BedrockPolicyClient
            self.provider = BedrockPolicyClient(config.bedrock)

    def _request(self, event: str, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "event": event,
            "phase": self.phase,
            "structure": self.profile,
            "state": state,
            "current_policy": self.policy.model_dump(),
            "decomposition_locked": self.locked_decomposition,
            "remaining_wall_seconds": max(0, self.deadline - monotonic()),
            "allowed_policy_schema": SearchPolicy.model_json_schema(),
            "invariants": [
                "Same instance, H, objectives, integrality and feasibility tolerances.",
                "Exact native pricing stays enabled, including Farkas pricing.",
                "Only GCG-compatible native cuts; no generated code or inequalities.",
                "Bounds and proof status come exclusively from GCG.",
            ],
        }

    def _call(self, request: dict[str, Any]) -> dict[str, Any]:
        started = monotonic()
        try:
            result = self.provider(request)
            return {"request": request, "reply": result, "seconds": monotonic() - started}
        except Exception as error:
            from ev_routing.llm.bedrock import BedrockResponseError

            # No persistir errores de proveedores que podrían incluir credenciales.
            result = {
                "request": request, "error": type(error).__name__,
                "seconds": monotonic() - started,
            }
            if isinstance(error, BedrockResponseError):
                result.update(
                    error=error.code, reply={"usage": error.usage},
                    stop_reason=error.stop_reason,
                )
            return result

    def _receive(self, result: dict[str, Any], *, apply: bool = True) -> bool:
        reply = result.get("reply")
        record = {
            "event": result["request"]["event"],
            "phase": result["request"]["phase"],
            "elapsed_seconds": monotonic() - self.started,
            "runtime_seconds": result["seconds"],
            "usage": reply.get("usage") if isinstance(reply, dict) else None,
            "model_id": self.config.bedrock.model_id,
            "status": "error" if "error" in result else "received",
        }
        if "stop_reason" in result:
            record["stop_reason"] = result["stop_reason"]
        if "error" in result:
            record["reason"] = result["error"]
        else:
            try:
                proposal = SearchPolicy.model_validate(result["reply"]["policy"])
                record["proposal"] = proposal.model_dump()
                if not apply or result["request"]["phase"] != self.phase:
                    record.update(status="not_applied", reason="phase_finished")
                elif (
                    self.locked_decomposition is not None
                    and proposal.decomposition != self.locked_decomposition
                ):
                    record.update(status="rejected", reason="decomposition_locked_during_solve")
                else:
                    self.policy = proposal
                    self.active_policy = "adaptive"
                    self.revision += 1
                    record.update(status="applied", revision=self.revision)
            except (ValueError, KeyError, TypeError):
                record.update(status="rejected", reason="invalid_policy")
        self.records.append(record)
        return record["status"] == "applied"

    def start_phase(self, phase: str, profile: dict[str, Any]) -> None:
        self.collect(apply=False)
        self.phase, self.profile = phase, profile
        self.locked_decomposition = None
        if self.config.policy == "deterministic":
            self.policy = deterministic_policy(profile)
            self.active_policy = "deterministic"
        if (
            self.config.policy == "adaptive" and self.pending is None
            and self.calls < self.config.max_llm_calls
            and self.deadline - monotonic() > self.config.bedrock.timeout_seconds
        ):
            self.calls += 1
            self._receive(self._call(self._request("before_decomposition", {})))
            self.last_request = monotonic()
            self.last_pricing_request = self.pricing_calls
        self.locked_decomposition = self.policy.decomposition
        self.revision += 1

    def collect(self, *, apply: bool = True) -> bool:
        if self.pending is None or not self.pending.done():
            return False
        result, self.pending = self.pending.result(), None
        return self._receive(result, apply=apply)

    def observe(self, event: str, state: dict[str, Any]) -> None:
        self.collect()
        if self.config.policy != "adaptive":
            return
        now = monotonic()
        if (
            self.pending is not None or self.calls >= self.config.max_llm_calls
            or now - self.last_request < self.config.decision_interval_seconds
            or self.pricing_calls - self.last_pricing_request
            < self.config.min_pricing_calls_between_decisions
            or self.deadline - now <= self.config.bedrock.timeout_seconds
        ):
            return
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bedrock-policy")
        self.calls += 1
        self.last_request, self.last_pricing_request = now, self.pricing_calls
        # Copia profunda y comprobación de finitud antes de abandonar el hilo SCIP.
        request = json.loads(json.dumps(self._request(event, state), allow_nan=False))
        self.pending = self.pool.submit(self._call, request)

    def close(self) -> None:
        if self.pending is not None:
            # El cliente limita conexión/lectura y no reintenta. Se contabiliza
            # también el tiempo de una respuesta tardía, sin alterar un solve cerrado.
            self._receive(self.pending.result(), apply=False)
            self.pending = None
        if self.pool is not None:
            self.pool.shutdown(wait=True)

    def report(self) -> dict[str, Any]:
        applied = sum(record["status"] == "applied" for record in self.records)
        failures = any(record["status"] in {"error", "rejected"} for record in self.records)
        status = "disabled" if self.config.policy != "adaptive" else (
            "fallback" if not applied else "partial_fallback" if failures else "applied"
        )
        return {
            "policy": self.config.policy,
            "effective_policy": self.active_policy,
            "status": status,
            "calls": self.calls,
            "applied_decisions": applied,
            "model_id": self.config.bedrock.model_id if self.config.policy == "adaptive" else None,
            "region": self.config.bedrock.region,
            "aws_profile": self.config.bedrock.profile,
            "runtime_seconds": sum(record["runtime_seconds"] for record in self.records),
            "pricing_callbacks": self.pricing_calls,
            "cut_callbacks": self.cut_calls,
            "candidate_cuts": self.candidate_cuts,
            "policy_selected_cuts": self.selected_cuts,
            "decisions": self.records,
            "cost_estimate": None,
            "cost_reason": "No se configuró una tarifa verificada del modelo.",
        }
