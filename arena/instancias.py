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


def grafo_osm_recortado(csv_nodos: str | Path, destino: Path,
                        margen_m: float = 1500.0) -> dict:
    """Recorta el GraphML empaquetado a un bbox alrededor de los servicios del CSV.

    Guarda el subgrafo (mismo formato OSM, EPSG:4326) en `destino` y devuelve metadatos.
    Reduccion SIMETRICA: el mismo subgrafo se usa para el motor del companero y para
    el validador neutral; ambos ven exactamente la misma red acotada. Se conservan solo
    nodos dentro del bbox y las aristas entre ellos.
    """
    import csv as _csv
    from math import cos, radians

    import networkx as nx

    origen = grafo_osm_descomprimido()
    g = nx.read_graphml(str(origen))

    lats, lons = [], []
    with open(csv_nodos, encoding="utf-8-sig", newline="") as f:
        for r in _csv.DictReader(f):
            try:
                lats.append(float(r["latitude"]))
                lons.append(float(r["longitude"]))
            except (TypeError, ValueError, KeyError):
                continue
    lat_pad = margen_m / 111_195
    lon_pad = lat_pad / max(0.01, cos(radians(sum(lats) / len(lats))))
    sur, norte = min(lats) - lat_pad, max(lats) + lat_pad
    oeste, este = min(lons) - lon_pad, max(lons) + lon_pad

    dentro = [n for n, d in g.nodes(data=True)
              if sur <= float(d["y"]) <= norte and oeste <= float(d["x"]) <= este]
    sub = g.subgraph(dentro).copy()
    sub.graph["crs"] = g.graph.get("crs", "epsg:4326")
    destino.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(sub, str(destino))
    return {"graphml": str(destino), "nodos": sub.number_of_nodes(),
            "arcos": sub.number_of_edges(), "bbox": [oeste, sur, este, norte]}


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

    # Seleccion de cargadores: por ids explicitos, por cantidad mas cercana a los
    # clientes/base, o todos (por defecto). Permite acotar el modelo del companero.
    if inst.get("cargadores_ids"):
        cids = set(inst["cargadores_ids"])
        cargadores = [r for r in cargadores if r["node_id"] in cids]
    elif inst.get("max_cargadores") is not None:
        cargadores = _cargadores_cercanos(cargadores, [*base, *clientes],
                                          int(inst["max_cargadores"]))

    return _escribir_csv([*base, *clientes, *cargadores], destino)


def _cargadores_cercanos(cargadores: list[dict], referencia: list[dict],
                         n: int) -> list[dict]:
    """Devuelve los n cargadores mas cercanos (haversine minima a cualquier referencia)."""
    from math import asin, cos, radians, sin, sqrt

    def hav(a, b):
        lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
        v = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return 2 * 6_371_009 * asin(min(1.0, sqrt(v)))

    refs = [(float(r["latitude"]), float(r["longitude"])) for r in referencia]
    def dmin(c):
        pos = (float(c["latitude"]), float(c["longitude"]))
        return min(hav(pos, r) for r in refs) if refs else 0.0

    return sorted(cargadores, key=dmin)[: max(0, n)]
