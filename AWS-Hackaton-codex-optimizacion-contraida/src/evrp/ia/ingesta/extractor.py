"""Ingesta de pedidos desde texto e imagen hacia nodos del motor E-VRP.

Flujo:
    extraer(texto|imagen) --LLM--> pedidos (JSON estructurado, con confianza)
        -> geocodificar los que no traen lat/lon
        -> a_nodos(pedidos, csv_base) -> filas 'visit' en formato oficial

Contrato de salida de `extraer` (ver docs/experimentos/ia_ingesta.md):
    {
      "pedidos": [
        {"id_sugerido", "nombre", "direccion", "lat"|null, "lon"|null,
         "cantidad"|null, "ventana"|null, "notas", "confianza"}
      ],
      "advertencias": [str, ...],
      "uso": {"modelo", "tokens_in", "tokens_out", "latencia_s"}
    }

Degradación segura: si no hay cliente Bedrock, `extraer` sigue funcionando con el
extractor heurístico (regex) para texto; la imagen requiere el LLM multimodal.
El motor nunca depende de esto.
"""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

from ..seguridad import AVISO_NO_CONFIABLE, delimitar_no_confiable
from .geocodificador import (
    AREA_MAPA,
    Geocodificador,
    GeocodificadorNulo,
    en_area,
)

log = logging.getLogger(__name__)

# Columnas del formato oficial de nodos (coinciden con data/*_routing_nodes.csv).
CABECERA_OFICIAL = [
    "node_id", "node_type", "latitude", "longitude", "address", "network",
    "total_ports", "dc_fast_ports", "level2_ports", "connector_types", "max_power_kw",
]

CAMPOS_PEDIDO = (
    "id_sugerido", "nombre", "direccion", "lat", "lon",
    "cantidad", "ventana", "notas", "confianza",
)

# Esquema (toolSpec) que fuerza al modelo a devolver la lista de pedidos.
HERRAMIENTA_PEDIDOS = {
    "toolSpec": {
        "name": "registrar_pedidos",
        "description": (
            "Registra los pedidos de entrega detectados en el texto o la imagen. "
            "Un pedido es una entrega a un cliente con su dirección. Ignora firmas, "
            "saludos y texto que no sea un pedido."
        ),
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "pedidos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id_sugerido": {"type": "string", "description": "ID corto, p.ej. P1, P2"},
                            "nombre": {"type": "string", "description": "Nombre del cliente o destinatario"},
                            "direccion": {"type": "string", "description": "Dirección postal tal como aparece"},
                            "lat": {"type": ["number", "null"], "description": "Latitud si viene explícita"},
                            "lon": {"type": ["number", "null"], "description": "Longitud si viene explícita"},
                            "cantidad": {"type": ["number", "null"], "description": "Unidades/bultos del pedido"},
                            "ventana": {"type": ["string", "null"], "description": "Franja horaria, p.ej. 9-12"},
                            "notas": {"type": "string", "description": "Instrucciones de entrega relevantes"},
                            "confianza": {"type": "number", "description": "0..1 seguridad de la extracción"},
                        },
                        "required": ["direccion"],
                    },
                },
                "advertencias": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Dudas o datos ambiguos detectados",
                },
            },
            "required": ["pedidos"],
        }},
    }
}

_SISTEMA = (
    "Eres el asistente de logística de una jefa de flota. Extraes pedidos de entrega "
    "a partir de mensajes informales (correo, WhatsApp, listas, tablas) o imágenes. "
    "Para cada pedido captura destinatario, dirección y cualquier detalle (cantidad, "
    "franja horaria, notas). No inventes direcciones ni coordenadas: si un dato no "
    "aparece, déjalo nulo. Si el texto trae coordenadas explícitas (lat/lon), cópialas. "
    "Marca con confianza baja (<0.5) los pedidos ambiguos y anótalos en advertencias. "
    + AVISO_NO_CONFIABLE
)

# Regex para coordenadas explícitas "lat, lon" (fallback heurístico sin LLM).
_RE_COORD = re.compile(r"(-?\d{1,2}\.\d{3,}),\s*(-?\d{1,3}\.\d{3,})")


def _norm_pedido(p: dict, idx: int) -> dict:
    """Normaliza un pedido a los campos del contrato, con valores por defecto."""
    def _num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    conf = _num(p.get("confianza"))
    return {
        "id_sugerido": str(p.get("id_sugerido") or f"P{idx}").strip(),
        "nombre": str(p.get("nombre") or "").strip(),
        "direccion": str(p.get("direccion") or "").strip(),
        "lat": _num(p.get("lat")),
        "lon": _num(p.get("lon")),
        "cantidad": _num(p.get("cantidad")),
        "ventana": (str(p.get("ventana")).strip() if p.get("ventana") else None),
        "notas": str(p.get("notas") or "").strip(),
        "confianza": 0.5 if conf is None else max(0.0, min(1.0, conf)),
    }


