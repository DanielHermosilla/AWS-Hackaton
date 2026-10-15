"""The pinned evrp public API translated into the beta presentation contract.

The upstream remains unmodified. Its contracted model is not certified equivalent
here to modelamiento.pdf; raw traces retain their original meaning and ID mapping.
"""
from __future__ import annotations

import copy
import csv
import math
from pathlib import Path
import subprocess
import tempfile
import time

from .service import CSV_FIELDS, PROVIDER_COMMIT, ProviderError


def load_provider():
    try:
        import evrp
        import highspy
        from evrp import config
        from evrp.preparacion import InstanciaPreparada
    except ImportError as exc:
        raise ProviderError("El entorno del proveedor evrp/HiGHS no está disponible. Inicie el servidor con el entorno fijado.",
                            "provider_unavailable", 503) from exc
    root = Path(evrp.__file__).resolve().parents[2]
    try:
        actual = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        clean = subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", "src/evrp", "pyproject.toml", "uv.lock"],
                               capture_output=True, check=False, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError("No se pudo verificar el checkout fijado del proveedor.", "provider_unavailable", 503) from exc
    if actual != PROVIDER_COMMIT or not clean:
        raise ProviderError("El proveedor no coincide con el commit fijado o tiene cambios locales. Use el checkout evrp documentado.",
                            "provider_version_mismatch", 503)
    if highspy.Highs().version() != "1.11.0":
        raise ProviderError("La beta requiere HiGHS 1.11.0 del lockfile del proveedor.", "provider_version_mismatch", 503)
    return evrp, config, InstanciaPreparada


def provider_available():
    try:
        load_provider()
        return True
    except ProviderError:
        return False


def effective_config(validated, config_module):
    f, e, seconds = validated["fleet"], validated["energy"], validated["time_limit_seconds"]
    cfg = config_module.cargar(sobrescribir={
        "flota": [{"tipo": "leaf2013", "cantidad": f["num_vehicles"]}],
        "tipos_vehiculo": {"leaf2013": {
            "bateria_kwh": f["battery_capacity_kwh"], "reserva_kwh": f["reserve_kwh"],
            "soc_inicial": f["initial_soc"], "consumo_kwh_km": e["consumo_kwh_km"],
            "masa_kg": e["masa_kg"], "eta_traccion": e["eta_traccion"], "eta_regeneracion": e["eta_regeneracion"],
            "conectores": ["CHADEMO", "J1772"],
        }},
        "pipeline": {"red": "haversine", "energia": "pendiente" if e["usar_pendiente"] else "plano",
                     "cargadores": "todos", "inicial": "insercion", "solver": "milp"},
        "red": {"factor_vial": 1., "osm_grafo": None, "osm_permitir_descarga": False,
                "respaldo_linea_recta": False, "elevacion": "ninguna", "elevacion_csv": None,
                "osm_cache": None, "cache_adyacencia": False},
        "escala": {"k_vecinos": 0, "min_s": .5, "overshoot_margen_s": .1},
        # Use one formulation to avoid upstream's compacta → completa retry using
        # the budget twice. The bound is a solver budget, not a wall-clock guarantee.
        "solver": {"tiempo_limite_s": seconds, "presupuesto_total_s": seconds,
                   "formulacion": "completa", "conectividad": "flujo", "hilos": 1,
                   "mostrar_log": False, "usar_todos_vehiculos": False},
        "asesor": {"tipo": "ninguno", "sugerir_config": False, "explicar": False,
                   "region": None, "perfil_aws": None, "modelo": None},
    })
    # All admitted vehicle types must match path selection energy. The beta accepts
    # one homogeneous fleet and explicitly rejects extra fleet/config fields.
    for group in cfg["flota"]:
        t = cfg["tipos_vehiculo"][group["tipo"]]
        if any(not math.isclose(t[k], e[k], rel_tol=0, abs_tol=1e-12)
               for k in ("consumo_kwh_km", "masa_kg", "eta_traccion", "eta_regeneracion")):
            raise ProviderError("La energía de la flota no coincide con la preparación.")
    return cfg


