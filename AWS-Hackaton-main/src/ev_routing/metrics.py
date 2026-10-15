from typing import Any, Dict

from .contracts import ProblemInstance, RunResult


def compute_kpis(instance: ProblemInstance, run_result: RunResult) -> Dict[str, Any]:
    served = run_result.served_count or 0
    total_visits = len(instance.visit_nodes())
    return {
        "delivered_visits": served,
        "total_visits": total_visits,
        "delivery_rate": served / total_visits if total_visits else 0.0,
        "total_energy_kwh": run_result.total_energy_kwh,
    }


def summarize_run(run_result: RunResult) -> str:
    k = run_result.kpis or {}
    return f"delivered={k.get('delivered_visits')} energy={k.get('total_energy_kwh')}"
