"""Cliente Bedrock Converse; no contiene credenciales ni ejecuta código del LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ev_routing.search_policy import BedrockConfig

# Adaptación de los structure cards, observación/hipótesis/acción y separación
# de evidencia primal/dual de LLM4MIP. Procedencia y MIT: docs/llm4mip-adaptation.md.
SYSTEM_PROMPT = """You select implemented search policies for an electric-vehicle
routing MILP solved with GCG Dantzig-Wolfe branch-price-and-cut.
Return exactly one JSON object conforming to allowed_policy_schema.
Return policy VALUES, not the JSON schema, and do not wrap them in "policy".
Example: {"decomposition":"vehicle","cut_family":"original",
"cut_selection":"sparse","max_selected_cuts":20,
"pricing":"heuristic_then_exact","columns_per_round":50,
"pricing_heuristic_nodes":500,"stabilization":true,"rationale":"Brief hypothesis."}
Use the structure card and observed progress to identify the bottleneck:
feasibility, incumbent quality, dual bound, pricing cost, or separation cost.
Choose a falsifiable action and explain the observation and hypothesis briefly
in rationale. Distinguish evidence from assumptions. Never claim optimality,
infeasibility, valid bounds or absence of improving columns yourself.
vehicle convexifies each complete vehicle block; vehicle_routing convexifies
only movement/service-location constraints and keeps resource rows in master.
Moving resource rows to the master weakens or leaves unchanged the initial DW
relaxation; consider it for cheaper pricing, not inherently tighter bounds.
Changing decomposition is allowed only before the solve, when unlocked.
native cut_family leaves GCG settings unchanged; original uses GCG's original
space separation; original_basis also enables GCG's native basis separation.
Subset-row cuts are not offered: this convexification has continuous master
variables and GCG's subset-row separator requires a pure integer master.
cut_selection controls ranking of optional valid candidate cuts only.
pricing chooses native behavior, heuristic-then-exact, or exact-only search.
Never disable exact pricing, alter the model, H, tolerances, objectives, resource
budget or proof criteria. Do not output code, equations or arbitrary parameters.
"""


class BedrockResponseError(ValueError):
    """Conservar consumo incluso cuando una respuesta pagada no es utilizable."""

    def __init__(self, code: str, response: dict):
        super().__init__(code)
        self.code = code
        self.usage = response.get("usage", {})
        self.stop_reason = response.get("stopReason")


class BedrockPolicyClient:
    def __init__(self, config: BedrockConfig, *, client: Any = None, system_prompt: str = SYSTEM_PROMPT,
                 temperature: float | None = None, trace_directory: str | None = None):
        self.config, self.client = config, client
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.trace_directory = trace_directory

    def request_payload(self, request: dict[str, Any]) -> dict[str, Any]:
        """Cuerpo exacto de Converse; no contiene credenciales ni cabeceras."""
        text = json.dumps(request, ensure_ascii=False, allow_nan=False)
        if len(text.encode("utf-8")) > 40_000:
            raise ValueError("El perfil excede el límite de entrada de Bedrock")
        inference = {"maxTokens": self.config.max_output_tokens}
        # El razonamiento adaptativo de Claude Fable no admite temperature=0.
        # Al solicitar esfuerzo explícito se conserva el muestreo del proveedor.
        if self.temperature is not None and self.config.reasoning_effort is None:
            inference["temperature"] = self.temperature
        payload = {
            "modelId": self.config.model_id,
            "system": [{"text": self.system_prompt}],
            "messages": [{"role": "user", "content": [{"text": text}]}],
            "inferenceConfig": inference,
        }
        if self.config.reasoning_effort is not None:
            payload["additionalModelRequestFields"] = {
                "output_config": {"effort": self.config.reasoning_effort},
            }
        return payload

    def _trace(self, name: str, data: dict) -> None:
        if self.trace_directory:
            directory = Path(self.trace_directory)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / name).write_text(
                json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = self.request_payload(request)
        self._trace("llm-request.json", payload)
        if self.client is None:
            import boto3
            from botocore.config import Config

            session = boto3.Session(
                profile_name=self.config.profile, region_name=self.config.region,
            )
            self.client = session.client(
                "bedrock-runtime", region_name=self.config.region,
                config=Config(
                    connect_timeout=min(3, self.config.timeout_seconds),
                    read_timeout=self.config.timeout_seconds,
                    retries={"total_max_attempts": 1},
                ),
            )
        response = self.client.converse(**payload)
        # La respuesta del modelo, incluso inválida, permite diagnosticar fallback.
        # Omitir cabeceras HTTP y metadatos de transporte.
        self._trace("llm-response.json", {
            key: response.get(key) for key in ("output", "usage", "stopReason", "metrics")
        })
        if response.get("stopReason") not in {"end_turn", "stop_sequence"}:
            raise BedrockResponseError("incomplete_response", response)
        answer = "".join(
            block.get("text", "") for block in response["output"]["message"]["content"]
        )
        # Aceptar una envoltura Markdown sin interpretar nada como código.
        if answer.strip().startswith("```") and answer.strip().endswith("```"):
            answer = "\n".join(answer.strip().splitlines()[1:-1])
        try:
            policy = json.loads(answer)
        except (ValueError, TypeError) as error:
            raise BedrockResponseError("invalid_json", response) from error
        if not isinstance(policy, dict):
            raise BedrockResponseError("invalid_object", response)
        return {
            "policy": policy,
            "usage": response.get("usage", {}),
            "stop_reason": response.get("stopReason"),
        }
