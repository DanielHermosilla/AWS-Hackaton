"""Server-owned road contexts and bounded search configuration.

Only the operator supplies filesystem paths or AWS configuration. HTTP callers
select a supported policy and refer to prepared contexts by opaque identifiers.
"""

from __future__ import annotations

import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ev_routing.search_policy import DEFAULT_BEDROCK_MODEL, BedrockConfig, SearchConfig

from .service import ProviderError, SolveRequestError, fingerprint

if TYPE_CHECKING:
    from ev_routing.contracts import ProblemInstance
    from ev_routing.service_graph import PathArchive


@dataclass
class PreparedContext:
    instance: ProblemInstance
    road: ProblemInstance
    archive: PathArchive
    request: dict
    seconds: float
    instance_hash: str
    size: int
    energy_report: dict | None = None


class Runtime:
    def __init__(
        self, *, graphml=None, network_profile="delivery", max_snap_distance_m=100,
        log_directory="artifacts/webapp", max_contexts=2, max_context_bytes=384 * 1024 * 1024,
        tee=False,
    ):
        self.graphml = Path(graphml).resolve(strict=True) if graphml is not None else None
        self.network_profile = network_profile
        self.max_snap_distance_m = max_snap_distance_m
        self.log_directory = Path(log_directory)
        self.max_contexts = max_contexts
        self.max_context_bytes = max_context_bytes
        self.contexts = OrderedDict()
        self.tee = tee
        from .bedrock_session import BedrockSession
        from .history_store import HistoryStore

        self.bedrock = BedrockSession(BedrockConfig(
            model_id=os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL),
            region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            profile=os.getenv("AWS_PROFILE") or None,
        ))
        self.histories = HistoryStore(self.bedrock)

    def close(self):
        self.histories.close()
        self.bedrock.disconnect()
        self.contexts.clear()

    def prepare_road(self, nodes, parameters, rate, request):
        from ev_routing.contracts import ProblemInstance
        from ev_routing.energy import file_sha256
        from ev_routing.network import build_osm_instance
        from ev_routing.resource_graph import prepare_service_graph

        if self.graphml is None:
            raise SolveRequestError(
                "No hay una red vial configurada en el servidor. Inícielo con --graphml "
                "o seleccione explícitamente la aproximación sintética."
            )
        started = time.perf_counter()
        history_id = request.get("energy_profile_id")
        history_key = self.histories.cache_key(history_id) if history_id else None
        key = fingerprint({
            "request": request, "graph": file_sha256(self.graphml),
            "profile": self.network_profile, "snap_m": self.max_snap_distance_m,
            "historical_energy": history_key,
        })
        for identifier, (stored_key, context) in self.contexts.items():
            if stored_key == key:
                return identifier, context, True
        try:
            road = build_osm_instance(
                nodes, parameters, rate, graphml_path=self.graphml, allow_download=False,
                network_profile=self.network_profile,
                max_snap_distance_m=self.max_snap_distance_m, name="Instancia vial web",
            )
            road.provenance["energy_model"] = {
                "kind": "user_supplied_distance_rate", "kwh_per_km": rate,
                "limitations": ["Consumo supuesto explícito; no incluye pendiente ni tráfico."],
            }
            road = ProblemInstance.model_validate({
                **dict(road), "operations": request.get("operations", {}),
                "provenance": {
                    **road.provenance,
                    **({"scenario": request["scenario"]} if request.get("scenario") else {}),
                    "assumptions": [
                        *road.provenance.get("assumptions", []),
                        *(["Demanda e infraestructura simuladas a partir del caso de la hackatón."]
                          if request.get("scenario", {}).get("kind") == "hackathon_simulation" else []),
                    ],
                },
            })
            energy_report = None
            if history_id:
                road, energy_report = self.histories.apply(history_id, road, rate)
            pricing, archive = prepare_service_graph(road)
        except ValueError as exc:
            if "max_snap_distance_m" in str(exc):
                raise SolveRequestError(
                    "Una ubicación está fuera de la cobertura de calles disponible. "
                    "Revisa sus coordenadas o usa la aproximación por distancia para un ejemplo sintético."
                ) from exc
            raise SolveRequestError(f"No se pudo preparar la red vial: {exc}") from exc
        # Admission bound measured on serialized payloads, not an RSS guarantee.
        size = sum(len(item.model_dump_json().encode()) for item in (road, pricing, archive))
        if size > self.max_context_bytes:
            raise ProviderError(
                "El contexto vial excede el límite local. Use la CLI para esta red.",
                "context_too_large", 413,
            )
        while self.contexts and (
            len(self.contexts) >= self.max_contexts
            or sum(c.size for _, c in self.contexts.values()) + size > self.max_context_bytes
        ):
            self.contexts.popitem(last=False)
        identifier = str(uuid.uuid4())
        context = PreparedContext(
            pricing, road, archive, request, time.perf_counter() - started,
            fingerprint(pricing.model_dump(mode="json")), size, energy_report,
        )
        self.contexts[identifier] = (key, context)
        return identifier, context, False

    def get_context(self, identifier, instance):
        if not isinstance(identifier, str) or identifier not in self.contexts:
            raise SolveRequestError("La preparación vial expiró. Vuelva a preparar la entrada.")
        context = self.contexts[identifier][1]
        if fingerprint(instance) != context.instance_hash:
            raise SolveRequestError("La instancia no corresponde a la preparación vial indicada.")
        return context

    def search_config(self, policy, run_id):
        return SearchConfig(
            policy=policy,
            bedrock=self.bedrock.settings(BedrockConfig(
                model_id=os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL),
                region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
                profile=os.getenv("AWS_PROFILE") or None,
                reasoning_effort="low", max_output_tokens=2048, timeout_seconds=8,
            )),
            max_llm_calls=2, instance_context_bytes=8000,
            log_directory=str(self.log_directory / run_id / "logs"),
            show_llm_trace=self.tee,
        )

    def policy_provider(self, search):
        return self.bedrock.policy_provider(search.bedrock) if search.policy == "adaptive" else None
