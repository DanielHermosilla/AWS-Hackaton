"""Construccion de instancias para la arena: subconjuntos de CSV y sinteticas.

Todas las instancias se materializan como un CSV en una cache de la arena para que
ambos motores lean exactamente los mismos nodos. El mapa OSM es el empaquetado en
evrp (ann_arbor_drive.graphml.gz), descomprimido una sola vez a la cache de arena.
"""
from __future__ import annotations

import csv
import gzip
import shutil
from pathlib import Path

CABECERA = ["node_id", "node_type", "latitude", "longitude", "address", "network",
            "total_ports", "dc_fast_ports", "level2_ports", "connector_types", "max_power_kw"]

CACHE = Path("results/arena/.cache")


def grafo_osm_descomprimido(destino: Path | None = None) -> Path:
    """Descomprime el GraphML empaquetado en evrp a la cache de la arena y lo devuelve."""
    import evrp
    base = Path(evrp.__file__).parent
    gz = base / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
    if not gz.exists():
        raise FileNotFoundError(f"No se encontro el mapa empaquetado: {gz}")
    destino = destino or (CACHE / "osm" / "ann_arbor_drive.graphml")
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists() or destino.stat().st_mtime < gz.stat().st_mtime:
        with gzip.open(gz, "rb") as a, open(destino, "wb") as b:
            shutil.copyfileobj(a, b)
    return destino


def _leer_csv(ruta: str | Path) -> list[dict]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _escribir_csv(filas: list[dict], ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECERA)
        w.writeheader()
        for r in filas:
            w.writerow({k: r.get(k, "") for k in CABECERA})
    return ruta


def _tipo(fila: dict) -> str:
    return (fila.get("node_type") or "").strip().lower()


def materializar(inst: dict, destino_dir: Path) -> Path:
    """Devuelve la ruta a un CSV concreto para la instancia descrita en el escenario.

    - {csv, max_clientes/clientes_ids}: subconjunto de un CSV existente.
    - {sintetica:{clientes, semilla, referencia_csv, cargadores}}: generada con evrp.sintetico.
    """
    nombre = inst["nombre"]
    destino = destino_dir / f"{nombre}.csv"
    if inst.get("sintetica"):
        from evrp import sintetico
        s = inst["sintetica"]
        filas = sintetico.generar(
            clientes=int(s["clientes"]), semilla=int(s.get("semilla", 0)),
            referencia=s.get("referencia_csv"), cargadores=s.get("cargadores"))
        return _escribir_csv(filas, destino)

    if not inst.get("csv"):
        raise ValueError(f"La instancia {nombre!r} no define 'csv' ni 'sintetica'")
    filas = _leer_csv(inst["csv"])
    base = [r for r in filas if _tipo(r) in ("base", "depot", "deposito")]
    cargadores = [r for r in filas if _tipo(r) in ("charger", "cargador", "station")]
    clientes = [r for r in filas if _tipo(r) in ("visit", "client", "cliente", "customer")]

    if inst.get("clientes_ids"):
        ids = set(inst["clientes_ids"])
        clientes = [r for r in clientes if r["node_id"] in ids]
    elif inst.get("max_clientes") is not None:
        clientes = clientes[: int(inst["max_clientes"])]

    return _escribir_csv([*base, *clientes, *cargadores], destino)
