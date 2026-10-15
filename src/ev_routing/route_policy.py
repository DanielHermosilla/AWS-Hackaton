"""Una decisión estratégica por ejecución; acciones implementadas y verificables."""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic
from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr

from ev_routing.contracts import Contract
from ev_routing.scip_tuning import prompt_catalog, validate_parameters
from ev_routing.search_policy import SearchConfig


class RoutePolicy(Contract):
    route_cuts: Literal["none", "subset_row_triples"] = "subset_row_triples"
    columns_per_round: int = Field(default=50, ge=1, le=500, strict=True)
    max_subset_rows: int = Field(default=100, ge=0, le=1000, strict=True)
    subtour_batch_size: int = Field(default=100, ge=1, le=1000, strict=True)
    branching: Literal["relpscost", "mostinf"] = "relpscost"
    heuristics: Literal["default", "fast", "aggressive", "off"] = "default"
    presolve: Literal["default", "fast", "aggressive", "off"] = "default"
    separation: Literal["default", "fast", "aggressive", "off"] = "default"
    scip_parameters: dict[str, StrictBool | StrictInt | StrictFloat | StrictStr] = Field(
        default_factory=dict, max_length=2500,
    )
    seed_strategy: Literal["none", "cheapest_insertion", "regret_insertion"] = "cheapest_insertion"
    seed_starts: int = Field(default=1, ge=1, le=32, strict=True)
    pricing_strategy: Literal["exhaustive", "heuristic_then_exact"] = "exhaustive"
    pricing_search: Literal["breadth_first", "depth_first"] = "breadth_first"
    pricing_heuristic_starts: int = Field(default=4, ge=1, le=32, strict=True)
    dominance: Literal["convex", "vertices_only"] = "convex"
    rationale: str = Field(default="", max_length=6000)


ROUTE_PROMPT = """Select a substantive, coherent search configuration before an H-free electric
vehicle routing solve. Return ONLY a JSON object with VALUES allowed by the schema.
Do not include introductory or concluding prose, comments, schema or markdown.
Use only schema properties; put all explanations in rationale, never extra *_note fields.
Example: {"route_cuts":"subset_row_triples","columns_per_round":50,
"max_subset_rows":100,"subtour_batch_size":100,"branching":"relpscost",
"rationale":"Brief observation and hypothesis."}
The exact model selects physically feasible complete routes, with binary customer
assignments and continuous route weights. Pricing retains partial charging,
regeneration saturation and time windows. Subset-row triple inequalities are valid
and every future column receives its coefficient. More cuts may make pricing costly.
The native_scip_catalog lists actual installed parameters and their defaults,
grouped by path segments to save tokens. Output FLAT slash-separated full names
in scip_parameters, with native bool/int/float/string values.
Address LP strategy, primal heuristics, branching, node selection and, when unlocked,
presolve and separation. Presets may change many native parameters at once.
Do not copy all defaults or make arbitrary changes merely to increase their count:
explain a falsifiable strategy, emphasizing the actual bottleneck.
Keep rationale concise, preferably under 800 characters.
The certified single-tour reduction uses directed arc variables and subtour inequalities.
The general master relies on a Python continuous-resource route pricer: it can be
starved of useful long routes by breadth-first enumeration, while SCIP stays at
the root. More native cuts or different branching cannot fix that alone.
An independently validated cheapest-insertion incumbent is already retained when
supported. Inspect validated_incumbent and search_budget before deciding.
seed_strategy chooses additional no-charge starting routes; regret_insertion and
more seed_starts diversify them without discarding a better incumbent.
heuristic_then_exact first tries dual-guided feasible routes, then retains the exact
oracle as a fallback. It never certifies lack of columns from a heuristic failure.
pricing_search changes traversal order only; vertices_only uses conservative
dominance and may retain extra labels. More subset-row cuts add work to pricing.
The implementation enables these heuristics only for nonnegative untimed cases;
all other resources, charging and revisits remain handled by exact pricing.
Budget allocation is fixed by the caller, including heuristic and inference time.
Do not change data, resources, formulation, objectives, budgets or proof criteria.
Do not output code. The solver, never the LLM, proves optimality or complete pricing.
This is one strategic call shared by both lexicographic phases, not a pricing callback.
"""


