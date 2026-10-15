"""Comandos de preparación y resolución reproducibles, sin UI y sin LLM.

``prepare`` combina nodos, calles y estimaciones en un JSON autosuficiente.
``run`` resuelve exactamente ese JSON; no cambia sus parámetros físicos.
La descarga de calles solo ocurre si el usuario pasa ``--download-network``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

from ev_routing.config import load_config
from ev_routing.contracts import SolverConfig
from ev_routing.energy import fit_distance_rate, integrate_eved_csv
from ev_routing.inputs import load_instance, load_routing_nodes, save_instance
from ev_routing.network import build_osm_instance
from ev_routing.pipeline import run_instance


def build_parser() -> argparse.ArgumentParser:
    """Describir las dos operaciones; no mezclar H con un límite de segundos."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="CSV + calles + energía -> instancia JSON")
    prepare.add_argument("--nodes", required=True, type=Path)
    prepare.add_argument("--graphml", required=True, type=Path, help="Caché vial OSMnx local")
    prepare.add_argument("--download-network", action="store_true")
    prepare.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    prepare.add_argument("--max-snap-distance-m", type=float, default=100.0)
    prepare.add_argument("--config", type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--name", default="routing-instance")
    prepare.add_argument("--visit-id", action="append", default=None)
    chargers = prepare.add_mutually_exclusive_group()
    chargers.add_argument("--charger-id", action="append", default=None)
    chargers.add_argument("--no-chargers", action="store_true")
    energy = prepare.add_mutually_exclusive_group(required=True)
    energy.add_argument("--eved", type=Path, help="Calibrar referencia descriptiva con EV")
    energy.add_argument("--energy-rate", type=float, help="Consumo asumido, kWh/km")
    prepare.add_argument("--energy-cache", type=Path)
    prepare.add_argument("--max-gap-seconds", type=float, default=10.0)

    run = commands.add_parser("run", help="Resolver instancia JSON y comprobar resultado")
    run.add_argument("--instance", required=True, type=Path)
    run.add_argument("--config", type=Path, help="Solo se utiliza la sección solver")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--solver", choices=["auto", "gurobi", "scip"])
    run.add_argument("--time-limit-seconds", type=float)
    run.add_argument("--threads", type=int)
    run.add_argument("--seed", type=int)
    run.add_argument("--tee", action="store_true", help="Mostrar salida nativa del solver")
    return parser


def _prepare(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    nodes = load_routing_nodes(args.nodes)
    visit_ids = {node.node_id for node in nodes if node.node_type == "visit"}
    charger_ids = {node.node_id for node in nodes if node.node_type == "charger"}
    for requested, known, kind in (
        (args.visit_id, visit_ids, "cliente"),
        (args.charger_id, charger_ids, "cargador"),
    ):
        unknown = set(requested or []) - known
        if unknown:
            raise ValueError(f"IDs de {kind} desconocidos: {sorted(unknown)}")
    # Los subconjuntos sirven para ensayos. Se registran para no confundirlos
    # con la instancia oficial completa de 20 entregas.
    selected = [
        node
        for node in nodes
        if node.node_type == "base"
        or (
            node.node_type == "visit"
            and (args.visit_id is None or node.node_id in args.visit_id)
        )
        or (
            node.node_type == "charger"
            and not args.no_chargers
            and (args.charger_id is None or node.node_id in args.charger_id)
        )
    ]
    if args.eved is not None:
        summary = integrate_eved_csv(
            args.eved,
            max_gap_seconds=args.max_gap_seconds,
            cache_path=args.energy_cache,
        )
        energy_model = fit_distance_rate(summary)
        rate = energy_model.kwh_per_km
        energy_provenance = energy_model.model_dump(mode="json")
    else:
        rate = args.energy_rate
        energy_provenance = {
            "kind": "user_supplied_distance_rate",
            "kwh_per_km": rate,
            "limitations": ["Coeficiente supuesto por el usuario, no calibrado con eVED."],
        }
    instance = build_osm_instance(
        selected,
        config.model,
        rate,
        graphml_path=args.graphml,
        allow_download=args.download_network,
        bbox=tuple(args.bbox) if args.bbox else None,
        max_snap_distance_m=args.max_snap_distance_m,
        name=args.name,
    )
    instance.provenance.update(
        routing_csv_sha256=hashlib.sha256(args.nodes.read_bytes()).hexdigest(),
        selected_visit_ids=[n.node_id for n in selected if n.node_type == "visit"],
        selected_charger_ids=[n.node_id for n in selected if n.node_type == "charger"],
        energy_model=energy_provenance,
        capacity_note="Capacidad útil y reserva configuradas; no medidas por este programa.",
    )
    save_instance(instance, args.output)
    print(
        json.dumps(
            {
                "instance_path": str(args.output),
                "nodes": len(instance.nodes),
                "arcs": len(instance.arcs),
                "deliveries": len(instance.customer_ids),
                "energy_kwh_per_km": rate,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance)
    values = load_config(args.config).solver.model_dump()
    for key in ("solver", "time_limit_seconds", "threads", "seed"):
        if getattr(args, key) is not None:
            values[key] = getattr(args, key)
    if args.tee:
        values["tee"] = True
    result = run_instance(instance, SolverConfig.model_validate(values), output_path=args.output)
    print(
        json.dumps(
            {
                "result_path": str(args.output),
                "status": result["status"],
                "solver": result["solve"]["used_solver"],
                "deliveries": result["kpis"]["served_deliveries"],
                "net_battery_energy_kwh": result["kpis"]["net_battery_energy_kwh"],
                "lexicographic_optimal": result["solve"]["lexicographic_optimal"],
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0 if result["kpis"]["feasible"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Códigos: 0 resultado válido, 1 sin ruta validada, 2 entrada/ejecución errónea."""
    args = build_parser().parse_args(argv)
    try:
        return _prepare(args) if args.command == "prepare" else _run(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(
            json.dumps({"error": str(error), "type": type(error).__name__}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