def _extraer_heuristico(texto: str) -> dict:
    """Fallback sin LLM: una línea = un pedido; detecta coordenadas explícitas."""
    pedidos = []
    for i, linea in enumerate(l for l in (texto or "").splitlines() if l.strip()):
        m = _RE_COORD.search(linea)
        lat = lon = None
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
        pedidos.append(_norm_pedido(
            {"id_sugerido": f"P{i + 1}", "direccion": linea.strip(),
             "lat": lat, "lon": lon, "confianza": 0.3}, i + 1))
    return {"pedidos": pedidos,
            "advertencias": ["Extracción heurística sin IA: revise los campos."],
            "uso": {"modelo": "heuristico", "tokens_in": 0, "tokens_out": 0, "latencia_s": 0.0}}


MAX_IMAGEN_BYTES = 5_000_000  # Bedrock Converse limita imágenes a ~3,75 MB


def _leer_imagen(imagen) -> bytes | None:
    if imagen is None:
        return None
    if isinstance(imagen, (bytes, bytearray)):
        datos = bytes(imagen)
    else:
        ruta = Path(imagen)
        if ruta.stat().st_size > MAX_IMAGEN_BYTES:
            raise ValueError("imagen demasiado grande")
        datos = ruta.read_bytes()
    if len(datos) > MAX_IMAGEN_BYTES:
        raise ValueError("imagen demasiado grande")
    return datos


