"""Versioned /solve boundary, adapted from deploy-aws service responsibilities.

Provider contract: evrp f88d012; deliberately not compatible with API 1.0.
No user supplied path, Python configuration, AWS settings or solver options execute.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
import uuid
from typing import Any

API_VERSION = "2.0-beta.1"
PROVIDER_COMMIT = "f88d0120c0b80087d718224b46b2613735cee69c"
MAX_NODES = 200
MAX_SEGMENTS = 200_000
CSV_FIELDS = {"node_id", "node_type", "latitude", "longitude", "address", "network",
              "total_ports", "dc_fast_ports", "level2_ports", "connector_types", "max_power_kw"}
ENERGY_FIELDS = {"usar_pendiente", "consumo_kwh_km", "masa_kg", "eta_traccion", "eta_regeneracion"}


class SolveRequestError(ValueError):
    """An actionable, safe validation error at the public boundary."""


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error", status: int = 502):
        super().__init__(message)
        self.code, self.status = code, status


def strict_loads(value: str | bytes) -> Any:
    def invalid(value):
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
        raise SolveRequestError("JSON inválido; use un objeto UTF-8 sin claves duplicadas.") from exc


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def object_fields(value, allowed, label, required=()):
    if not isinstance(value, dict):
        raise SolveRequestError(f"{label} debe ser un objeto JSON.")
    if set(value) - set(allowed):
        raise SolveRequestError(f"{label} contiene campos no admitidos: {', '.join(sorted(set(value) - set(allowed)))}.")
    if set(required) - set(value):
        raise SolveRequestError(f"{label}: faltan {', '.join(sorted(set(required) - set(value)))}.")
    return value


def number(value, label, minimum=None, maximum=None, *, integer=False, strings=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str) if strings else (int, float)):
        raise SolveRequestError(f"{label} debe ser un número finito.")
    try:
        n = float(value)
    except (ValueError, OverflowError) as exc:
        raise SolveRequestError(f"{label} debe ser un número finito.") from exc
    if not math.isfinite(n) or (minimum is not None and n < minimum) or (maximum is not None and n > maximum):
        raise SolveRequestError(f"{label} está fuera del rango admitido.")
    if integer and not n.is_integer():
        raise SolveRequestError(f"{label} debe ser entero.")
    return int(n) if integer else n


def text(value, label, maximum=4000):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise SolveRequestError(f"{label} debe ser texto válido de hasta {maximum} caracteres.")
    return value


def normalize_nodes(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_NODES:
        raise SolveRequestError(f"nodes debe contener entre 1 y {MAX_NODES} nodos.")
    result, seen = [], set()
    for i, row in enumerate(rows):
        object_fields(row, CSV_FIELDS, f"nodes[{i}]", ("node_id", "node_type", "latitude", "longitude"))
        nid = text(row["node_id"], "node_id", 256)
        if not nid.strip() or nid in seen:
            raise SolveRequestError("node_id debe ser único y no vacío.")
        seen.add(nid)
        kind = row["node_type"]
        if not isinstance(kind, str) or kind not in {"base", "visit", "charger"}:
            raise SolveRequestError("node_type debe ser base, visit o charger.")
        out = {"node_id": nid, "node_type": kind,
               "latitude": number(row["latitude"], "latitude", -90, 90, strings=True),
               "longitude": number(row["longitude"], "longitude", -180, 180, strings=True)}
        for field in ("address", "network", "connector_types"):
            value = row.get(field)
            out[field] = text("" if value is None else value, field)
        out["connector_types"] = ";".join(c.strip() for c in out["connector_types"].split(";") if c.strip())
        for field in ("total_ports", "dc_fast_ports", "level2_ports", "max_power_kw"):
            value = row.get(field)
            out[field] = None if value is None or value == "" else number(
                value, field, 0, integer=field != "max_power_kw", strings=True)
        total, dc, level2 = (out[k] for k in ("total_ports", "dc_fast_ports", "level2_ports"))
        if total is not None and (sum(v or 0 for v in (dc, level2)) > total):
            raise SolveRequestError(f"Puertos inconsistentes en {nid}: DC + nivel 2 supera total_ports.")
        result.append(out)
    if sum(n["node_type"] == "base" for n in result) != 1:
        raise SolveRequestError("La instancia debe contener exactamente una base.")
    return result


def validate_prepared(prepared):
    object_fields(prepared, {"esquema", "nodos", "tramos", "geometrias", "red", "energia_caminos", "origen"},
                  "prepared", ("esquema", "nodos", "tramos", "red", "energia_caminos"))
    if prepared["esquema"] != "evrp.instancia_preparada/1":
        raise SolveRequestError("Esquema preparado no admitido; se requiere evrp.instancia_preparada/1.")
    native = prepared["nodos"]
    if not isinstance(native, list) or not 1 <= len(native) <= MAX_NODES:
        raise SolveRequestError("prepared.nodos excede el tamaño admitido o está vacío.")
    rows, filas = [], set()
    for n in native:
        object_fields(n, {"id", "tipo", "lat", "lon", "fila", "conectores", "puertos", "potencia_kw", "direccion", "operador"},
                      "prepared.nodos", ("id", "tipo", "lat", "lon", "fila", "conectores"))
        if not isinstance(n["tipo"], str) or n["tipo"] not in {"base", "cliente", "cargador"}:
            raise SolveRequestError("Tipo de nodo preparado no admitido.")
        fila = number(n["fila"], "fila", 0, integer=True)
        if fila in filas:
            raise SolveRequestError("prepared.nodos contiene índices fila duplicados.")
        filas.add(fila)
        if not isinstance(n["conectores"], list) or not all(isinstance(c, str) for c in n["conectores"]):
            raise SolveRequestError("conectores debe ser una lista de texto.")
        rows.append({"node_id": n["id"], "node_type": {"base": "base", "cliente": "visit", "cargador": "charger"}[n["tipo"]],
                     "latitude": n["lat"], "longitude": n["lon"], "address": n.get("direccion", ""),
                     "network": n.get("operador", ""), "connector_types": ";".join(n["conectores"]),
                     "total_ports": n.get("puertos"), "max_power_kw": n.get("potencia_kw")})
    nodes = normalize_nodes(rows)
    pairs = {}
    for a in nodes:
        for b in nodes:
            key = f'{a["node_id"]}|{b["node_id"]}'
            if key in pairs:
                raise SolveRequestError("Serialización preparada ambigua por IDs con '|'; vuelva a preparar desde los nodos originales.")
            pairs[key] = (a["node_id"], b["node_id"])
    segments = prepared["tramos"]
    if not isinstance(segments, dict) or not isinstance(prepared.get("geometrias", {}), dict):
        raise SolveRequestError("tramos y geometrias deben ser objetos por par de nodos.")
    required = {key for key, (a, b) in pairs.items() if a != b}
    if not required.issubset(segments):
        raise SolveRequestError("La preparada no cubre todos los pares dirigidos de nodos.")
    positions = {n["node_id"]: (n["latitude"], n["longitude"]) for n in nodes}
    total_points = 0
    for name, collection in (("tramos", segments), ("geometrias", prepared.get("geometrias", {}))):
        for key, values in collection.items():
            if key not in pairs or not isinstance(values, list):
                raise SolveRequestError(f"{name} contiene una referencia inexistente o una secuencia inválida.")
            origin, destination = pairs[key]
            if name == "tramos" and origin == destination and values:
                raise SolveRequestError("Los tramos de permanencia deben estar vacíos; el proveedor no recorre autoarcos.")
            if name == "tramos" and not values and positions[origin] != positions[destination]:
                raise SolveRequestError("Un camino entre coordenadas distintas no puede tener una secuencia vacía.")
            total_points += len(values)
            if total_points > MAX_SEGMENTS:
                raise SolveRequestError("La preparada excede el límite de segmentos/geometrías de esta beta.")
            if name == "geometrias" and len(values) < 2:
                raise SolveRequestError("Cada geometría guardada requiere al menos dos puntos.")
            for pair in values:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise SolveRequestError(f"Cada elemento de {name} debe tener dos números.")
                if name == "tramos":
                    number(pair[0], "distancia km", 0); number(pair[1], "desnivel m")
                else:
                    number(pair[0], "geometría latitude", -90, 90); number(pair[1], "geometría longitude", -180, 180)
    energy = object_fields(prepared["energia_caminos"], ENERGY_FIELDS, "energia_caminos", ENERGY_FIELDS)
    if type(energy["usar_pendiente"]) is not bool:
        raise SolveRequestError("usar_pendiente debe ser booleano.")
    for key in ("consumo_kwh_km", "masa_kg"):
        number(energy[key], key, 1e-12)
    number(energy["eta_traccion"], "eta_traccion", 1e-12, 1)
    number(energy["eta_regeneracion"], "eta_regeneracion", 0, 1)
    if (not isinstance(prepared["red"], dict) or not isinstance(prepared["red"].get("tipo"), str)
            or prepared["red"]["tipo"] not in {"osm", "haversine", "preparada"}):
        raise SolveRequestError("prepared.red.tipo debe ser osm, haversine o preparada.")
    if not isinstance(prepared.get("origen", {}), dict):
        raise SolveRequestError("prepared.origen debe ser un objeto.")
    return nodes, pairs


def validate_request(payload):
    object_fields(payload, {"api_version", "nodes", "prepared", "fleet", "solver", "network_mode", "exclude_node_ids"},
                  "petición", ("api_version", "fleet"))
    try:
        json_bytes(payload)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise SolveRequestError("La petición debe ser JSON finito válido.") from exc
    if payload["api_version"] != API_VERSION:
        raise SolveRequestError(f"api_version debe ser {API_VERSION}.")
    if ("nodes" in payload) == ("prepared" in payload):
        raise SolveRequestError("Envíe nodes o prepared, exactamente una entrada.")
    native = payload.get("prepared")
    if "prepared" in payload:
        if "network_mode" in payload:
            raise SolveRequestError("prepared ya contiene la red; no admite network_mode.")
        nodes, pairs = validate_prepared(native)
        energy = dict(native["energia_caminos"])
    else:
        if payload.get("network_mode") != "haversine":
            raise SolveRequestError("Para nodes confirme network_mode='haversine': referencia sin red vial.")
        nodes, pairs = normalize_nodes(payload["nodes"]), None
        energy = {"usar_pendiente": False, "masa_kg": 1590., "eta_traccion": .9, "eta_regeneracion": .6}
    f = object_fields(payload["fleet"], {"num_vehicles", "battery_capacity_kwh", "reserve_kwh", "initial_soc", "consumption_kwh_km"},
                      "fleet", ("battery_capacity_kwh", "reserve_kwh"))
    fleet = {"num_vehicles": number(f.get("num_vehicles", 2), "num_vehicles", 1, 20, integer=True),
             "battery_capacity_kwh": number(f["battery_capacity_kwh"], "battery_capacity_kwh", 1e-9),
             "reserve_kwh": number(f["reserve_kwh"], "reserve_kwh", 1e-9),
             "initial_soc": number(f.get("initial_soc", .6), "initial_soc", 1e-9, 1)}
    if fleet["reserve_kwh"] > fleet["initial_soc"] * fleet["battery_capacity_kwh"]:
        raise SolveRequestError("reserve_kwh no puede superar la batería inicial.")
    consumption = f.get("consumption_kwh_km", energy.get("consumo_kwh_km"))
    fleet["consumption_kwh_km"] = number(consumption, "consumption_kwh_km", 1e-12)
    if native is not None and not math.isclose(fleet["consumption_kwh_km"], energy["consumo_kwh_km"], rel_tol=0, abs_tol=1e-12):
        raise SolveRequestError("consumption_kwh_km difiere de la preparada; vuelva a preparar la red.")
    energy["consumo_kwh_km"] = fleet["consumption_kwh_km"]
    solver = object_fields(payload.get("solver", {}), {"time_limit_seconds"}, "solver")
    seconds = number(solver.get("time_limit_seconds", 30), "time_limit_seconds", 1, 120)
    excluded = payload.get("exclude_node_ids", [])
    ids = {n["node_id"] for n in nodes}
    if not isinstance(excluded, list) or not all(isinstance(i, str) for i in excluded) or len(set(excluded)) != len(excluded):
        raise SolveRequestError("exclude_node_ids debe ser una lista de IDs únicos.")
    if not set(excluded).issubset(ids):
        raise SolveRequestError("exclude_node_ids contiene un ID inexistente.")
    if any(n["node_type"] == "base" and n["node_id"] in excluded for n in nodes):
        raise SolveRequestError("No se puede excluir la base.")
    return {"nodes": nodes, "prepared": native, "pairs": pairs, "fleet": fleet,
            "energy": energy, "time_limit_seconds": seconds, "excluded": excluded}


def solve(payload):
    started = time.perf_counter()
    validated = validate_request(payload)
    from .evrp_adapter import run
    result = run(validated)
    result["run_id"] = str(uuid.uuid4())
    result["raw"]["input"] = copy.deepcopy(payload)
    prepared = result["raw"]["prepared"]
    network_identity = {key: prepared[key] for key in ("esquema", "nodos", "tramos", "geometrias", "energia_caminos")}
    network_identity["red"] = {key: value for key, value in prepared["red"].items() if key != "tiempos"}
    result["metadata"].update(provider="evrp", provider_commit=PROVIDER_COMMIT,
                              input_hash=fingerprint(payload),
                              config_hash=fingerprint(result["raw"]["effective_config"]),
                              network_hash=fingerprint(network_identity))
    result["runtime_seconds"]["total"] = time.perf_counter() - started
    envelope = {"api_version": API_VERSION, "result": result}
    json_bytes(envelope)
    return envelope


def health():
    from .evrp_adapter import provider_available
    return {"status": "ok", "api_version": API_VERSION, "provider": "evrp",
            "provider_commit": PROVIDER_COMMIT, "provider_available": provider_available()}
