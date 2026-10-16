"""Cabeza LLM asíncrona: snapshots JSON al trabajador, decisiones en el hilo SCIP."""

from __future__ import annotations

import hashlib
import inspect
import json
from concurrent.futures import Future
from pathlib import Path
from threading import Thread
from time import monotonic

from pyscipopt import Model

from ev_routing.route_policy import ROUTE_PROMPT, RoutePolicy, _save_decision
from ev_routing.scip_tuning import parameter_catalog, validate_parameters

API_GROUPS = {
    "pricing": ["includePricer", "addVar", "addConsCoeff", "getDualsolLinear", "getDualfarkasLinear"],
    "branching": ["includeBranchrule", "getLPBranchCands", "branchVar", "getVarPseudocost"],
    "nodes": ["includeNodesel", "getOpenNodes", "getBestboundNode", "getPrioChild"],
    "separation": ["includeSepa", "addCons", "getSolVal", "getLPObjVal"],
    "primal": ["includeHeur", "createSol", "setSolVal", "trySol", "getBestSol"],
    "events": ["includeEventhdlr", "catchEvent", "dropEvent", "getNNodes", "getNLPs"],
    "diagnosis": ["getLPColsData", "getLPRowsData", "getLPBasisInd", "getCondition",
                  "getPrimalbound", "getDualbound", "getGap", "getDepth"],
    "configuration": ["getParams", "getParam", "setParam", "writeProblem", "optimizeNogil"],
}


def api_catalog():
    groups = {}
    for group, names in API_GROUPS.items():
        groups[group] = {}
        for name in names:
            function = getattr(Model, name, None)
            if function is not None:
                groups[group][name] = str(inspect.signature(function))
    return {"implemented_callback_families": ["Pricer", "Branchrule", "Nodesel", "Sepa", "Heur", "Eventhdlr"],
            "installed_model_public_entries": len([n for n in dir(Model) if not n.startswith("_")]),
            "interfaces": groups,
            "authority": "Only implemented adapters execute API calls; no generated code."}


def instance_context(instance, budget, directory=None):
    """Representación completa cuando cabe; muestreo explícito y archivo íntegro si no."""
    physical = {
        "parameters": instance.parameters.model_dump(),
        "operations": instance.operations.model_dump(),
        "vehicles": instance.vehicle_ids,
        "compatible_stations": {k: sorted(instance.chargers_for(k)) for k in instance.vehicle_ids},
        "nodes": [[n.node_id, n.node_type] for n in instance.nodes],
        "arc_columns": ["from", "to", "arc_id", "nominal_kwh", "seconds", "battery_profile"],
        "arcs": [[a.from_node_id, a.to_node_id, a.arc_id, a.energy_kwh,
                  a.travel_time_seconds,
                  a.battery_profile.model_dump() if a.battery_profile is not None else None]
                 for a in instance.arcs],
        "semantics": "Transit is not delivery. Partial charge, saturation and intermediate deficits apply.",
    }
    raw = json.dumps(physical, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / "pricing-instance.json").write_text(raw + "\n")
        (path / "scip-api-catalog.json").write_text(json.dumps(api_catalog(), indent=2) + "\n")
        (path / "scip-parameter-catalog.json").write_text(
            json.dumps(parameter_catalog(), indent=2) + "\n",
        )
    if len(raw.encode()) <= budget:
        return {"scope": "complete_physical_graph", "sha256": digest, "instance": physical}
    # No truncar JSON ni presentar un recorte como instancia completa.
    head = {k: v for k, v in physical.items() if k not in {"arcs", "nodes"}}
    services = [n for n in physical["nodes"] if n[1] != "junction"]
    head["nodes"] = services
    head["arcs"] = []
    size = len(json.dumps(head).encode())
    for arc in sorted(physical["arcs"], key=lambda a: (a[0], a[1], str(a[2]))):
        width = len(json.dumps(arc).encode()) + 2
        if size + width > budget:
            break
        head["arcs"].append(arc)
        size += width
    return {
        "scope": "bounded_excerpt_not_complete_graph", "sha256": digest, "instance": head,
        "omitted_arcs": len(physical["arcs"]) - len(head["arcs"]),
        "omitted_junctions": len(physical["nodes"]) - len(services),
        "full_instance_exported_locally": bool(directory),
    }