def prepare(validated, cfg, evrp, prepared_class, encode):
    native = validated["prepared"]
    if native is not None:
        d = copy.deepcopy(native)
        # Decode a native pair only using the complete unambiguous lookup validated
        # at the boundary, never split opaque IDs on a delimiter.
        d["nodos"] = [{**n, "id": encode[n["id"]]} for n in d["nodos"]]
        for name in ("tramos", "geometrias"):
            d[name] = {"|".join(encode[i] for i in validated["pairs"][key]): values
                       for key, values in native.get(name, {}).items()}
        return prepared_class.desde_dict(d)
    with tempfile.TemporaryDirectory(prefix="zmd-beta-") as directory:
        path = Path(directory) / "nodes.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=sorted(CSV_FIELDS))
            writer.writeheader()
            for node in validated["nodes"]:
                writer.writerow({**node, "node_id": encode[node["node_id"]]})
        prepared = evrp.preparar(path, config=cfg, geometria=True)
    prepared.origen["archivo"] = "api-nodes.csv"
    return prepared


def strict_provider_result(raw):
    """Only unavailable solver statistics may become null; physical data may not."""
    unavailable = []
    def visit(value, path):
        if isinstance(value, float) and not math.isfinite(value):
            statistic = (path.startswith("result.kpis.solver.") or path.startswith("result.bitacora.")) and path.rsplit(".", 1)[-1] in {"cota", "gap"}
            if not statistic:
                raise ProviderError("El proveedor devolvió un dato físico no finito; el resultado no puede presentarse.", "invalid_provider_result")
            unavailable.append({"path": path, "reason": "Estadística no finita/no disponible en el proveedor", "provider_value": repr(value)})
            return None
        if isinstance(value, dict):
            return {str(k): visit(v, f"{path}.{k}") for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v, f"{path}.{i}") for i, v in enumerate(value)]
        return value
    return visit(raw, "result"), unavailable


def _geometry(route_ids, prepared):
    points = []
    positions = {n.id: (n.lat, n.lon) for n in prepared.nodos}
    for origin, destination in zip(route_ids, route_ids[1:]):
        if origin == destination:
            continue
        # Do not call RedPreparada.geometria(): it invents a straight line when absent.
        sequence = prepared.geometrias.get((origin, destination))
        if not sequence:
            return None
        # RedOSM keeps the original node positions at both ends; snaps are
        # interior points. a_dict rounds geometry to 6 decimals but not nodes.
        # Admit only that rounding error (plus floating slack), never snap radius.
        for endpoint, node_id in ((sequence[0], origin), (sequence[-1], destination)):
            if any(not math.isclose(actual, expected, rel_tol=0, abs_tol=5e-7 + 1e-12)
                   for actual, expected in zip(endpoint, positions[node_id])):
                return None
        coords = [[float(lon), float(lat)] for lat, lon in sequence]
        if points:
            if points[-1] != coords[0]:
                return None
            coords = coords[1:]
        points.extend(coords)
    return {"type": "LineString", "coordinates": points} if len(points) >= 2 else None


