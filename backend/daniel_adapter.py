"""Project Daniel's native RunResult without replacing its physics or certificates.

Runtime imports only the merged local project core.
"""

from __future__ import annotations

import copy
from pathlib import Path

from .service import ProviderError, json_bytes


def load_provider():
    try:
        import pyscipopt  # noqa: F401 - actual native dependency must import successfully

        import ev_routing

        expected = Path(__file__).resolve().parents[1] / "src" / "ev_routing"
        if not Path(ev_routing.__file__).resolve().is_relative_to(expected.resolve()):
            raise ProviderError(
                "ev_routing debe cargarse desde src/ev_routing de este checkout, no desde otro proveedor.",
                "provider_unavailable",
                503,
            )
        from ev_routing.pipeline import run_instance
        from ev_routing.search_policy import SearchConfig

        return run_instance, SearchConfig
    except ImportError as exc:
        raise ProviderError(
            "El núcleo local o PySCIPOpt no está disponible; sincronice el entorno del proyecto.",
            "provider_unavailable",
            503,
        ) from exc


def provider_available():
    try:
        load_provider()
        return True
    except ProviderError:
        return False


def _arc_lookup(instance):
    return {
        (a.from_node_id, a.to_node_id, a.arc_id): a
        for a in instance.arcs
    }


def route_geometry(instance, steps, *, arcs=None, nodes=None):
    """Native Arc.geometry stores [latitude, longitude] (network.py)."""
    nodes = nodes if nodes is not None else {n.node_id: n for n in instance.nodes}
    arcs = arcs if arcs is not None else _arc_lookup(instance)
    points = []
    for step in steps:
        destination = step.next_node_id
        if destination is None or (destination == step.node_id and step.arc_id is None):
            continue
        arc = arcs.get((step.node_id, destination, step.arc_id))
        if arc is None or len(arc.geometry) < 2:
            return None
        for point, node_id in ((arc.geometry[0], step.node_id), (arc.geometry[-1], destination)):
            node = nodes.get(node_id)
            if node is None or node.latitude is None or node.longitude is None:
                return None
            if abs(point[0] - node.latitude) > 1e-6 or abs(point[1] - node.longitude) > 1e-6:
                return None
        coords = [[lon, lat] for lat, lon in arc.geometry]
        if points:
            if points[-1] != coords[0]:
                return None
            coords = coords[1:]
        for point in coords:
            if not points or point != points[-1]:
                points.append(point)
    return {"type": "LineString", "coordinates": points} if len(points) >= 2 else None


