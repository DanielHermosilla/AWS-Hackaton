"""API 3.0: road/synthetic preparation and the shared native solver pipeline.

The HTTP boundary never accepts file paths, free solver options, or AWS settings.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path
from typing import Any

API_VERSION = "3.0"
PROVIDER_COMMIT = "ab67dc6b88a720f274789bb0dace8e47a68a7460"
MAX_PREPARE_NODES = 200
MAX_NATIVE_NODES = 20_000
MAX_NATIVE_ARCS = 200_000
CSV_FIELDS = {
    "node_id",
    "node_type",
    "latitude",
    "longitude",
    "address",
    "network",
    "total_ports",
    "dc_fast_ports",
    "level2_ports",
    "connector_types",
    "max_power_kw",
}


class SolveRequestError(ValueError):
    """Safe, actionable validation error at the HTTP boundary."""


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error", status: int = 502):
        super().__init__(message)
        self.code, self.status = code, status


def strict_loads(value: str | bytes) -> Any:
    def invalid(_):
        raise SolveRequestError("JSON no permite NaN ni Infinity.")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise SolveRequestError("JSON contiene una clave duplicada.")
            out[key] = value
        return out

    try:
        return json.loads(value, parse_constant=invalid, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, SolveRequestError):
            raise
        raise SolveRequestError(
            "JSON inválido; use un objeto UTF-8 sin claves duplicadas."
        ) from exc


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )


def fingerprint(value: Any) -> str:
    def canonical_numbers(item):
        # JSON/JavaScript has one number type: JSON.stringify writes 24.0 as 24.
        # Normalize that representation only, without numerical tolerances or
        # coercion of booleans/strings. Otherwise a browser cannot return a
        # prepared context whose hash was produced by Python.
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, dict):
            return {key: canonical_numbers(v) for key, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [canonical_numbers(v) for v in item]
        return item

    return hashlib.sha256(
        json.dumps(
            canonical_numbers(value),
            ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def object_fields(value, allowed, label, required=()):
    if not isinstance(value, dict):
        raise SolveRequestError(f"{label} debe ser un objeto JSON.")
    if set(value) - set(allowed):
        raise SolveRequestError(
            f"{label} contiene campos no admitidos: {', '.join(sorted(set(value) - set(allowed)))}."
        )
    if set(required) - set(value):
        raise SolveRequestError(f"{label}: faltan {', '.join(sorted(set(required) - set(value)))}.")
    return value


def number(value, label, minimum=None, maximum=None, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SolveRequestError(f"{label} debe ser un número finito.")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise SolveRequestError(f"{label} está fuera del rango numérico admitido.") from exc
    if not finite:
        raise SolveRequestError(f"{label} debe ser un número finito.")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise SolveRequestError(f"{label} está fuera del rango admitido.")
    if integer and int(value) != value:
        raise SolveRequestError(f"{label} debe ser entero.")
    return int(value) if integer else float(value)


def _finite_json(value):
    try:
        return json_bytes(value)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise SolveRequestError("La petición debe ser JSON finito válido.") from exc


def _models():
    try:
        import ev_routing

        expected = Path(__file__).resolve().parents[1] / "src" / "ev_routing"
        if not Path(ev_routing.__file__).resolve().is_relative_to(expected.resolve()):
            raise ProviderError(
                "Los contratos deben cargarse desde el núcleo local src/ev_routing.",
                "provider_unavailable",
                503,
            )
        from ev_routing.contracts import Node, ProblemInstance, SolverConfig

        return Node, ProblemInstance, SolverConfig
    except ImportError as exc:
        raise ProviderError(
            "El núcleo ev_routing no está instalado; sincronice el entorno del proyecto.",
            "provider_unavailable",
            503,
        ) from exc


def _validate_model(model, value, label):
    try:
        # JSON strict validation permits native geometry arrays as tuples, while
        # rejecting bool/string coercion into physical numeric fields.
        return model.model_validate_json(_finite_json(value), strict=True)
    except ValueError as exc:
        if isinstance(exc, SolveRequestError):
            raise
        errors = getattr(exc, "errors", lambda **_: [])(include_url=False, include_input=False)
        details = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in errors[:6]
        )
        raise SolveRequestError(
            f"{label} inválida. {details or 'Revise su esquema y valores.'}"
        ) from exc


def _native_instance(value, *, prepared=False):
    _, ProblemInstance, _ = _models()
    if not isinstance(value, dict) or value.get("schema_version") not in ("1.0", "1.1"):
        raise SolveRequestError(
            "instance debe ser un objeto ProblemInstance con schema_version 1.0 o 1.1."
        )
    provenance = value.get("provenance", {})
    representation = provenance.get("representation") if isinstance(provenance, dict) else None
    kind = representation.get("kind") if isinstance(representation, dict) else representation
    if not prepared and kind in ("service_paths_nonnegative", "resource_paths"):
        raise SolveRequestError(
            "La representación de caminos requiere una preparación vial del servidor "
            "con red original y archivo de caminos. Cargue los arcos elementales o prepare el CSV."
        )
    if representation is not None and not isinstance(representation, dict):
        raise SolveRequestError("provenance.representation debe ser un objeto.")
    if kind is not None and not isinstance(kind, str):
        raise SolveRequestError("provenance.representation.kind debe ser texto.")
    if (
        not isinstance(value.get("nodes"), list)
        or not 1 <= len(value["nodes"]) <= MAX_NATIVE_NODES
        or not isinstance(value.get("arcs"), list)
        or len(value["arcs"]) > MAX_NATIVE_ARCS
    ):
        raise SolveRequestError(
            "La instancia supera el límite local de nodos/arcos o sus listas son inválidas."
        )
    instance = _validate_model(ProblemInstance, value, "Instancia nativa")
    if any(not node.node_id.strip() for node in instance.nodes):
        raise SolveRequestError("node_id no puede estar vacío o contener solo espacios.")
    for arc in instance.arcs:
        if any(abs(lat) > 90 or abs(lon) > 180 for lat, lon in arc.geometry):
            raise SolveRequestError(
                "La geometría nativa debe usar pares [latitud,longitud] dentro de sus rangos."
            )
    return instance


def available_solver_threads():
    """Allow all CPUs available to the process, within SCIP's 64-thread limit."""
    if hasattr(os, "sched_getaffinity"):
        count = len(os.sched_getaffinity(0))
    else:
        count = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    return max(1, min(count, 64))