def present(validated, prepared, cfg, raw, decode):
    nodes = [n for n in validated["nodes"] if n["node_id"] not in validated["excluded"]]
    by_id = {n["node_id"]: n for n in nodes}
    base = next(n["node_id"] for n in nodes if n["node_type"] == "base")
    f = validated["fleet"]
    fleet = [{"id": str(i + 1), "type": "leaf2013", "label": f"Nissan Leaf 2013 · {i + 1}",
              "battery_capacity_kwh": f["battery_capacity_kwh"], "reserve_kwh": f["reserve_kwh"],
              "initial_soc": f["initial_soc"]} for i in range(f["num_vehicles"])]
    kpis = raw["kpis"]
    violations = []
    for event in raw.get("bitacora", []):
        if event.get("paso") == "validacion":
            for error in event.get("errores", []):
                message = str(error)
                for encoded, original in decode.items():
                    message = message.replace(encoded, original)
                violations.append(message)
    warnings = [
        "Consumo efectivo no disponible: el proveedor mezcla políticas de recarga en sus KPIs; se conserva el detalle y la salida original.",
        "No se publica un certificado de optimalidad ni equivalencia con el modelo vial base; las trazas originales están en la exportación.",
    ]
    routes, served, total_balance = [], set(), 0.
    # validador._simular independently rounds each detail value to 4 decimals.
    rounding_tolerance = 5e-5 + 1e-12
    boundary_precision_unavailable = False
    actual_routes = raw.get("rutas", {})
    if set(actual_routes) != {v["id"] for v in fleet}:
        raise ProviderError("Las rutas del proveedor no corresponden a la flota solicitada.", "invalid_provider_result")
    for vehicle in fleet:
        vid = vehicle["id"]
        encoded_route = actual_routes[vid]
        try:
            ids = [decode[n] for n in encoded_route]
        except KeyError as exc:
            raise ProviderError("La ruta del proveedor refiere a un nodo desconocido.", "invalid_provider_result") from exc
        if not ids or any(n not in by_id for n in ids):
            raise ProviderError("La ruta contiene nodos inexistentes o excluidos.", "invalid_provider_result")
        if ids[0] != base or ids[-1] != base:
            violations.append(f"Vehículo {vid}: la ruta no empieza y termina en la base.")
        details = raw.get("detalle", {}).get(vid, [])
        if len(details) != len(ids) - 1:
            raise ProviderError("El detalle de batería no coincide con las paradas del proveedor.", "invalid_provider_result")
        initial = f["battery_capacity_kwh"] * f["initial_soc"]
        steps = [{"position": 0, "node_id": ids[0], "arrival_energy_kwh": initial,
                  "departure_energy_kwh": initial, "charge_kwh": 0., "energy_kwh": None,
                  "delivered_visit_ids": []}]
        visits, charges = [], 0.
        previous_departure = initial
        for pos, (nid, detail) in enumerate(zip(ids[1:], details), 1):
            if decode.get(detail.get("nodo")) != nid:
                raise ProviderError("El detalle del proveedor está asociado a otra parada.", "invalid_provider_result")
            arrival = detail["bateria_llegada_kwh"]
            departure = detail["bateria_salida_kwh"]
            charge = detail["carga_kwh"]
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
                   for v in (arrival, departure, charge)):
                raise ProviderError("La batería del proveedor no es un número finito.", "invalid_provider_result")
            if (arrival < f["reserve_kwh"] - rounding_tolerance or departure < f["reserve_kwh"] - rounding_tolerance or
                arrival > f["battery_capacity_kwh"] + rounding_tolerance or departure > f["battery_capacity_kwh"] + rounding_tolerance or
                charge < 0 or not math.isclose(arrival + charge, departure, abs_tol=.0002)):
                violations.append(f"Vehículo {vid}, parada {pos}: balance/capacidad/reserva incoherente.")
            readings = {"arrival_energy_kwh": arrival, "departure_energy_kwh": departure}
            for field, value in readings.items():
                if ((f["reserve_kwh"] - rounding_tolerance <= value < f["reserve_kwh"]) or
                    (f["battery_capacity_kwh"] < value <= f["battery_capacity_kwh"] + rounding_tolerance)):
                    readings[field] = None
                    boundary_precision_unavailable = True
            if charge > .0002 and by_id[nid]["node_type"] != "charger":
                violations.append(f"Vehículo {vid}, parada {pos}: recarga fuera de un cargador.")
            delivered = [nid] if by_id[nid]["node_type"] == "visit" else []
            if delivered:
                if nid in served:
                    violations.append(f"Entrega {nid} repetida entre rutas o paradas.")
                else:
                    visits.append(nid)
                served.add(nid)
            steps.append({"position": pos, "node_id": nid, **readings, "charge_kwh": charge,
                          "energy_kwh": None, "delivered_visit_ids": delivered})
            charges += charge
            previous_departure = departure
        total_balance += initial + charges - previous_departure
        distance = kpis.get("por_vehiculo", {}).get(vid, {}).get("km")
        if distance is not None and (isinstance(distance, bool) or not isinstance(distance, (float, int)) or distance < 0 or not math.isfinite(distance)):
            raise ProviderError("La distancia del proveedor es inválida.", "invalid_provider_result")
        routes.append({"vehicle_id": vid, "served_visit_ids": visits, "steps": steps,
                       "geometry": _geometry(encoded_route, prepared), "distance_km": distance, "energy_kwh": None})
    visit_ids = {n["node_id"] for n in nodes if n["node_type"] == "visit"}
    unserved = [n["node_id"] for n in nodes if n["node_type"] == "visit" and n["node_id"] not in served]
    try:
        reported_pending = {decode[n] for n in kpis.get("no_atendidos", [])}
    except KeyError as exc:
        raise ProviderError("El proveedor reporta entregas pendientes inexistentes.", "invalid_provider_result") from exc
    if kpis.get("entregas") != len(served) or kpis.get("clientes") != len(visit_ids) or reported_pending != set(unserved):
        violations.append("El cumplimiento del proveedor no coincide con las rutas entregadas.")
    provider_feasible = kpis.get("factible")
    if type(provider_feasible) is not bool:
        raise ProviderError("El proveedor no informa un estado de validación válido.", "invalid_provider_result")
    effective = kpis.get("energia_efectiva_kwh")
    coherent = isinstance(effective, (float, int)) and not isinstance(effective, bool) and math.isclose(effective, total_balance, abs_tol=max(.001, sum(len(r["steps"]) for r in routes) * .0002))
    if not coherent:
        warnings.append("La energía efectiva informada no coincide con el balance del detalle de recarga. La factibilidad del resultado mostrado queda sin certificar.")
    if boundary_precision_unavailable:
        warnings.append("Precisión de batería insuficiente en un límite: el proveedor redondea a 4 decimales y alguna lectura cruza capacidad o reserva dentro de 0,00005 kWh. Esa lectura se muestra como no disponible, sin recortarla; el valor original está en la exportación. La factibilidad queda sin certificar.")
    feasible = False if violations or not provider_feasible else (True if coherent and not boundary_precision_unavailable else None)
    red_type = prepared.red.get("tipo", "preparada")
    if red_type == "haversine":
        warnings.append("Red exploratoria haversine: las líneas guardadas no son rutas viales validadas.")
    if any(r["geometry"] is None and r["served_visit_ids"] for r in routes):
        warnings.append("Geometría omitida: faltan secuencias guardadas, son discontinuas o sus extremos no corresponden a los nodos. Vuelva a preparar la instancia para dibujarla; se conserva la secuencia de paradas.")
    return {
        "status": "validation_failed" if feasible is False else ("partial" if unserved else "result_available"),
        "nodes": nodes, "fleet": fleet, "routes": routes, "served_count": len(served), "total_visits": len(visit_ids),
        "unserved_visit_ids": unserved, "total_energy_kwh": None,
        "validation": {"feasible": feasible, "violations": violations,
                       "scope": "Validador evrp sobre caminos preparados y modelo energético determinista, con recarga completa; no acredita una red real ni equivalencia con modelamiento.pdf. El puente comprueba la coherencia del detalle y KPIs."
                                + (" El detalle redondeado no permite certificar alguna lectura en el límite de capacidad/reserva." if boundary_precision_unavailable else "")},
        "phases": [], "warnings": warnings,
        "assumptions": ["Capacidad útil, reserva y consumo son supuestos indicados en esta ejecución.",
                        "Flota homogénea Leaf 2013, conectores CHAdeMO/J1772; el depósito no ofrece recarga.",
                        "Preparación reutilizada sin descargar mapas; modelo contraído evrp con caminos fijados y recarga completa.",
                        "Asesor y AWS desactivados en esta beta; solver HiGHS 1.11.0, un hilo.",
                        "El tiempo solicitado limita el solver; preparación, construcción y validación pueden añadir tiempo.",
                        "No se modelan jornada, colas, tiempos de servicio ni capacidad de paquetes."],
        "network": {"type": red_type, "vial": red_type == "osm",
                    "geometry_source": "saved_prepared_sequences", "provenance_verified": False},
        "metadata": {"id_map": decode}, "raw": {"prepared": prepared.a_dict(), "effective_config": cfg, "result": raw},
    }


