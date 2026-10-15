"""Control por eventos entre etapas; SCIP y el checker conservan la autoridad."""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic

from ev_routing.route_policy import ROUTE_PROMPT, RoutePolicy, _save_decision
from ev_routing.scip_tuning import parameter_catalog, validate_parameters


class RouteOrchestrator:
    """Decisiones seriales acotadas, con política determinista ante fallos."""

    def __init__(self, config, profile, deadline, seconds, provider=None):
        self.config, self.profile, self.deadline = config, profile, deadline
        self.provider = provider
        self.policy = RoutePolicy()
        if config.policy == "deterministic":
            self.policy = RoutePolicy(seed_starts=12, pricing_heuristic_starts=8)
        self.started = monotonic()
        self.inference_budget = seconds * config.llm_time_fraction
        self.records = []
        self.skipped = []
        self.runtime = 0.0
        self.last_call = -float("inf")
        self.single_tour = profile.get("single_tour_certificate", {}).get("applicable", False)

    def decide(self, event, state):
        now = monotonic()
        if self.config.policy != "adaptive" or len(self.records) >= self.config.max_llm_calls:
            return self.policy
        if event == "search_stagnation" and now - self.last_call < self.config.decision_interval_seconds:
            return self.policy
        available = min(self.deadline - now, self.inference_budget - self.runtime)
        if available <= self.config.bedrock.timeout_seconds + 1:
            self.skipped.append({"event": event, "reason": "insufficient_inference_budget"})
            return self.policy
        # Catálogo compacto: todos los nombres propuestos se contrastan además con SCIP.
        catalog = parameter_catalog(self.single_tour)
        preferred = {
            "lp/initalgorithm", "lp/resolvealgorithm", "lp/pricing", "lp/scaling",
            "lp/colagelimit", "lp/rowagelimit", "lp/cleanupcols", "lp/cleanuprows",
            "branching/relpscost/maxreliable", "branching/relpscost/inititer",
            "branching/relpscost/sbiterquot", "branching/relpscost/sbiterofs",
            "nodeselection/estimate/stdpriority", "nodeselection/dfs/stdpriority",
            "nodeselection/bfs/stdpriority", "nodeselection/uct/stdpriority",
        }
        parameters = {
            k: v for k, v in catalog["parameters_and_defaults"].items()
            if k in preferred or (k.startswith("heuristics/") and k.endswith("/freq"))
        }
        mutable = set(RoutePolicy.model_fields)
        if self.single_tour:
            mutable = {
                "subtour_batch_size", "branching", "heuristics", "presolve",
                "separation", "scip_parameters", "rationale",
            }
        elif event != "before_search":
            mutable -= {"seed_starts", "charging_seed_starts", "seed_time_fraction"}
            if event == "search_stagnation":
                mutable -= {
                    "share_vehicle_oracles", "bound_strategy", "bound_time_fraction",
                    "subtour_batch_size", "presolve", "separation",
                }
                if state.get("phase") == "energy":
                    mutable.discard("deliveries_time_fraction")
        schema = RoutePolicy.model_json_schema()
        schema["properties"] = {k: v for k, v in schema["properties"].items() if k in mutable}
        request = {
            "event": event, "phase": state.get("phase", "planning"),
            "structure": self.profile, "state": state,
            "remaining_wall_seconds": max(0, self.deadline - now),
            "remaining_calls": self.config.max_llm_calls - len(self.records),
            "current_policy": self.policy.model_dump(),
            "allowed_policy_schema": schema, "mutable_policy_fields": sorted(mutable),
            "native_scip_catalog": {**catalog, "parameters_and_defaults": parameters},
        }
        before = self.policy.model_dump()
        record = {
            "event": event, "phase": request["phase"], "elapsed_seconds": now - self.started,
            "model_id": self.config.bedrock.model_id, "region": self.config.bedrock.region,
            "state": state, "before_policy": before, "usage": None,
        }
        directory = None
        if self.config.log_directory:
            directory = Path(self.config.log_directory) / "decisions" / f"{len(self.records)+1:02d}-{event}"
        started = monotonic()
        try:
            provider = self.provider
            if provider is None:
                from ev_routing.llm.bedrock import BedrockPolicyClient
                provider = BedrockPolicyClient(
                    self.config.bedrock, system_prompt=ROUTE_PROMPT, temperature=0,
                    trace_directory=str(directory) if directory else None,
                )
            if directory:
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "state.json").write_text(
                    json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                )
            response = provider(request)
            record["usage"] = response.get("usage")
            # Validar también campos inactivos: no tolerar datos/código desconocidos.
            requested = RoutePolicy.model_validate({**before, **response["policy"]})
            inactive = {
                k: v for k, v in requested.model_dump().items()
                if k not in mutable and v != before[k]
            }
            proposal = RoutePolicy.model_validate({
                **before, **{k: v for k, v in requested.model_dump().items() if k in mutable},
            })
            proposal.scip_parameters = validate_parameters(proposal.scip_parameters, self.single_tour)
            if monotonic() >= self.deadline:
                record.update(status="not_applied", reason="global_deadline")
            else:
                self.policy = proposal
                after = proposal.model_dump()
                record.update(
                    status="applied", proposal=after,
                    inactive_settings=inactive,
                    mutable_policy_fields=sorted(mutable),
                    effective_changes={
                        key: {"before": before[key], "after": value}
                        for key, value in after.items() if value != before[key] and key != "rationale"
                    },
                )
        except Exception as error:
            from ev_routing.llm.bedrock import BedrockResponseError
            record.update(status="rejected", reason=type(error).__name__)
            if isinstance(error, BedrockResponseError):
                record.update(reason=error.code, usage=error.usage)
        record["runtime_seconds"] = monotonic() - started
        self.runtime += record["runtime_seconds"]
        self.last_call = monotonic()
        self.records.append(record)
        if self.config.show_llm_trace:
            print("[ORCHESTRATOR] " + json.dumps(record, ensure_ascii=False, allow_nan=False), flush=True)
        _save_decision(self.config, self.report())
        return self.policy

    def report(self):
        applied = sum(r["status"] == "applied" for r in self.records)
        failed = any(r["status"] != "applied" for r in self.records)
        status = self.config.policy
        if self.config.policy == "standard":
            status = "disabled"
        elif self.config.policy == "adaptive":
            status = "fallback" if not applied else "partial_fallback" if failed else "adaptive"
        return {
            "requested_policy": self.config.policy,
            "active_policy": self.config.policy if applied or self.config.policy != "adaptive" else "standard",
            "status": status, "calls": len(self.records), "applied_decisions": applied,
            "decisions": self.records, "skipped_events": self.skipped,
            "runtime_seconds": self.runtime, "inference_budget_seconds": self.inference_budget,
            "callback_calls": 0, "policy": self.policy.model_dump(),
        }