def validate_request(payload, *, runtime=None):
    object_fields(
        payload,
        {"api_version", "instance", "solver", "prepared_instance_id"},
        "petición",
        ("api_version", "instance", "solver"),
    )
    _finite_json(payload)
    if payload["api_version"] != API_VERSION:
        raise SolveRequestError(
            "La instancia usa una versión incompatible. Cargue un archivo de la API 3.0."
        )
    solver = object_fields(
        payload["solver"], {"time_limit_seconds", "search_policy", "energy_relative_gap", "random_seed"}, "solver",
        ("time_limit_seconds",),
    )
    seconds = number(solver["time_limit_seconds"], "time_limit_seconds", 1, 120)
    energy_gap = number(solver.get("energy_relative_gap", .005), "El gap de optimalidad", 0, 1)
    seed = number(solver.get("random_seed", 0), "La semilla", 0, 2_000_000_000, integer=True)
    policy = solver.get("search_policy", "standard")
    if not isinstance(policy, str) or policy not in {"standard", "adaptive", "deterministic"}:
        raise SolveRequestError("search_policy debe ser standard, deterministic o adaptive.")
    prepared = "prepared_instance_id" in payload
    if prepared:
        if runtime is None:
            raise SolveRequestError("La preparación vial no está disponible; vuelva a prepararla.")
        context = runtime.get_context(payload["prepared_instance_id"], payload["instance"])
        instance = context.instance
    else:
        instance = _native_instance(payload["instance"])
    _, _, SolverConfig = _models()
    config = SolverConfig(
        solver="scip-routes",
        time_limit_seconds=seconds,
        threads=available_solver_threads(),
        seed=seed,
        relative_gap=0,
        energy_relative_gap=energy_gap,
        tee=False,
    )
    return instance, config


