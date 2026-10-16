"""Local challenge inputs; never publish or manufacture the original datasets."""

import random
from pathlib import Path

from .service import MAX_PREPARE_NODES, ProviderError, SolveRequestError, number, object_fields


def data_directory_path(data_directory=None):
    return Path(data_directory) if data_directory else Path(__file__).resolve().parents[1] / "data"


def hackathon_scenario(dataset, *, data_directory=None):
    if dataset not in ("competition", "evaluation"):
        raise SolveRequestError("Elige competition o evaluation para el caso de la hackatón.")
    from ev_routing.inputs import load_routing_nodes

    directory = data_directory_path(data_directory)
    path = directory / f"{dataset}_routing_nodes.csv"
    if not path.is_file():
        raise ProviderError(
            f"Falta {path.name} en data/ del servidor. Puedes cargar tu CSV de ubicaciones.",
            "scenario_unavailable", 404,
        )
    nodes = []
    for node in load_routing_nodes(path):
        row = node.model_dump(mode="json", exclude_none=True)
        row["connector_types"] = ";".join(node.connector_types)
        nodes.append(row)
    return {
        "name": f"Hackatón · {dataset} · Ann Arbor, Michigan",
        "source_file": path.name,
        "nodes": nodes,
        "network_mode": "road",
        "scenario": {"kind": "hackathon", "dataset": dataset},
    }


def validate_scenario(value):
    """A declaration of scenario origin, never evidence of physical feasibility."""
    if value is None:
        return None
    object_fields(value, {"kind", "dataset", "seed"}, "escenario", ("kind", "dataset"))
    if value["kind"] not in ("hackathon", "hackathon_simulation"):
        raise SolveRequestError("Origen de escenario no admitido.")
    if value["dataset"] not in ("competition", "evaluation"):
        raise SolveRequestError("Dataset del escenario no admitido.")
    if "seed" in value:
        number(value["seed"], "Semilla del escenario", 0, 2_000_000_000, integer=True)
    return dict(value)


def simulate_hackathon(scenario, options, runtime):
    """Vary services on the original street network; keep the depot fixed."""
    from ev_routing.contracts import ModelParameters, Node
    from ev_routing.network import build_osm_instance
    from ev_routing.simulation import simulate_customers

    object_fields(options, {"customers", "chargers", "seed"}, "simulación", ("customers", "chargers"))
    customers = number(options["customers"], "Clientes", 1, 199, integer=True)
    chargers = number(options["chargers"], "Cargadores", 0, 198, integer=True)
    seed = number(options.get("seed", 0), "Semilla", 0, 2_000_000_000, integer=True)
    if 1 + customers + chargers > MAX_PREPARE_NODES:
        raise SolveRequestError("La simulación admite hasta 200 ubicaciones, incluido el depósito.")
    original = scenario["nodes"]
    visits = sorted((n for n in original if n["node_type"] == "visit"), key=lambda n: n["node_id"])
    stations = sorted((n for n in original if n["node_type"] == "charger"), key=lambda n: n["node_id"])
    extra_customers = max(0, customers - len(visits))
    extra_chargers = max(0, chargers - len(stations))
    extra = extra_customers + extra_chargers
    added = []
    if extra:
        if runtime.graphml is None:
            raise SolveRequestError(
                "Para añadir ubicaciones se necesita la red de Ann Arbor en el servidor "
                "(--graphml). Puedes reducir las cantidades del caso original."
            )
        source_nodes = [
            Node.model_validate({**node, "connector_types": node.get("connector_types", "").split(";")
                                 if node.get("connector_types") else []})
            for node in original
        ]
        try:
            road = build_osm_instance(
                source_nodes, ModelParameters(), .2, graphml_path=runtime.graphml,
                allow_download=False, network_profile=runtime.network_profile,
                max_snap_distance_m=runtime.max_snap_distance_m,
            )
            # Reuse the audited sampler: source customer bounds, unique coordinates
            # and the depot's strongly connected component. No synthetic road links.
            simulated = simulate_customers(road, len(visits) + extra, seed=seed)
        except FileNotFoundError as error:
            raise SolveRequestError(
                "Falta la red vial configurada. Instala el GraphML de Ann Arbor en el servidor."
            ) from error
        except ValueError as error:
            raise SolveRequestError(f"No se pudo crear la variante: {error}") from error
        added_ids = set(simulated.provenance["simulation"]["added_customer_ids"])
        added = sorted((n for n in simulated.nodes if n.node_id in added_ids), key=lambda n: n.node_id)
    rng = random.Random(seed)
    chosen_visits = rng.sample(visits, min(customers, len(visits)))
    chosen_stations = rng.sample(stations, min(chargers, len(stations)))
    for index, node in enumerate(added):
        client = index < extra_customers
        # Ports/connectors on added stations are explicit simulation assumptions.
        row = {
            "node_id": f"SIM-{'CLIENT' if client else 'CHARGER'}-{node.node_id}",
            "node_type": "visit" if client else "charger",
            "latitude": node.latitude, "longitude": node.longitude,
            "address": "Cliente simulado" if client else "Cargador simulado",
        }
        if client:
            chosen_visits.append(row)
        else:
            row.update(connector_types="J1772;CHAdeMO", total_ports=2, dc_fast_ports=1,
                       level2_ports=1, max_power_kw=50)
            chosen_stations.append(row)
    nodes = [
        *[n for n in original if n["node_type"] == "base"],
        *chosen_visits, *chosen_stations,
    ]
    return {
        **scenario, "name": f"Simulación · {customers} clientes · {chargers} cargadores · Ann Arbor",
        "nodes": nodes,
        "scenario": {**scenario["scenario"], "kind": "hackathon_simulation", "seed": seed},
        "simulation": {
            "customers": customers, "chargers": chargers, "seed": seed,
            "added_customers": extra_customers, "added_chargers": extra_chargers,
            "assumptions": [
                "Demanda e infraestructura simuladas; se conserva el depósito y la red vial.",
                "Ubicaciones nuevas en calles conectadas al depósito, dentro de la zona de clientes.",
                "Cargadores nuevos supuestos: J1772/CHAdeMO, dos puertos y máximo nominal de 50 kW; no es potencia efectiva de carga.",
            ],
        },
    }


def load_historical_case(payload, runtime, *, data_directory=None):
    object_fields(payload, {"dataset", "simulation", "energy_profile_id"}, "caso", ("dataset",))
    scenario = hackathon_scenario(payload["dataset"], data_directory=data_directory)
    if "simulation" in payload:
        scenario = simulate_hackathon(scenario, payload["simulation"], runtime)
    if "energy_profile_id" in payload:
        profile = runtime.histories.get(payload["energy_profile_id"]).public()
    else:
        profile = runtime.histories.load_example(data_directory=data_directory)
    if profile["status"] != "ready":
        raise SolveRequestError("El histórico no está preparado. Revisa las mediciones y su formato.")
    return {"scenario": scenario, "profile": profile}