def _save_decision(config: SearchConfig, report: dict) -> None:
    if config.log_directory:
        directory = Path(config.log_directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "llm-decision.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    if config.show_llm_trace and not report["calls"]:
        print("[LLM] Sin llamada: " + json.dumps(report, ensure_ascii=False), flush=True)


def choose_route_policy(config: SearchConfig, profile: dict, deadline: float, provider=None):
    policy = RoutePolicy()
    if config.policy == "deterministic":
        policy = RoutePolicy(columns_per_round=20, max_subset_rows=50)
    report = {
        "requested_policy": config.policy, "active_policy": config.policy,
        "status": "disabled" if config.policy == "standard" else config.policy,
        "calls": 0, "applied_decisions": 0, "decisions": [], "runtime_seconds": 0.0,
        "callback_calls": 0, "policy": policy.model_dump(),
    }
    if config.policy != "adaptive":
        _save_decision(config, report)
        return policy, report
    if deadline - monotonic() <= config.bedrock.timeout_seconds:
        report.update(status="fallback", active_policy="standard", reason="insufficient_call_budget")
        _save_decision(config, report)
        return policy, report
    if provider is None:
        from ev_routing.llm.bedrock import BedrockPolicyClient
        provider = BedrockPolicyClient(
            config.bedrock, system_prompt=ROUTE_PROMPT, temperature=0,
            trace_directory=config.log_directory, max_input_bytes=160_000,
        )
    request = {
        "event": "before_decomposition", "phase": "both_lexicographic_phases",
        "structure": profile, "allowed_policy_schema": RoutePolicy.model_json_schema(),
        "current_policy": policy.model_dump(),
        "native_scip_catalog": prompt_catalog(bool(
            profile.get("single_tour_certificate", {}).get("applicable")
        )),
    }
    before = policy.model_dump()
    if config.show_llm_trace:
        print("\n[LLM] Prompt del sistema:\n" + ROUTE_PROMPT, flush=True)
        print("[LLM] Prompt del usuario:\n" + json.dumps(
            request, ensure_ascii=False, indent=2, allow_nan=False,
        ), flush=True)
    started = monotonic()
    record = {
        "event": "before_decomposition", "phase": "both_lexicographic_phases",
        "model_id": config.bedrock.model_id, "region": config.bedrock.region,
        "usage": None,
        "available_native_parameters": request["native_scip_catalog"]["available_parameter_count"],
    }
    try:
        response = provider(request)
        record["usage"] = response.get("usage")
        values = response["policy"]
        if isinstance(values, dict):
            # Un campo extra nulo no solicita ninguna acción. Conservarlo en la
            # auditoría; campos extra con valores y parámetros SCIP desconocidos
            # siguen provocando rechazo completo, sin aplicación parcial.
            ignored = {key: value for key, value in values.items()
                       if key not in RoutePolicy.model_fields and value is None}
            if ignored:
                record["ignored_null_fields"] = ignored
                values = {key: value for key, value in values.items() if key not in ignored}
        proposal = RoutePolicy.model_validate(values)
        proposal.scip_parameters = validate_parameters(proposal.scip_parameters, bool(
            profile.get("single_tour_certificate", {}).get("applicable")
        ))
        policy = proposal
        record.update(status="applied", proposal=policy.model_dump())
        report.update(status="adaptive", applied_decisions=1)
    except Exception as error:
        from ev_routing.llm.bedrock import BedrockResponseError
        record.update(status="rejected", reason=type(error).__name__)
        if isinstance(error, BedrockResponseError):
            record.update(reason=error.code, usage=error.usage)
        elif isinstance(error, ValueError):
            record["validation_error"] = str(error)[:2000]
        report.update(status="fallback", active_policy="standard")
    elapsed = monotonic() - started
    record["runtime_seconds"] = elapsed
    report.update(
        calls=1, decisions=[record], runtime_seconds=elapsed, policy=policy.model_dump(),
    )
    applicable = profile.get("applicable_actions", [
        key for key in before if key != "rationale"
    ])
    if policy.route_cuts == "none":
        applicable = [key for key in applicable if key != "max_subset_rows"]
    after = policy.model_dump()
    changes = {
        key: {"before": before[key], "after": after[key]}
        for key in applicable if before[key] != after[key]
    }
    record.update(
        before_policy=before, effective_settings={key: after[key] for key in applicable},
        effective_changes=changes,
        inactive_settings={key: after[key] for key in after
                           if key not in applicable and key != "rationale"},
    )
    _save_decision(config, report)
    if config.show_llm_trace:
        print("[LLM] Decisión validada:\n" + json.dumps(
            record, ensure_ascii=False, indent=2, allow_nan=False,
        ), flush=True)
        if record["status"] == "applied" and not changes:
            print("[LLM] Propuesta aceptada; no cambia los parámetros efectivos.", flush=True)
    return policy, report