def prepare(payload, *, runtime=None):
    object_fields(
        payload,
        {"api_version", "nodes", "fleet", "network_mode", "operations"},
        "preparación",
        ("api_version", "nodes", "fleet", "network_mode"),
    )
    _finite_json(payload)
    if payload["api_version"] != API_VERSION or payload["network_mode"] not in (
        "haversine", "road",
    ):
        raise SolveRequestError(
            "Confirme api_version='3.0' y network_mode='road' o 'haversine'."
        )
    from ev_routing.contracts import Operations

    operations = _validate_model(Operations, payload.get("operations", {}), "Operaciones")
    rows = payload["nodes"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PREPARE_NODES:
        raise SolveRequestError(
            f"La preparación admite entre 1 y {MAX_PREPARE_NODES} ubicaciones."
        )
    fleet = object_fields(
        payload["fleet"],
        {
            "num_vehicles",
            "battery_capacity_kwh",
            "reserve_kwh",
            "initial_soc",
            "consumption_kwh_km",
            "vehicle_connector_types",
        },
        "fleet",
        ("battery_capacity_kwh", "reserve_kwh", "consumption_kwh_km"),
    )
    count = number(fleet.get("num_vehicles", 2), "num_vehicles", 1, 20, integer=True)
    capacity = number(fleet["battery_capacity_kwh"], "battery_capacity_kwh", 1e-12)
    reserve = number(fleet["reserve_kwh"], "reserve_kwh", 1e-12)
    soc = number(fleet.get("initial_soc", 0.6), "initial_soc", 1e-12, 1)
    consumption = number(fleet["consumption_kwh_km"], "consumption_kwh_km", 1e-12)
    connectors = fleet.get("vehicle_connector_types", ["J1772", "CHAdeMO"])
    if not isinstance(connectors, list) or not all(
        isinstance(c, str) and c.strip() for c in connectors
    ):
        raise SolveRequestError(
            "vehicle_connector_types debe ser una lista de conectores explícitos."
        )
    Node, _, _ = _models()
    nodes = []
    for row in rows:
        object_fields(
            row, CSV_FIELDS, "nodo CSV", ("node_id", "node_type", "latitude", "longitude")
        )
        data = copy.deepcopy(row)
        if not isinstance(data["node_type"], str) or data["node_type"] not in {
            "base",
            "visit",
            "charger",
        }:
            raise SolveRequestError("Los nodos CSV deben ser base, visit o charger.")
        connector_text = data.get("connector_types", "")
        if not isinstance(connector_text, str):
            raise SolveRequestError("connector_types CSV debe ser texto separado por ';'.")
        data["connector_types"] = list(
            dict.fromkeys(c.strip() for c in connector_text.split(";") if c.strip())
        )
        node = _validate_model(Node, data, "Nodo CSV")
        if node.latitude is None or node.longitude is None:
            raise SolveRequestError(
                "La preparación haversine requiere coordenadas en todos los nodos."
            )
        total, dc, level2 = node.total_ports, node.dc_fast_ports, node.level2_ports
        if total is not None and sum(v or 0 for v in (dc, level2)) > total:
            raise SolveRequestError(
                f"Puertos inconsistentes en {node.node_id}: DC + nivel 2 supera el total."
            )
        nodes.append(node.model_dump(mode="json"))
    if payload["network_mode"] == "road":
        if runtime is None:
            raise SolveRequestError("Configure --graphml en el servidor para preparar calles.")
        from ev_routing.contracts import ModelParameters

        parameters = _validate_model(ModelParameters, {
            "vehicle_count": count, "battery_capacity_kwh": capacity,
            "reserve_kwh": reserve, "initial_soc": soc,
            "vehicle_connector_types": connectors,
        }, "Parámetros de flota")
        identifier, context, reused = runtime.prepare_road(
            [_validate_model(Node, n, "Nodo") for n in nodes], parameters, consumption,
            copy.deepcopy(payload),
        )
        return {
            "api_version": API_VERSION,
            "instance": context.instance.model_dump(mode="json"),
            "prepared_instance_id": identifier,
            "preparation": {"runtime_seconds": context.seconds, "reused": reused},
        }
    arcs = []
    for origin in nodes:
        for destination in nodes:
            if origin is destination:
                continue
            lat1, lon1, lat2, lon2 = map(
                math.radians,
                (
                    origin["latitude"],
                    origin["longitude"],
                    destination["latitude"],
                    destination["longitude"],
                ),
            )
            h = (
                math.sin((lat2 - lat1) / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
            )
            distance_m = 2 * 6_371_009 * math.asin(min(1.0, math.sqrt(max(0.0, h))))
            arcs.append(
                {
                    "from_node_id": origin["node_id"],
                    "to_node_id": destination["node_id"],
                    "distance_m": distance_m,
                    "energy_kwh": distance_m / 1000 * consumption,
                    "geometry": [
                        [origin["latitude"], origin["longitude"]],
                        [destination["latitude"], destination["longitude"]],
                    ],
                }
            )
    instance = _native_instance(
        {
            "schema_version": "1.0",
            "name": "Escenario geodésico sintético",
            "nodes": nodes,
            "arcs": arcs,
            "parameters": {
                "vehicle_count": count,
                "battery_capacity_kwh": capacity,
                "reserve_kwh": reserve,
                "initial_soc": soc,
                "vehicle_connector_types": connectors,
            },
            "operations": operations.model_dump(mode="json"),
            "provenance": {
                "kind": "synthetic",
                "network": {"kind": "haversine", "vial": False, "geometry_source": "synthetic_haversine"},
                "consumption_kwh_km": consumption,
                "assumptions": [
                    "Red completa geodésica sintética; no representa calles ni restricciones de circulación.",
                    "Energía supuesta como distancia geodésica por consumo configurado; sin pendiente.",
                    "Las líneas del mapa unen las ubicaciones por distancia; no representan calles.",
                    "La coincidencia de conectores es textual y sensible a mayúsculas, conforme al contrato nativo.",
                ],
            },
        }
    )
    return {"api_version": API_VERSION, "instance": instance.model_dump(mode="json")}


def solve(payload, *, runtime=None):
    started = time.perf_counter()
    instance, config = validate_request(payload, runtime=runtime)
    prepared_seconds = time.perf_counter() - started
    from .daniel_adapter import run
    from .runtime import Runtime

    runtime = runtime or Runtime()
    run_id = str(uuid.uuid4())
    context = runtime.get_context(payload["prepared_instance_id"], payload["instance"]) \
        if "prepared_instance_id" in payload else None
    search = runtime.search_config(payload["solver"].get("search_policy", "standard"), run_id)
    config.tee = runtime.tee
    result = run(
        instance, config, search_config=search,
        road_instance=context.road if context else None,
        path_archive=context.archive if context else None,
    )
    result["run_id"] = run_id
    canonical = instance.model_dump(mode="json")
    result["raw"].update(input=copy.deepcopy(payload), instance=canonical)
    result["metadata"].update(
        provider="ev_routing",
        provider_commit=PROVIDER_COMMIT,
        native_schema_version=instance.schema_version,
        input_hash=fingerprint(canonical),
        config_hash=fingerprint(result["raw"]["effective_config"]),
        network_hash=fingerprint(
            {
                "nodes": canonical["nodes"],
                "arcs": canonical["arcs"],
                "provenance": canonical["provenance"],
            }
        ),
    )
    result["runtime_seconds"]["preparation"] = prepared_seconds
    result["runtime_seconds"]["road_preprocessing"] = context.seconds if context else None
    result["runtime_seconds"]["total"] = time.perf_counter() - started
    if context:
        result["raw"]["prepare_request"] = copy.deepcopy(context.request)
        result["metadata"]["road_instance_sha256"] = context.archive.road_instance_sha256
    envelope = {"api_version": API_VERSION, "result": result}
    json_bytes(envelope)
    return envelope


def health(*, runtime=None):
    from .daniel_adapter import provider_available

    return {
        "status": "ok",
        "api_version": API_VERSION,
        "provider": "ev_routing",
        "provider_commit": PROVIDER_COMMIT,
        "native_schema_version": "1.0",
        "native_schema_versions": ["1.0", "1.1"],
        "provider_available": provider_available(),
        "capabilities": {
            "road_preparation": runtime is not None and runtime.graphml is not None,
            "search_policies": ["standard", "deterministic", "adaptive"],
            "energy_relative_gap": 0.005,
        },
    }
