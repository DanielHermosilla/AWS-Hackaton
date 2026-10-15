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
from ev_routing.contracts import ProblemInstance, Solution, SolverConfig
from ev_routing.metrics import compute_metrics
from ev_routing.search_policy import SearchConfig
from ev_routing.solve import solve_instance
from ev_routing.validation import validate_solution


def run_instance(
    instance: ProblemInstance,
    config: SolverConfig | None = None,
    *,
    output_path: str | Path | None = None,
    initial_solution: Solution | None = None,
    search_config: SearchConfig | None = None,
) -> dict[str, Any]:
    """Resolver y conservar solución, certificados y auditoría separadas."""
    started = time.perf_counter()
    config = config or SolverConfig()
    without_h = config.solver == "scip-routes"
    # La integración importa el solver de Daniel, sin el preprocesamiento
    # derivado de codex/optimizacion-contraida. No aceptar sus arcos agregados
    # sin la expansión/validación que esa representación necesita.
    representation = instance.provenance.get("representation", {})
    if isinstance(representation, dict) and representation.get("kind") == "service_paths_nonnegative":
        raise ValueError("Esta integración requiere arcos elementales; no admite service_paths_nonnegative")
    initial_checking = time.perf_counter()
    if initial_solution is not None:
        report = validate_solution(instance, initial_solution, enforce_movement_limit=not without_h)
        if not report.feasible:
            raise ValueError(f"Solución inicial inválida: {report.violations}")
    initial_validation_seconds = time.perf_counter() - initial_checking
    canonical = json.dumps(
        instance.model_dump(mode="json"), sort_keys=True, allow_nan=False
    ).encode()
    options = {}
    if initial_solution is not None:
        options["initial_solution"] = initial_solution
    if search_config is not None:
        options["search_config"] = search_config
    solved = solve_instance(instance, config, **options)
    checking = time.perf_counter()
    validation = (
        validate_solution(instance, solved.solution, enforce_movement_limit=not without_h)
        if solved.solution is not None else None
    )
    road_audit = None
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
        "formulation": {
            "kind": "complete_routes_without_h" if without_h else "legacy_position_indexed",
            "movement_limit_used": None if without_h else instance.parameters.movement_limit,
        },
        "operations": instance.operations.model_dump(mode="json"),
        "provenance": instance.provenance,
        "solver_config": config.model_dump(),
        "status": status,
        "solve": solved.model_dump(mode="json"),
        "validation": validation.model_dump() if validation else None,
        "road_validation": road_audit,
        "initial_solution": {
            "provided": initial_solution is not None,
            "validated": initial_solution is not None,
            "deliveries": len(initial_solution.served_visit_ids) if initial_solution else None,
            "energy_kwh": initial_solution.net_energy_kwh if initial_solution else None,
        },
        "kpis": compute_metrics(instance, solved.solution, validation),
        "tuning": solved.search["controller"] if solved.search else {
            "status": "disabled",
            "reason": "El backend seleccionado resuelve sin LLM ni llamadas a AWS.",
            "future_entry_point": "ev_routing.llm.tuning.propose_tuning",
        },
        "runtime_seconds": {
            "resolution_including_model": solved.runtime_seconds,
            "validation": validation_seconds,
            "initial_solution_validation": initial_validation_seconds,
            "total": time.perf_counter() - started,
            # Incluido en resolución/total; puede solaparse con solver en DW.
            "llm": solved.search["controller"]["runtime_seconds"] if solved.search else 0.0,
        },
    }
    # No serializar Infinity/NaN: no son JSON y suelen ocultar cotas ausentes.
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialized + "\n", encoding="utf-8")
    return result
