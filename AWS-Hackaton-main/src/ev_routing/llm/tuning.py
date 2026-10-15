from typing import Any, Dict, List, Tuple

from ..contracts import TuningProposal, TuningRequest


DEFAULT_ALLOWED = ["heuristics", "cuts", "presolve", "branching", "mip_rel_gap", "time_limit"]


def build_structural_summary(instance) -> Dict[str, Any]:
    return {
        "num_nodes": len(instance.nodes),
        "num_visits": len(instance.visit_nodes()),
        "num_chargers": len(instance.charger_nodes()),
        "num_vehicles": instance.fleet.num_vehicles,
        "movement_limit": instance.movement_limit,
        "battery_capacity_kwh": instance.fleet.battery_capacity_kwh,
    }


def validate_proposal(proposal_dict: Dict[str, Any], allowed_parameters: List[str]) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    if not isinstance(proposal_dict, dict):
        return False, ["proposal is not a dict"]
    params = proposal_dict.get("parameters", {})
    if not isinstance(params, dict):
        return False, ["parameters must be an object"]
    unknown = [k for k in params if k not in (allowed_parameters or [])]
    if unknown:
        warnings.append(f"unknown parameters ignored: {unknown}")
    # do not accept changes to problem config / model
    forbidden = {"movement_limit", "battery_capacity_kwh", "reserve_kwh", "initial_soc", "objective"}
    if forbidden & set(params):
        return False, [f"forbidden tuning parameters: {forbidden & set(params)}"]
    return True, warnings


def apply_proposal(solver_config, proposal: TuningProposal, allowed_parameters: List[str]) -> Tuple[Any, bool]:
    ok, ws = validate_proposal(proposal.model_dump() if hasattr(proposal, "model_dump") else {"parameters": proposal.parameters}, allowed_parameters)
    if not ok:
        return solver_config, False
    # We do not mutate problem; only solver options
    new = solver_config.model_copy() if hasattr(solver_config, "model_copy") else solver_config.copy()
    for k, v in (proposal.parameters or {}).items():
        if k in allowed_parameters:
            new.options = dict(new.options or {})
            new.options[k] = v
    return new, True
