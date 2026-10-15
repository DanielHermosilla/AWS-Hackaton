"""Generador de instancias sintéticas reproducibles con el formato oficial de nodos.

Los clientes se muestrean entre los nodos del mapa vial empaquetado dentro de una zona
(por defecto la del dataset eVED en Ann Arbor), así siempre caen sobre calles reales.
Los cargadores y la base se copian de un CSV de referencia (los cargadores reales) o se
muestrean igual que los clientes.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

ZONA_EVED = (42.22, -83.80, 42.33, -83.67)  # lat_min, lon_min, lat_max, lon_max
CABECERA = ["node_id", "node_type", "latitude", "longitude", "address", "network", "total_ports",
            "dc_fast_ports", "level2_ports", "connector_types", "max_power_kw"]


def _nodos_viales(zona) -> list[tuple[float, float]]:
    import gzip
    import xml.etree.ElementTree as ET

    ruta = Path(__file__).parent / "assets" / "osm" / "ann_arbor_drive.graphml.gz"
    with gzip.open(ruta, "rb") as f:
        arbol = ET.parse(f)
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    claves = {k.get("attr.name"): k.get("id") for k in arbol.getroot().findall("g:key", ns)
              if k.get("for") == "node"}
    out = []
    for n in arbol.getroot().iter("{http://graphml.graphdrawing.org/xmlns}node"):
        datos = {d.get("key"): d.text for d in n}
        y, x = float(datos[claves["y"]]), float(datos[claves["x"]])
        if zona[0] <= y <= zona[2] and zona[1] <= x <= zona[3]:
            out.append((y, x))
    return out


def generar(clientes: int, semilla: int = 0, referencia: str | Path | None = None,
            cargadores: int | None = None, zona=ZONA_EVED, base_aleatoria: bool = False) -> list[dict]:
    """Devuelve filas (dicts) con el formato oficial. `cargadores=None` usa todos los de la referencia."""
    rng = random.Random(semilla)
    puntos = _nodos_viales(zona)
    if len(puntos) < clientes + 1:
        raise ValueError("La zona no tiene suficientes nodos viales")
    ref = []
    if referencia:
        with open(referencia, encoding="utf-8-sig", newline="") as f:
            ref = list(csv.DictReader(f))
    filas: list[dict] = []
    base_ref = [r for r in ref if r["node_type"] == "base"]
    if base_ref and not base_aleatoria:
        filas.append({k: base_ref[0].get(k, "") for k in CABECERA})
    else:
        y, x = rng.choice(puntos)
        filas.append({**dict.fromkeys(CABECERA, ""), "node_id": "BASE", "node_type": "base",
                      "latitude": f"{y:.7f}", "longitude": f"{x:.7f}"})
    for i, (y, x) in enumerate(rng.sample(puntos, clientes), start=1):
        filas.append({**dict.fromkeys(CABECERA, ""), "node_id": f"V{i}", "node_type": "visit",
                      "latitude": f"{y:.7f}", "longitude": f"{x:.7f}"})
    carg_ref = [r for r in ref if r["node_type"] == "charger"]
    if carg_ref and cargadores is None:
        filas += [{k: r.get(k, "") for k in CABECERA} for r in carg_ref]
    else:
        n = cargadores if cargadores is not None else 20
        for i, (y, x) in enumerate(rng.sample(puntos, n), start=1):
            dc = rng.random() < 0.2
            filas.append({**dict.fromkeys(CABECERA, ""), "node_id": f"C{i}", "node_type": "charger",
                          "latitude": f"{y:.7f}", "longitude": f"{x:.7f}", "total_ports": "2",
                          "dc_fast_ports": "2" if dc else "0", "level2_ports": "0" if dc else "2",
                          "connector_types": rng.choice(["CHAdeMO", "CCS", "CCS; NACS"]) if dc else "J1772",
                          "max_power_kw": "50" if dc else "6.6"})
    return filas


def escribir(filas: list[dict], ruta: str | Path) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECERA)
        w.writeheader()
        w.writerows(filas)
    return ruta
