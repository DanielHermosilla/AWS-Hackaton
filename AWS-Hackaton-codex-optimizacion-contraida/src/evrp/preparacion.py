"""Etapa 1 — preprocesamiento: red vial → caminos de mínima energía entre nodos clave.

Produce una `InstanciaPreparada` serializable (.json o .json.gz) con:
  - los nodos del CSV (base, clientes, cargadores),
  - para cada par ordenado (i, j) los tramos elementales del camino elegido [(km, Δh_m), ...],
  - opcionalmente la geometría (lat, lon) de cada camino, para dibujarlo,
  - procedencia: tipo de red, grafo, modelo de energía usado para elegir caminos, versión.

Depende de: mapa, consumo por km (solo si hay pendiente), pendiente/elevación.
NO depende de: batería, reserva, SoC, flota ni solver → se resuelven en la etapa 2
(`evrp.resolver_preparada`) sin recalcular la red.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .datos import Nodo, cargar_nodos
from .red import Red

ESQUEMA = "evrp.instancia_preparada/1"


class RedPreparada(Red):
    """Red reconstruida desde una InstanciaPreparada (no necesita OSM ni internet)."""

    def __init__(self, tramos: dict[tuple[str, str], list[tuple[float, float]]],
                 pos: dict[str, tuple[float, float]], nombre: str,
                 geometrias: dict[tuple[str, str], list[tuple[float, float]]] | None = None,
                 origen_grafo: str | None = None):
        self._tramos = tramos
        self._pos = pos
        self._geo = geometrias or {}
        self.nombre = nombre                # conserva "osm"/"haversine" del origen (KPI red.vial)
        self.origen_grafo = origen_grafo
        self.tiempos: dict[str, float] = {}

    def preparar(self, nodos, energia):     # ya está preparada
        faltan = {n.id for n in nodos} - set(self._pos)
        if faltan:
            raise ValueError(f"Nodos no presentes en la instancia preparada: {sorted(faltan)[:5]}")

    def tramos(self, i, j):
        if i == j:
            return []
        return self._tramos[(i, j)]

    def geometria(self, i, j):
        return self._geo.get((i, j)) or [self._pos[i], self._pos[j]]


@dataclass
class InstanciaPreparada:
    nodos: list[Nodo]
    tramos: dict[tuple[str, str], list[tuple[float, float]]]
    red: dict[str, Any]                      # tipo, grafo, tiempos, elevacion
    energia_caminos: dict[str, Any]          # modelo usado para ELEGIR caminos
    geometrias: dict[tuple[str, str], list[tuple[float, float]]] = field(default_factory=dict)
    origen: dict[str, Any] = field(default_factory=dict)
    esquema: str = ESQUEMA

    # ---------------------------------------------------------------- uso
    def a_red(self) -> RedPreparada:
        pos = {n.id: (n.lat, n.lon) for n in self.nodos}
        return RedPreparada(self.tramos, pos, self.red.get("tipo", "preparada"), self.geometrias,
                            self.red.get("grafo"))

    def resumen(self) -> dict:
        return {"esquema": self.esquema, "nodos": len(self.nodos),
                "clientes": sum(n.tipo == "cliente" for n in self.nodos),
                "cargadores": sum(n.tipo == "cargador" for n in self.nodos),
                "pares": len(self.tramos), "red": self.red, "energia_caminos": self.energia_caminos,
                "con_geometria": bool(self.geometrias), "origen": self.origen}

    # ------------------------------------------------------- serialización
    def a_dict(self) -> dict:
        def clave(p):
            return f"{p[0]}|{p[1]}"
        return {
            "esquema": self.esquema,
            "origen": self.origen,
            "red": self.red,
            "energia_caminos": self.energia_caminos,
            "nodos": [{**asdict(n), "conectores": sorted(n.conectores)} for n in self.nodos],
            "tramos": {clave(p): [[round(km, 6), round(dh, 3)] for km, dh in t] for p, t in self.tramos.items()},
            "geometrias": {clave(p): [[round(a, 6), round(b, 6)] for a, b in g]
                           for p, g in self.geometrias.items()},
        }

    def guardar(self, ruta: str | Path) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = json.dumps(self.a_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if ruta.suffix == ".gz":
            with gzip.open(ruta, "wb", compresslevel=6) as f:
                f.write(datos)
        else:
            ruta.write_bytes(datos)
        return ruta

    @classmethod
    def desde_dict(cls, d: dict) -> "InstanciaPreparada":
        if not isinstance(d, dict) or d.get("esquema") != ESQUEMA:
            raise ValueError(f"Esquema no soportado (se espera {ESQUEMA})")
        from .datos import MAX_NODOS

        if not isinstance(d.get("nodos"), list) or len(d["nodos"]) > MAX_NODOS:
            raise ValueError(f"Instancia inválida: nodos ausentes o más de {MAX_NODOS}")
        n = len(d["nodos"])
        for clave in ("tramos", "geometrias"):
            if len(d.get(clave) or {}) > n * (n - 1):
                raise ValueError(f"Instancia inválida: '{clave}' tiene más pares que nodos²")

        def par(k):
            i, j = k.split("|", 1)
            return (i, j)
        campos = set(Nodo.__dataclass_fields__)
        nodos = []
        for x in d["nodos"]:
            if not isinstance(x, dict) or not set(x) <= campos:
                raise ValueError("Instancia inválida: nodo con campos desconocidos")
            nodos.append(Nodo(**{**x, "conectores": frozenset(x.get("conectores") or [])}))
        tramos = {par(k): [(float(a), float(b)) for a, b in v] for k, v in d["tramos"].items()}
        geos = {par(k): [(float(a), float(b)) for a, b in v] for k, v in d.get("geometrias", {}).items()}
        if any(not math.isfinite(x) for t in tramos.values() for p in t for x in p):
            raise ValueError("Instancia inválida: tramos con valores no finitos")
        return cls(nodos, tramos, d["red"], d["energia_caminos"], geos, d.get("origen", {}), d["esquema"])

    @classmethod
    def cargar(cls, ruta: str | Path) -> "InstanciaPreparada":
        ruta = Path(ruta)
        if ruta.suffix == ".gz":
            datos = leer_gzip_acotado(ruta, MAX_INSTANCIA_BYTES)
        else:
            if ruta.stat().st_size > MAX_INSTANCIA_BYTES:
                raise ValueError("Instancia preparada demasiado grande")
            datos = ruta.read_bytes()
        return cls.desde_dict(json.loads(datos.decode("utf-8")))


# Una instancia oficial con geometría pesa ~0,9 MB comprimida (~10 MB sin comprimir).
MAX_INSTANCIA_BYTES = 200_000_000


def leer_gzip_acotado(ruta: str | Path, maximo: int, *, destino=None) -> bytes | None:
    """Descomprime por bloques y aborta si el contenido supera `maximo` bytes
    (bomba gzip). Con `destino` (archivo binario abierto) escribe ahí y devuelve None."""
    leidos, partes = 0, []
    with gzip.open(ruta, "rb") as f:
        while True:
            bloque = f.read(1 << 20)
            if not bloque:
                break
            leidos += len(bloque)
            if leidos > maximo:
                raise ValueError(f"{Path(ruta).name}: contenido descomprimido supera {maximo} bytes")
            if destino is not None:
                destino.write(bloque)
            else:
                partes.append(bloque)
    return None if destino is not None else b"".join(partes)


def _hash_archivo(ruta: str | Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()[:16]


def preparar_con_cfg(ruta_nodos: str | Path, cfg: dict, geometria: bool = False) -> InstanciaPreparada:
    """Etapa 1 con una configuración ya cargada (ver evrp.config.cargar)."""
    from .instancia import tipos_desde_config
    from .red import RedHaversine, crear_red

    t0 = time.perf_counter()
    nodos = cargar_nodos(ruta_nodos)
    energia = tipos_desde_config(cfg)[0].energia
    red = crear_red(cfg)
    respaldo = None
    try:
        red.preparar(nodos, energia)
    except Exception as exc:
        if cfg["pipeline"]["red"] == "osm" and cfg["red"].get("respaldo_linea_recta"):
            respaldo = str(exc)[:200]
            red = RedHaversine(cfg["red"]["factor_vial"])
            red.preparar(nodos, energia)
        else:
            raise
    ids = [n.id for n in nodos]
    tramos = {(i, j): list(red.tramos(i, j)) for i in ids for j in ids if i != j}
    geos = {(i, j): list(red.geometria(i, j)) for i in ids for j in ids if i != j} if geometria else {}
    info_red = {"tipo": red.nombre, "vial": red.nombre == "osm", "grafo": getattr(red, "origen_grafo", None),
                "elevacion": cfg["red"].get("elevacion", "ninguna") if energia.usar_pendiente else "ninguna",
                "meta_elevacion": getattr(red, "meta_elevacion", None),
                "tiempos": getattr(red, "tiempos", None), "respaldo_linea_recta": respaldo,
                "factor_vial": cfg["red"]["factor_vial"] if red.nombre == "haversine" else None}
    e = {"usar_pendiente": energia.usar_pendiente, "consumo_kwh_km": energia.consumo_kwh_km,
         "masa_kg": energia.masa_kg, "eta_traccion": energia.eta_traccion,
         "eta_regeneracion": energia.eta_regeneracion}
    from . import __version__

    origen = {"archivo": str(ruta_nodos), "sha256_16": _hash_archivo(ruta_nodos), "evrp": __version__,
              "tiempo_s": round(time.perf_counter() - t0, 3)}
    return InstanciaPreparada(nodos, tramos, info_red, e, geos, origen)
