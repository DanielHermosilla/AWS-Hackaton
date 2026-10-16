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
from ev_routing.service_graph import (
    SERVICE_REPRESENTATIONS,
    PathArchive,
    check_service_context,
    expand_and_validate,
)
from ev_routing.solve import solve_instance
from ev_routing.validation import validate_solution


def run_instance(
    instance: ProblemInstance,
    config: SolverConfig | None = None,
    *,
    output_path: str | Path | None = None,
    road_instance: ProblemInstance | None = None,
    path_archive: PathArchive | None = None,
    initial_solution: Solution | None = None,
    search_config: SearchConfig | None = None,
    policy_provider=None,
) -> dict[str, Any]:
    """Resolver y conservar solución, certificados y auditoría separadas."""
    started = time.perf_counter()
    config = config or SolverConfig()
    without_h = config.solver == "scip-routes"
    representation = instance.provenance.get("representation", {})
    if not isinstance(representation, dict):
        raise ValueError("provenance.representation debe ser un objeto con kind")
    is_service_graph = representation.get("kind") in SERVICE_REPRESENTATIONS
    if is_service_graph:
        if road_instance is None or path_archive is None:
            raise ValueError("Esta variante requiere --road-instance y --path-archive para validarse")
        check_service_context(instance, road_instance, path_archive)
    elif road_instance is not None or path_archive is not None:
        raise ValueError("Los caminos externos solo corresponden a la variante de servicios")
    initial_checking = time.perf_counter()
    if initial_solution is not None:
        report = validate_solution(instance, initial_solution, enforce_movement_limit=not without_h)
        if not report.feasible:
            raise ValueError(f"Solución inicial inválida: {report.violations}")
        if is_service_graph:
            _, report, _ = expand_and_validate(
                instance, road_instance, path_archive, initial_solution, without_h=without_h,
            )
            if not report.feasible:
                raise ValueError(f"Solución inicial vial inválida: {report.violations}")
    initial_validation_seconds = time.perf_counter() - initial_checking
    canonical = json.dumps(
        instance.model_dump(mode="json"), sort_keys=True, allow_nan=False
    ).encode()
    options = {}
    if initial_solution is not None:
        options["initial_solution"] = initial_solution
    if search_config is not None:
        options["search_config"] = search_config
    if policy_provider is not None:
        options["policy_provider"] = policy_provider
    solved = solve_instance(instance, config, **options)
    checking = time.perf_counter()
    validation = (
        validate_solution(instance, solved.solution, enforce_movement_limit=not without_h)
        if solved.solution is not None else None
    )
    road_audit = expanded = None
    if is_service_graph and validation is not None and validation.feasible:
        try:
            expanded, report, counts = expand_and_validate(
                instance, road_instance, path_archive, solved.solution, without_h=without_h,
            )
            road_audit = {
                **report.model_dump(),
                "road_movement_counts": counts,
                "original_road_movement_limit": road_instance.parameters.movement_limit,
                "within_original_movement_limit": all(
                    count <= road_instance.parameters.movement_limit for count in counts.values()
                ),
                "routes": [route.model_dump(mode="json") for route in expanded.routes],
                "scope": "Arcos, entregas, batería y opciones operacionales; H vial original separado.",
            }
            validation.checks["expanded_roads"] = report.feasible
            if not report.feasible:
                validation.feasible = False
                validation.violations.extend(report.violations)
                validation.checks["expanded_roads"] = False
        except (ValueError, KeyError) as error:
            validation.feasible = False
            validation.violations.append(f"Expansión vial inválida: {error}")
            validation.checks["expanded_roads"] = False
            road_audit = {"feasible": False, "violations": [str(error)]}
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
        "kpis": compute_metrics(
            road_instance.model_copy(update={"operations": instance.operations})
            if expanded is not None else instance,
            expanded if expanded is not None else solved.solution, validation,
        ),
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