def run(validated):
    evrp, config, prepared_class = load_provider()
    started = time.perf_counter()
    cfg = effective_config(validated, config)
    encode = {node["node_id"]: f"zmd{index:06d}" for index, node in enumerate(validated["nodes"])}
    decode = {v: k for k, v in encode.items()}
    try:
        prepared = prepare(validated, cfg, evrp, prepared_class, encode)
        preparation_seconds = time.perf_counter() - started
        solve_started = time.perf_counter()
        original = evrp.resolver_preparada(prepared, config=cfg, salida=None,
                                           excluir=[encode[n] for n in validated["excluded"]]).a_dict()
        solve_seconds = time.perf_counter() - solve_started
    except ProviderError:
        raise
    except RuntimeError as exc:
        # No incumbent is a search outcome, never a proof of infeasibility.
        if str(exc) == "No se encontró ninguna solución (ni heurística ni MILP)":
            raise ProviderError("El proveedor no encontró una solución en esta ejecución; no demuestra infactibilidad.",
                                "no_solution_found", 422) from exc
        raise ProviderError("El proveedor no pudo completar la ejecución. Revise los datos o el entorno fijado.") from exc
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise ProviderError("El proveedor rechazó la instancia o devolvió un contrato incompatible.") from exc
    raw, unavailable = strict_provider_result(original)
    result = present(validated, prepared, cfg, raw, decode)
    result["metadata"]["unavailable_statistics"] = unavailable
    if unavailable:
        result["warnings"].append("Algunas cotas/gaps del proveedor no están disponibles; se exportan como null con motivo.")
    result["runtime_seconds"] = {"preparation": preparation_seconds, "solver": solve_seconds, "total": None}
    return result
