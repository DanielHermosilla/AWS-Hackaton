"""Lectura del archivo de nodos y compatibilidad de conectores."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

# Sinónimos aceptados para node_type (el formato oficial usa base / visit / charger).
TIPOS_NODO = {
    "base": "base", "depot": "base", "deposito": "base",
    "visit": "cliente", "client": "cliente", "cliente": "cliente", "customer": "cliente",
    "charger": "cargador", "cargador": "cargador", "station": "cargador",
}

ALIAS_CONECTOR = {"TESLA": "NACS", "CCS1": "CCS", "CCS2": "CCS", "J1772COMBO": "CCS", "TYPE1": "J1772"}


def normalizar_conector(texto: str) -> str:
    t = texto.strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    return ALIAS_CONECTOR.get(t, t)


def _float(v: str | None, campo: str = "valor", *, minimo: float | None = None,
           maximo: float | None = None) -> float | None:
    """Número finito (rechaza inf, 1e999 y texto); vacío/nan = None. Rango opcional."""
    if v is None or str(v).strip() in ("", "nan", "NaN"):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{campo}: valor no numérico {str(v)[:30]!r}") from None
    if not math.isfinite(x):
        raise ValueError(f"{campo}: valor no finito")
    if (minimo is not None and x < minimo) or (maximo is not None and x > maximo):
        raise ValueError(f"{campo}={x} fuera de rango [{minimo}, {maximo}]")
    return x


# Topes de entrada: evitan valores absurdos y el costo O(n²) de los caminos entre pares.
MAX_NODOS = 2000
MAX_PUERTOS = 1000
MAX_POTENCIA_KW = 1000.0
MAX_CSV_BYTES = 10_000_000
MAX_TEXTO_CAMPO = 300


def _entero(v: str | None, campo: str) -> int | None:
    x = _float(v, campo, minimo=0, maximo=MAX_PUERTOS)
    if x is None:
        return None
    if x != int(x):
        raise ValueError(f"{campo}: se espera un entero")
    return int(x)


@dataclass(frozen=True)
class Nodo:
    id: str
    tipo: str            # base | cliente | cargador
    lat: float
    lon: float
    fila: int            # índice 0-based de la fila de datos en el CSV
    conectores: frozenset = field(default_factory=frozenset)
    puertos: int | None = None
    potencia_kw: float | None = None
    direccion: str = ""
    operador: str = ""
    puertos_dc: int | None = None     # dc_fast_ports
    puertos_ac: int | None = None     # level2_ports


def _texto(v: str | None, campo: str) -> str:
    s = (v or "").strip()
    if len(s) > MAX_TEXTO_CAMPO:
        raise ValueError(f"{campo}: texto demasiado largo ({len(s)} > {MAX_TEXTO_CAMPO})")
    return s


def cargar_nodos(ruta: str | Path) -> list[Nodo]:
    if Path(ruta).stat().st_size > MAX_CSV_BYTES:
        raise ValueError(f"Archivo de nodos demasiado grande (> {MAX_CSV_BYTES} bytes)")
    nodos: list[Nodo] = []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        faltan = {"node_id", "node_type", "latitude", "longitude"} - set(lector.fieldnames or [])
        if faltan:
            raise ValueError(f"Faltan columnas obligatorias en el archivo de nodos: {sorted(faltan)}")
        vistos: set[str] = set()
        for fila, r in enumerate(lector):
            nid = _texto(r["node_id"], "node_id")
            if not nid:
                continue
            if len(nodos) >= MAX_NODOS:
                raise ValueError(f"Demasiados nodos (máximo {MAX_NODOS})")
            if nid in vistos:
                raise ValueError(f"node_id duplicado: {nid}")
            vistos.add(nid)
            tipo = TIPOS_NODO.get((r["node_type"] or "").strip().lower())
            if tipo is None:
                raise ValueError(f"node_type desconocido en {nid}: {str(r['node_type'])[:30]!r}")
            lat = _float(r["latitude"], f"{nid}.latitude", minimo=-90, maximo=90)
            lon = _float(r["longitude"], f"{nid}.longitude", minimo=-180, maximo=180)
            if lat is None or lon is None:
                raise ValueError(f"Coordenadas inválidas en {nid}")
            conns = frozenset(
                normalizar_conector(c) for c in _texto(r.get("connector_types"), f"{nid}.connector_types").split(";")
                if c.strip()
            )
            nodos.append(Nodo(
                id=nid, tipo=tipo, lat=lat, lon=lon, fila=fila, conectores=conns,
                puertos=_entero(r.get("total_ports"), f"{nid}.total_ports"),
                potencia_kw=_float(r.get("max_power_kw"), f"{nid}.max_power_kw", minimo=0, maximo=MAX_POTENCIA_KW),
                direccion=_texto(r.get("address"), f"{nid}.address"),
                operador=_texto(r.get("network"), f"{nid}.network"),
                puertos_dc=_entero(r.get("dc_fast_ports"), f"{nid}.dc_fast_ports"),
                puertos_ac=_entero(r.get("level2_ports"), f"{nid}.level2_ports"),
            ))
    bases = [n for n in nodos if n.tipo == "base"]
    if len(bases) != 1:
        raise ValueError(f"Se espera exactamente 1 base; hay {len(bases)}")
    return nodos

def compatible(cargador: Nodo, conectores_vehiculo: set[str]) -> bool:
    """Un cargador sirve si comparte algún conector y no declara 0 puertos."""
    if cargador.tipo != "cargador":
        return False
    if cargador.puertos is not None and cargador.puertos <= 0:
        return False
    return bool(cargador.conectores & {normalizar_conector(c) for c in conectores_vehiculo})


# Modo eléctrico de cada conector (tras normalizar_conector). NACS y conectores
# desconocidos: DC si la estación declara puertos rápidos, si no AC.
CONECTORES_DC = frozenset({"CCS", "CHADEMO"})
CONECTORES_AC = frozenset({"J1772"})


def modo_conector(conector: str, cargador: Nodo) -> str:
    if conector in CONECTORES_DC:
        return "dc"
    if conector in CONECTORES_AC:
        return "ac"
    return "dc" if (cargador.puertos_dc or 0) > 0 else "ac"


def potencia_efectiva_kw(cargador: Nodo, conectores_vehiculo: set[str],
                         p_dc_kw: float | None, p_ac_kw: float | None) -> float | None:
    """Potencia de carga real = mín(vehículo, estación) en el mejor conector común.

    - 0.0: no hay conector común con puertos disponibles para su modo.
    - None: hay conector común pero el vehículo no declara su potencia para ese modo.
    `max_power_kw` es el máximo de la estación (no por conector); en AC el límite
    efectivo suele ser el cargador a bordo del vehículo (`p_ac_kw`).
    """
    if cargador.tipo != "cargador":
        return 0.0
    comunes = cargador.conectores & {normalizar_conector(c) for c in conectores_vehiculo}
    candidatas: list[float | None] = []
    for c in comunes:
        modo = modo_conector(c, cargador)
        puertos_modo = cargador.puertos_dc if modo == "dc" else cargador.puertos_ac
        if puertos_modo is not None and puertos_modo <= 0:
            continue                      # el conector existe pero no en ese tipo de puerto
        p_veh = p_dc_kw if modo == "dc" else p_ac_kw
        if p_veh is None:
            candidatas.append(None)
            continue
        est = cargador.potencia_kw
        candidatas.append(float(p_veh) if est is None else min(float(p_veh), float(est)))
    if not candidatas:
        return 0.0
    conocidas = [p for p in candidatas if p is not None]
    return max(conocidas) if conocidas else None


def celda_csv_segura(v):
    """Neutraliza inyección de fórmulas al exportar CSV (Excel/Sheets).

    Un texto que empieza por = + - @ TAB o CR se prefija con comilla simple. Los
    números (p. ej. longitudes negativas como -83.76) se dejan intactos.
    """
    if not isinstance(v, str) or not v or v[0] not in "=+-@\t\r":
        return v
    try:
        float(v)
        return v
    except ValueError:
        return "'" + v


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))