def project_result(instance, config, native, *, road_instance=None, search_config=None):
    from ev_routing.contracts import SolveResult, ValidationReport, VehicleRoute

    try:
        solved = SolveResult.model_validate(native["solve"])
        report = (
            ValidationReport.model_validate(native["validation"])
            if native.get("validation") is not None
            else None
        )
        json_bytes(native)
    except (ValueError, TypeError, KeyError) as exc:
        raise ProviderError(
            "El núcleo devolvió un resultado nativo incompleto o no finito.",
            "invalid_provider_result",
        ) from exc
    params = instance.parameters
    solution = solved.solution
    valid = solution is not None and report is not None and report.feasible
    display_instance = road_instance if road_instance is not None else instance
    display_routes = solution.routes if solution is not None else []
    road_audit = native.get("road_validation")
    if road_instance is not None:
        # No compact route is presented as a street route without the independent
        # expansion check. The native result remains untouched for inspection.
        valid = valid and road_audit is not None and road_audit.get("feasible") is True
        if valid:
            display_routes = [VehicleRoute.model_validate(r) for r in road_audit["routes"]]
        else:
            display_instance = instance
    scope = (
        "Validación independiente nativa de Daniel sobre los arcos y energía de la instancia; "
        "formulación por rutas completas sin H. No garantiza consumos reales ni una red vial no aportada."
    )
    warnings = []
    if solved.message:
        warnings.append(solved.message)
    network = display_instance.provenance.get("network", {})
    network_kind = network.get("kind") if isinstance(network, dict) else None
    if not isinstance(network_kind, str):
        network_kind = (
            "directed_road_graph"
            if isinstance(network, dict) and network.get("source") == "directed_road_graph"
            else "native"
        )
    synthetic = (
        display_instance.provenance.get("kind", "").startswith("synthetic")
        if isinstance(display_instance.provenance.get("kind"), str)
        else False
    )
    if synthetic or network_kind == "haversine":
        warnings.append(
            "Instancia sintética/geodésica: sus arcos y energía son supuestos; no representan rutas viales verificadas."
        )
    phases = [p.model_dump(mode="json") for p in solved.phases]
    time_limit_reached = (
        True
        if any(
            p.termination_condition
            in {"timelimit", "budget_exhausted", "maxTimeLimit", "time_limit"}
            for p in solved.phases
        )
        else None
    )
    if time_limit_reached:
        warnings.append(
            "Se alcanzó un límite de tiempo; se conserva el resultado nativo y cualquier solución disponible con su validación."
        )
    fleet = [
        {
            "id": vid,
            "type": "native",
            "label": f"Vehículo {i + 1}",
            "battery_capacity_kwh": params.battery_capacity_kwh,
            "reserve_kwh": params.reserve_kwh,
            "initial_soc": params.initial_soc,
        }
        for i, vid in enumerate(instance.vehicle_ids)
    ]
    routes = []
    arcs = _arc_lookup(display_instance)
    nodes_by_id = {n.node_id: n for n in display_instance.nodes}
    distances = {key: a.distance_m for key, a in arcs.items()}
    distances[instance.depot_id, instance.depot_id, None] = 0.0
    if solution is not None:
        for route in display_routes:
            steps = []
            for step in route.steps:
                readings = {
                    "arrival_energy_kwh": step.battery_arrival_kwh,
                    "departure_energy_kwh": step.battery_departure_kwh,
                }
                if any(
                    value < 0 or value > params.battery_capacity_kwh for value in readings.values()
                ):
                    # Raw native readings remain untouched. Invalid physical values
                    # are unavailable for display, never clipped into feasibility.
                    readings = {
                        key: value if 0 <= value <= params.battery_capacity_kwh else None
                        for key, value in readings.items()
                    }
                    warnings.append(
                        "Una lectura de batería nativa está fuera de capacidad: se omite en la presentación y se conserva en el resultado original."
                    )
                steps.append(
                    {
                        "position": step.position,
                        "node_id": step.node_id,
                        **readings,
                        "charge_kwh": step.charged_to_battery_kwh,
                        "energy_kwh": step.effective_arc_energy_kwh if valid else None,
                        "delivered_visit_ids": list(step.delivered_visit_ids),
                        "next_node_id": step.next_node_id,
                        "arc_id": step.arc_id,
                        "predicted_arc_energy_kwh": step.predicted_arc_energy_kwh,
                        "effective_arc_energy_kwh": step.effective_arc_energy_kwh,
                        "arrival_seconds": step.arrival_seconds,
                        "service_start_seconds": step.service_start_seconds,
                        "departure_seconds": step.departure_seconds,
                        "service_duration_seconds": step.service_duration_seconds,
                        "charging_duration_seconds": step.charging_duration_seconds,
                        "travel_time_seconds": step.travel_time_seconds,
                    }
                )
            delivered = list(
                dict.fromkeys(v for step in route.steps for v in step.delivered_visit_ids)
            )
            known_distances = [
                distances.get((step.node_id, step.next_node_id, step.arc_id))
                for step in route.steps
                if step.next_node_id is not None
            ]
            routes.append(
                {
                    "vehicle_id": route.vehicle_id,
                    "served_visit_ids": delivered,
                    "steps": steps,
                    "geometry": route_geometry(
                        display_instance, route.steps, arcs=arcs, nodes=nodes_by_id,
                    ) if valid else None,
                    "distance_km": sum(known_distances) / 1000
                    if valid and all(v is not None for v in known_distances)
                    else None,
                    "energy_kwh": route.net_energy_kwh if valid else None,
                    "duration_seconds": route.duration_seconds,
                }
            )
    if any(r["geometry"] is None and r["served_visit_ids"] for r in routes):
        warnings.append(
            "No hay geometría guardada continua con extremos asociados a sus nodos para alguna ruta; se conserva la secuencia sin fabricar líneas."
        )
    if solution is None:
        status = solved.status if solved.status in {"unavailable", "error"} else "no_solution"
        warnings.append(
            "No hay una solución disponible; entregas cumplidas y pendientes son desconocidas. Consulte las fases nativas para conocer el estado de la búsqueda."
        )
    elif not valid:
        status = "validation_failed"
    else:
        status = "partial" if solution.unserved_visit_ids else "result_available"
    assumptions = display_instance.provenance.get("assumptions", [])
    if not isinstance(assumptions, list) or not all(isinstance(a, str) for a in assumptions):
        assumptions = []
    native_times = native.get("runtime_seconds", {})
    used_nodes = {step.node_id for route in display_routes for step in route.steps}
    policy = search_config.policy if search_config else native.get("tuning", {}).get(
        "requested_policy", "standard",
    )
    return {
        "status": status,
        "has_solution": solution is not None,
        "nodes": [
            node.model_dump(mode="json") for node in display_instance.nodes
            if road_instance is None or node.node_type != "junction" or node.node_id in used_nodes
        ],
        "fleet": fleet,
        "routes": routes,
        "served_count": len(solution.served_visit_ids) if solution is not None else None,
        "total_visits": len(instance.customer_ids),
        "unserved_visit_ids": list(solution.unserved_visit_ids) if solution is not None else [],
        "total_energy_kwh": native["kpis"].get("net_battery_energy_kwh") if valid else None,
        "kpis": copy.deepcopy(native["kpis"]),
        "operations": copy.deepcopy(native["operations"]),
        "tuning": copy.deepcopy(native["tuning"]),
        "validation": {
            "feasible": bool(valid) if solution is not None and report is not None else None,
            "violations": list(report.violations) if report is not None else [],
            "checks": dict(report.checks) if report is not None else {},
            "scope": scope,
        },
        "phases": phases,
        "warnings": list(dict.fromkeys(warnings)),
        "assumptions": [
            *assumptions,
            f"SCIP por rutas sin H; un hilo, semilla 0; tolerancia energética "
            f"{100 * config.energy_relative_gap:g} %; política solicitada {policy}.",
            "El presupuesto de solver puede excederse por construcción, validación o sobrecostos de la biblioteca.",
        ],
        "network": {
            "type": network_kind,
            "vial": not synthetic
            and network_kind in {"osm", "road", "graphml", "directed_road_graph"},
            "geometry_source": "native_arc_geometry",
            "provenance_verified": False,
        },
        "metadata": {
            "native_run_id": native.get("run_id"),
            "native_status": native.get("status", solved.status),
            "lexicographic_optimal": solved.lexicographic_optimal,
            "time_limit_reached": time_limit_reached,
            "certificate_scope": solved.message,
            "formulation": native.get("formulation"),
            "native_solver": {
                "requested_solver": solved.requested_solver,
                "used_solver": solved.used_solver,
                "solver_version": solved.solver_version,
                "fallback_reason": solved.fallback_reason,
                "solution_source": solved.solution_source,
                "message": solved.message,
            },
        },
        "raw": {
            "effective_config": {
                "solver": config.model_dump(mode="json"),
                "search_policy": policy,
                **({"search": search_config.model_dump(mode="json")} if search_config else {}),
            },
            "result": native,
        },
        "runtime_seconds": {
            "preparation": None,
            "solver": native_times.get("resolution_including_model", solved.runtime_seconds),
            "total": None,
            "validation": native_times.get("validation"),
            "initial_solution_validation": native_times.get("initial_solution_validation"),
            "llm": native_times.get("llm"),
            "native_resolution_including_model": native_times.get("resolution_including_model"),
            "native_total": native_times.get("total"),
        },
    }


def run(instance, config, *, search_config=None, road_instance=None, path_archive=None):
    run_instance, SearchConfig = load_provider()
    try:
        native = run_instance(
            instance,
            config,
            search_config=search_config or SearchConfig(
                policy="standard", bedrock={"profile": None}, log_directory=None
            ),
            road_instance=road_instance, path_archive=path_archive,
            output_path=Path(search_config.log_directory).parent / "result.json"
            if search_config and search_config.log_directory else None,
        )
    except ImportError as exc:
        raise ProviderError(
            "Falta una dependencia del núcleo local/SCIP.", "provider_unavailable", 503
        ) from exc
    except Exception as exc:
        raise ProviderError(
            "El núcleo de Daniel no pudo completar la ejecución; revise la instancia y el entorno local."
        ) from exc
    return project_result(
        instance, config, native, road_instance=road_instance, search_config=search_config,
    )
