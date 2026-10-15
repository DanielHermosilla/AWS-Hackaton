"""Flujo local completo: instancia -> solver -> checker -> KPIs -> JSON."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ev_routing import __version__
from ev_routing.contracts import ProblemInstance, SolverConfig
from ev_routing.metrics import compute_metrics
from ev_routing.solve import solve_instance
from ev_routing.validation import validate_solution


def run_instance(
    instance: ProblemInstance,
    config: SolverConfig | None = None,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Resolver sin LLM y conservar solución, certificados y auditoría separadas."""
    started = time.perf_counter()
    config = config or SolverConfig()
    canonical = json.dumps(
        instance.model_dump(mode="json"), sort_keys=True, allow_nan=False
    ).encode()
    solved = solve_instance(instance, config)
    checking = time.perf_counter()
    validation = (
        validate_solution(instance, solved.solution) if solved.solution is not None else None
    )
    validation_seconds = time.perf_counter() - checking
    status = solved.status
    if validation is not None and not validation.feasible:
        # Un estado "optimal" del solver no autoriza entregar una ruta inválida.
        status = "invalid_solution"
    result = {
        "schema_version": "1.0",
        "run_id": uuid4().hex,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": __version__,
        "instance_name": instance.name,
        "instance_sha256": hashlib.sha256(canonical).hexdigest(),
        "parameters": instance.parameters.model_dump(),
        "provenance": instance.provenance,
        "solver_config": config.model_dump(),
        "status": status,
        "solve": solved.model_dump(mode="json"),
        "validation": validation.model_dump() if validation else None,
        "kpis": compute_metrics(instance, solved.solution, validation),
        "tuning": {
            "status": "disabled",
            "reason": "Esta rama resuelve sin LLM ni llamadas a AWS.",
            "future_entry_point": "ev_routing.llm.tuning.propose_tuning",
        },
        "runtime_seconds": {
            "resolution_including_model": solved.runtime_seconds,
            "validation": validation_seconds,
            "total": time.perf_counter() - started,
            "llm": 0.0,
        },
    }
    # No serializar Infinity/NaN: no son JSON y suelen ocultar cotas ausentes.
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialized + "\n", encoding="utf-8")
    return result