def extraer(texto: str | None = None, imagen: Any = None, contexto: str | None = None,
            *, cliente=None, modelo: str | None = None, max_tokens: int = 2048) -> dict:
    """Extrae pedidos de `texto` y/o `imagen`.

    - `cliente`: `ClienteBedrock` (opcional). Sin él y con solo texto, usa el
      extractor heurístico. Con imagen requiere el cliente (si falta, advertencia).
    - `contexto`: texto adicional para orientar al modelo (p. ej. "ciudad: Ann Arbor").

    Devuelve el dict del contrato {pedidos, advertencias, uso}.
    """
    img = _leer_imagen(imagen)
    if cliente is None:
        if img is not None:
            return {"pedidos": [], "advertencias": ["Imagen sin cliente Bedrock: no se puede leer."],
                    "uso": {"modelo": "ninguno", "tokens_in": 0, "tokens_out": 0, "latencia_s": 0.0}}
        return _extraer_heuristico(texto or "")

    partes = []
    if contexto:
        partes.append(f"Contexto (del operador): {contexto}")
    if texto:
        partes.append("Mensaje recibido:\n" + delimitar_no_confiable(texto))
    if img is not None and not texto:
        partes.append("Extrae los pedidos de la imagen adjunta.")
    prompt = "\n\n".join(partes) if partes else "Extrae los pedidos de la imagen adjunta."

    try:
        resp = cliente.preguntar(
            prompt, sistema=_SISTEMA, imagenes=[img] if img is not None else None,
            herramientas=[HERRAMIENTA_PEDIDOS], forzar_herramienta="registrar_pedidos",
            modelo=modelo, max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - degradación segura
        log.warning("Bedrock no disponible para ingesta (%s); fallback heurístico", type(exc).__name__)
        if img is not None and not texto:
            return {"pedidos": [], "advertencias": [f"IA no disponible: {type(exc).__name__}"],
                    "uso": {"modelo": modelo or "?", "tokens_in": 0, "tokens_out": 0, "latencia_s": 0.0}}
        base = _extraer_heuristico(texto or "")
        base["advertencias"].append(f"IA no disponible: {type(exc).__name__}")
        return base

    args = None
    for uso in resp.herramientas_usadas():
        if uso.get("name") == "registrar_pedidos":
            args = uso.get("input")
            break
    args = args or {}
    crudos = args.get("pedidos") or []
    pedidos = [_norm_pedido(p, i + 1) for i, p in enumerate(crudos) if isinstance(p, dict)]
    advertencias = [str(a) for a in (args.get("advertencias") or [])]
    return {
        "pedidos": pedidos,
        "advertencias": advertencias,
        "uso": {
            "modelo": modelo or getattr(cliente, "modelo", "?"),
            "tokens_in": resp.tokens_entrada,
            "tokens_out": resp.tokens_salida,
            "latencia_s": round(resp.latencia_s, 3),
        },
    }


def geocodificar_pedidos(pedidos: list[dict], geocodificador: Geocodificador | None = None,
                         *, contexto: str | None = None,
                         area: tuple[float, float, float, float] = AREA_MAPA) -> dict:
    """Rellena lat/lon de los pedidos sin coordenadas usando el geocodificador.

    No modifica pedidos que ya traen coordenadas válidas. Devuelve
    {pedidos (nueva lista), advertencias, geocodificados, total}. Rechaza (deja sin
    coordenadas y advierte) los resultados fuera del área del mapa.
    """
    geo = geocodificador or GeocodificadorNulo()
    salida: list[dict] = []
    advertencias: list[str] = []
    geocodificados = 0
    for p in pedidos:
        q = dict(p)
        if q.get("lat") is not None and q.get("lon") is not None:
            if not en_area(q["lat"], q["lon"], area):
                advertencias.append(f"{q['id_sugerido']}: coordenadas fuera del área del mapa.")
                q["lat"] = q["lon"] = None
            salida.append(q)
            continue
        if not q.get("direccion"):
            advertencias.append(f"{q['id_sugerido']}: sin dirección ni coordenadas.")
            salida.append(q)
            continue
        res = geo.geocodificar(q["direccion"], contexto=contexto)
        if res is None:
            advertencias.append(f"{q['id_sugerido']}: no se pudo geocodificar '{q['direccion']}'.")
            salida.append(q)
            continue
        if not en_area(res.lat, res.lon, area):
            advertencias.append(
                f"{q['id_sugerido']}: '{q['direccion']}' geocodificó fuera del área del mapa.")
            salida.append(q)
            continue
        q["lat"], q["lon"] = res.lat, res.lon
        q["notas"] = (q.get("notas") or "")
        geocodificados += 1
        salida.append(q)
    return {"pedidos": salida, "advertencias": advertencias,
            "geocodificados": geocodificados, "total": len(pedidos)}


def _leer_csv_base(csv_base: str | Path) -> tuple[list[str], list[dict]]:
    with open(csv_base, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        cabecera = list(lector.fieldnames or [])
        filas = [dict(r) for r in lector]
    return cabecera, filas


def a_nodos(pedidos: list[dict], csv_base: str | Path,
            *, area: tuple[float, float, float, float] = AREA_MAPA,
            prefijo: str = "V") -> dict:
    """Convierte pedidos en filas `visit` en formato oficial, listas para resolver.

    - Toma la base y los cargadores del `csv_base` (se mantienen intactos).
    - Rechaza pedidos sin coordenadas o fuera del área.
    - Rechaza duplicados por coordenada (redondeada a ~1 m) respecto del CSV base y
      entre pedidos.
    - Renombra los visits como `{prefijo}{n}` continuando tras los existentes.

    Devuelve {cabecera, filas (todas, base+cargadores+nuevos visits),
    filas_nuevas, rechazados: [{id_sugerido, motivo}], advertencias}.
    """
    cabecera, filas_base = _leer_csv_base(csv_base)
    rechazados: list[dict] = []
    advertencias: list[str] = []

    # Coordenadas ya ocupadas (base, visits y cargadores existentes), clave ~1 m.
    def _clave(lat: float, lon: float) -> tuple[int, int]:
        return (round(lat * 1e5), round(lon * 1e5))

    ocupadas: set[tuple[int, int]] = set()
    max_v = 0
    for r in filas_base:
        try:
            ocupadas.add(_clave(float(r["latitude"]), float(r["longitude"])))
        except (KeyError, TypeError, ValueError):
            pass
        nid = (r.get("node_id") or "").strip()
        m = re.fullmatch(rf"{re.escape(prefijo)}(\d+)", nid)
        if m:
            max_v = max(max_v, int(m.group(1)))

    nuevas: list[dict] = []
    n = max_v
    for p in pedidos:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            rechazados.append({"id_sugerido": p.get("id_sugerido"), "motivo": "sin coordenadas"})
            continue
        if not en_area(lat, lon, area):
            rechazados.append({"id_sugerido": p.get("id_sugerido"), "motivo": "fuera del área"})
            continue
        clave = _clave(lat, lon)
        if clave in ocupadas:
            rechazados.append({"id_sugerido": p.get("id_sugerido"), "motivo": "duplicado"})
            continue
        ocupadas.add(clave)
        n += 1
        fila = {c: "" for c in cabecera}
        fila["node_id"] = f"{prefijo}{n}"
        fila["node_type"] = "visit"
        fila["latitude"] = f"{lat:.6f}"
        fila["longitude"] = f"{lon:.6f}"
        if "address" in fila:
            fila["address"] = p.get("direccion") or ""
        nuevas.append(fila)

    if rechazados:
        advertencias.append(f"{len(rechazados)} pedido(s) rechazado(s); {len(nuevas)} aceptado(s).")
    return {
        "cabecera": cabecera,
        "filas": filas_base + nuevas,
        "filas_nuevas": nuevas,
        "rechazados": rechazados,
        "advertencias": advertencias,
    }


def escribir_csv(resultado_nodos: dict, ruta: str | Path) -> Path:
    """Escribe el CSV de nodos (base + cargadores + visits nuevos) en `ruta`."""
    ruta = Path(ruta)
    from evrp.datos import celda_csv_segura

    with open(ruta, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=resultado_nodos["cabecera"])
        escritor.writeheader()
        escritor.writerows({k: celda_csv_segura(v) for k, v in fila.items()}
                           for fila in resultado_nodos["filas"])
    return ruta