class LLMHead:
    def __init__(self, config, profile, deadline, seconds, provider=None, *, instance=None):
        self.config, self.profile, self.deadline, self.provider = config, profile, deadline, provider
        self.started, self.budget, self.runtime = monotonic(), seconds * config.llm_time_fraction, 0.0
        self.policy = RoutePolicy()
        if config.policy == "deterministic":
            self.policy = RoutePolicy(seed_starts=12, pricing_heuristic_starts=8)
        if config.route_policy_overrides:
            self.policy = RoutePolicy.model_validate({
                **self.policy.model_dump(), **config.route_policy_overrides,
            })
            self.policy.scip_parameters = validate_parameters(
                self.policy.scip_parameters,
                bool(profile.get("single_tour_certificate", {}).get("applicable")),
            )
            if set(self.policy.focus_customers) - set(instance.customer_ids if instance else []):
                raise ValueError("La política inicial menciona clientes inexistentes.")
        self.local_decisions = []
        self.urgent_customers = (
            sorted(instance.operations.customer_time_windows, key=lambda i: (
                instance.operations.customer_time_windows[i].close_seconds, i,
            ))[:8] if instance is not None and instance.operations.use_customer_time_windows else []
        )
        self.records, self.skipped = [], []
        self.pending, self.pending_request, self.calls = None, None, 0
        self.pending_deadline, self.pending_model = float("inf"), None
        self.abandoned = []
        self.last_request = -float("inf")
        self.revision, self.events, self.current_phase = 0, {}, "planning"
        self.context = (instance_context(instance, config.instance_context_bytes, config.log_directory)
                        if instance is not None and config.policy == "adaptive" else {})
        self.customer_ids = set(instance.customer_ids) if instance is not None else set()
        self.mps = None
        self.closed = False
        self.bedrock_clients, self.provider_setup_error = {}, None
        if config.policy == "adaptive" and provider is None:
            # Preparar SDK, credenciales y transporte antes de ALNS/SCIP: su
            # inicialización diferida puede agotar el plazo de la decisión.
            # No se invoca ningún modelo aquí; la inferencia sigue asíncrona.
            from ev_routing.llm.bedrock import create_bedrock_client
            try:
                timeouts = {config.bedrock.timeout_seconds}
                if config.bedrock.fast_model_id:
                    timeouts.add(config.bedrock.fast_timeout_seconds)
                for timeout in timeouts:
                    settings = config.bedrock.model_copy(update={"timeout_seconds": timeout})
                    self.bedrock_clients[timeout] = create_bedrock_client(settings)
            except Exception as error:
                # El trabajador registrará el fallo con el fallback habitual,
                # sin reintentar autenticación ni exponer mensajes del SDK.
                self.provider_setup_error = error

    def _console(self, label, data):
        if self.config.show_llm_trace:
            print(f"\n[LLM] {label}:\n" + json.dumps(
                data, ensure_ascii=False, indent=2, allow_nan=False,
            ), flush=True)

    def attach_master(self, model, name):
        if not self.config.export_mps or not self.config.log_directory:
            return
        path = Path(self.config.log_directory) / f"{name}.mps"
        model.writeProblem(str(path), verbose=False)
        raw = path.read_text()
        self.mps = {
            "scope": "RESTRICTED_MASTER_ONLY_missing_future_routes_and_physical_pricing",
            "sha256": hashlib.sha256(raw.encode()).hexdigest(), "bytes": len(raw.encode()),
            "text": raw if len(raw.encode()) <= self.config.instance_context_bytes // 2 else None,
            "omitted_reason": None if len(raw.encode()) <= self.config.instance_context_bytes // 2
            else "MPS exceeds per-request budget; full file exported locally",
        }

    def _call(self, request, bedrock, index):
        started = monotonic()
        result = {"request": request, "model_id": bedrock.model_id, "call_index": index}
        try:
            provider = self.provider
            if provider is None:
                if self.provider_setup_error is not None:
                    raise self.provider_setup_error
                from ev_routing.llm.bedrock import BedrockPolicyClient
                provider = BedrockPolicyClient(
                    bedrock, system_prompt=ROUTE_PROMPT, temperature=0,
                    client=self.bedrock_clients.get(bedrock.timeout_seconds),
                    trace_directory=(str(Path(self.config.log_directory) / "decisions" / f"{index:02d}")
                                     if self.config.log_directory else None),
                    show_trace=self.config.show_llm_trace,
                )
            result["reply"] = provider(request)
        except Exception as error:
            from ev_routing.llm.bedrock import BedrockResponseError
            result["error"] = type(error).__name__
            if isinstance(error, BedrockResponseError):
                result.update(error=error.code, reply={"usage": error.usage})
        result["seconds"] = monotonic() - started
        result["finished_at"] = monotonic()
        return result

    def collect(self):
        for future, record in list(self.abandoned):
            if not future.done():
                continue
            result = future.result()
            reply = result.get("reply", {})
            self.runtime += result["seconds"] - record["runtime_seconds"]
            record.update(runtime_seconds=result["seconds"], inference_completed=True,
                          usage=reply.get("usage") if isinstance(reply, dict) else None,
                          usage_status="provider_returned_after_deadline")
            if result.get("error"):
                record["provider_error"] = result["error"]
            self._console("Respuesta tardía; política conservada", {
                key: value for key, value in record.items() if key != "proposal"
            })
            self.abandoned.remove((future, record))
        if (self.pending is not None and monotonic() >= self.pending_deadline
                and (not self.pending.done()
                     or self.pending.result()["finished_at"] > self.pending_deadline)):
            # Un timeout de lectura no limita DNS, credenciales ni un cuerpo que
            # llegue por fragmentos. Vencer la DECISIÓN permite usar el modelo
            # rápido sin bloquear SCIP; no afirma cancelar la facturación remota.
            elapsed = monotonic() - self.last_request
            record = {
                "event": self.pending_request["event"], "phase": self.pending_request["phase"],
                "model_id": self.pending_model, "status": "not_applied",
                "call_index": self.calls,
                "reason": "decision_deadline", "runtime_seconds": elapsed,
                "usage": None, "usage_status": "unknown_until_provider_returns",
                "inference_completed": False,
            }
            self.runtime += elapsed
            self.records.append(record)
            self.abandoned.append((self.pending, record))
            self.pending = None
            self._console("Decisión vencida; no se aplica", record)
            _save_decision(self.config, self.report())
        if self.pending is None or not self.pending.done():
            return False
        result = self.pending.result()
        self.pending = None
        self.runtime += result["seconds"]
        reply = result.get("reply", {})
        if not isinstance(reply, dict):
            result["error"], reply = "invalid_response", {}
        record = {
            "event": result["request"]["event"], "phase": result["request"]["phase"],
            "model_id": result["model_id"], "runtime_seconds": result["seconds"],
            "call_index": result["call_index"],
            "usage": reply.get("usage"), "status": "rejected",
            "elapsed_seconds": monotonic() - self.started,
            "inference_completed": True,
        }
        if "error" in result:
            record["reason"] = result["error"]
        elif self.closed or monotonic() >= self.deadline:
            record.update(status="not_applied", reason="solve_finished")
        else:
            try:
                before = self.policy.model_dump()
                proposal = RoutePolicy.model_validate({**before, **reply["policy"]})
                if set(proposal.focus_customers) - self.customer_ids:
                    raise ValueError("unknown_customer")
                proposal.scip_parameters = validate_parameters(
                    proposal.scip_parameters,
                    bool(self.profile.get("single_tour_certificate", {}).get("applicable")),
                )
                inactive = set()
                if self.current_phase != "planning":
                    inactive |= {"seed_strategy", "seed_starts", "seed_charging", "seed_time_fraction",
                                 "charging_seed_starts", "share_vehicle_oracles"}
                if self.current_phase == "energy":
                    inactive |= {"deliveries_time_fraction", "bound_strategy", "bound_time_fraction"}
                    if not self.profile.get("single_tour_certificate", {}).get("applicable"):
                        inactive |= {"presolve", "separation", "subtour_batch_size"}
                changes = {}
                for name, value in proposal.model_dump().items():
                    if name not in inactive and value != before[name]:
                        setattr(self.policy, name, value)
                        changes[name] = {"before": before[name], "after": value}
                self.revision += 1
                record.update(status="applied", revision=self.revision,
                              effective_changes=changes, proposal=self.policy.model_dump(),
                              algorithm_changes=[name for name in changes if name != "rationale"],
                              inactive_settings={k: getattr(proposal, k) for k in inactive
                                                 if getattr(proposal, k) != before[k]})
            except (ValueError, KeyError, TypeError):
                record["reason"] = "invalid_policy"
        self.records.append(record)
        self._console("Decisión validada", {
            key: value for key, value in record.items() if key != "proposal"
        })
        _save_decision(self.config, self.report())
        return record["status"] == "applied"

    def decide(self, event, state):
        self.current_phase = state.get("phase", self.current_phase)
        self.events[event] = self.events.get(event, 0) + 1
        self.collect()
        if self.config.local_rule_control:
            self._local_rules(event, state)
        now = monotonic()
        if (self.closed or self.config.policy != "adaptive" or self.pending is not None
            or self.calls >= self.config.max_llm_calls
            or (event not in {"before_search", "after_seed"}
                and now - self.last_request < self.config.decision_interval_seconds)):
            return self.policy
        available = min(self.deadline - now - .1, self.budget - self.runtime)
        if available < .25:
            return self.policy
        bedrock = self.config.bedrock
        if bedrock.fast_model_id and (event != "before_search" or available < bedrock.timeout_seconds):
            bedrock = bedrock.model_copy(update={
                "model_id": bedrock.fast_model_id, "timeout_seconds": bedrock.fast_timeout_seconds,
                "reasoning_effort": None,
            })
        observed = [r["runtime_seconds"] for r in self.records
                    if r.get("model_id") == bedrock.model_id and r["status"] == "applied"]
        if observed and available < 1.25 * min(observed):
            if not any(r["reason"] == "insufficient_measured_latency" for r in self.skipped):
                self.skipped.append({"event": event, "reason": "insufficient_measured_latency",
                                     "model_id": bedrock.model_id, "available_seconds": available})
            return self.policy
        bedrock = bedrock.model_copy(update={"timeout_seconds": min(bedrock.timeout_seconds, available)})
        catalog = parameter_catalog(bool(self.profile.get("single_tour_certificate", {}).get("applicable")))
        concise = {k: v for k, v in catalog["parameters_and_defaults"].items()
                   if k.endswith(("/freq", "/priority", "/stdpriority")) or k.startswith("lp/")}
        request = {
            "event": event, "phase": self.current_phase, "structure": self.profile,
            "instance_context": self.context, "restricted_master": self.mps,
            "state": state, "current_policy": self.policy.model_dump(),
            "allowed_policy_schema": RoutePolicy.model_json_schema(),
            "scip_api": api_catalog(),
            "native_scip_catalog": {**catalog, "parameters_and_defaults": concise},
            "remaining_wall_seconds": max(0, self.deadline-now),
            "remaining_calls": self.config.max_llm_calls-self.calls,
            "finished_stages": (
                [] if self.current_phase == "planning" else
                ["seeding", "bound_relaxation"] if self.current_phase == "energy" else ["seeding"]
            ),
            "recent_decisions": [{k: r.get(k) for k in ("event", "status", "effective_changes")}
                                 for r in self.records[-2:]],
        }
        # No objetos SCIP ni referencias mutables cruzan al trabajador.
        request = json.loads(json.dumps(request, allow_nan=False))
        self.calls += 1
        self.last_request = now
        self.pending_request = request
        self.pending_deadline = min(self.deadline, now + bedrock.timeout_seconds)
        self.pending_model = bedrock.model_id
        future = Future()
        self.pending = future
        index = self.calls
        self._console("Consulta enviada; SCIP continúa", {
            "call_index": index, "model_id": bedrock.model_id,
            "event": event, "phase": self.current_phase,
            "timeout_seconds": bedrock.timeout_seconds,
            "instance_scope": self.context.get("scope"),
            "request_directory": (str(Path(self.config.log_directory) / "decisions" / f"{index:02d}")
                                  if self.config.log_directory else None),
        })

        def run():
            future.set_result(self._call(request, bedrock, index))

        Thread(target=run, name="bedrock-evrp-head", daemon=True).start()
        self.collect()
        return self.policy

    def _local_rules(self, event, state):
        """Control barato y determinista, sin inferencia ni información del testigo."""
        if self.closed or monotonic() >= self.deadline:
            return
        changes = {}
        if event == "before_search":
            changes = {"focus_customers": self.urgent_customers}
        elif event in {"after_seed", "search_stagnation"}:
            delivered = state.get("deliveries", 0) or 0
            if delivered < self.profile.get("customers", 0):
                changes = {
                    "repair_strategy": "regret", "resource_path_order": "time",
                    "destroy_operators": ["related", "route", "random"],
                    "ruin_fraction": .3, "diversification_probability": .15,
                    "resource_repair_seconds": .12,
                    "focus_customers": self.urgent_customers,
                }
            else:
                changes = {
                    "focus_customers": [], "resource_path_order": "energy",
                    "destroy_operators": ["worst", "related", "random"],
                    "ruin_fraction": .2, "diversification_probability": .08,
                    "memetic_enabled": True, "population_size": 16,
                    "restricted_master_seconds": 1.0,
                }
        if not changes:
            return
        validated = RoutePolicy.model_validate({**self.policy.model_dump(), **changes})
        effective = {}
        for key in changes:
            value = getattr(validated, key)
            if value != getattr(self.policy, key):
                effective[key] = {"before": getattr(self.policy, key), "after": value}
                setattr(self.policy, key, value)
        if effective:
            self.revision += 1
            record = {"event": event, "phase": self.current_phase,
                      "elapsed_seconds": monotonic() - self.started,
                      "effective_changes": effective, "revision": self.revision}
            self.local_decisions.append(record)
            self._console("Regla local aplicada; sin LLM", record)

    def close(self):
        self.closed = True
        self.collect()
        if self.pending is not None:
            self.records.append({
                "event": self.pending_request["event"], "phase": self.pending_request["phase"],
                "model_id": self.pending_model,
                "call_index": self.calls,
                "status": "not_applied", "reason": "inference_inflight_at_solve_end",
                "runtime_seconds": max(0, monotonic()-self.last_request), "usage": None,
                "usage_status": "unknown_until_provider_returns",
                "inference_completed": False,
            })
            self._console("Fin de resolución con solicitud pendiente", self.records[-1])
        _save_decision(self.config, self.report())

    def report(self):
        applied = sum(r["status"] == "applied" for r in self.records)
        failure = any(r["status"] != "applied" for r in self.records)
        status = ("disabled" if self.config.policy == "standard" else self.config.policy)
        if self.config.policy == "adaptive":
            status = "fallback" if not applied else "partial_fallback" if failure else "adaptive"
        return {
            "requested_policy": self.config.policy,
            "active_policy": ("adaptive" if applied else
                              "standard" if self.config.policy == "adaptive" else self.config.policy),
            "status": status, "calls": self.calls, "applied_decisions": applied,
            "decisions_changing_algorithm": sum(bool(r.get("algorithm_changes")) for r in self.records),
            "decisions": self.records,
            "runtime_seconds": sum(r["runtime_seconds"] for r in self.records),
            "completed_inference_seconds": sum(r["runtime_seconds"] for r in self.records
                                               if r.get("inference_completed")),
            "inference_inflight": (
                self.pending is not None and not self.pending.done()
                or any(not future.done() for future, _ in self.abandoned)
            ),
            "events": self.events, "revision": self.revision,
            "callback_calls": sum(value for name, value in self.events.items()
                                  if name not in {"before_search", "after_seed", "search_stagnation",
                                                  "heuristic_progress"}),
            "policy": self.policy.model_dump(), "skipped": self.skipped,
            "instance_scope": self.context.get("scope"), "model_id": self.config.bedrock.model_id,
            "local_policy_mode": (
                "rules" if self.config.local_rule_control else
                "fixed" if self.config.route_policy_overrides else "standard"
            ),
            "local_decisions": self.local_decisions,
        }
