"""Geocodificación detrás de una interfaz común (`Geocodificador`).

Tres implementaciones, de más a menos dependiente de servicios externos:

1. `AmazonLocation` — Amazon Location Service (SearchPlaceIndexForText). Requiere
   un *place index* ya existente (su creación tiene costo por uso; este módulo no
   crea recursos). Degrada a `None` si no hay índice o permiso.
2. `Nominatim` — OpenStreetMap. Respeta la política de uso: 1 req/s como máximo,
   `User-Agent` propio y uso no masivo. Pensado para pocos pedidos manuales.
3. `GeocodificadorNulo` — no llama a ninguna red; solo "geocodifica" cuando el
   texto ya trae coordenadas explícitas (lo resuelve la capa de extracción).

Todas devuelven `ResultadoGeocodificacion | None` y nunca lanzan por fallos de
red: registran y degradan. El motor E-VRP no depende de nada de esto.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Área del mapa vial empaquetado (Ann Arbor). Coherente con `sintetico.ZONA_EVED`,
# con un pequeño margen para no rechazar direcciones del borde.
AREA_MAPA = (42.20, -83.82, 42.35, -83.65)  # lat_min, lon_min, lat_max, lon_max


def en_area(lat: float, lon: float, area: tuple[float, float, float, float] = AREA_MAPA) -> bool:
    """True si (lat, lon) cae dentro del rectángulo del mapa empaquetado."""
    return area[0] <= lat <= area[2] and area[1] <= lon <= area[3]


@dataclass
class ResultadoGeocodificacion:
    lat: float
    lon: float
    etiqueta: str = ""          # dirección normalizada que devolvió el proveedor
    confianza: float = 0.0      # 0..1 (relevancia del proveedor si la expone)
    fuente: str = ""            # nombre del geocodificador


class Geocodificador(ABC):
    """Convierte una dirección libre en coordenadas, o None si no la resuelve."""

    nombre = "abstracto"

    @abstractmethod
    def geocodificar(self, direccion: str, *, contexto: str | None = None) -> ResultadoGeocodificacion | None:
        ...


class GeocodificadorNulo(Geocodificador):
    """No usa red: siempre devuelve None (solo se aceptan coordenadas explícitas)."""

    nombre = "nulo"

    def geocodificar(self, direccion, *, contexto=None):
        return None


class AmazonLocation(Geocodificador):
    """Amazon Location Service. Necesita un place index existente (`indice`).

    No crea recursos (la creación es facturable). Si el índice no existe o falta
    permiso, degrada a None y lo registra. El cliente boto3 se puede inyectar
    para pruebas.
    """

    nombre = "amazon_location"

    def __init__(self, indice: str, region: str = "us-east-1", perfil: str | None = None,
                 cliente=None, *, sesgo_area: tuple[float, float, float, float] | None = AREA_MAPA):
        self.indice = indice
        self.sesgo_area = sesgo_area
        if cliente is not None:
            self.cliente = cliente
            return
        import boto3
        sesion = boto3.Session(profile_name=perfil) if perfil else boto3.Session()
        self.cliente = sesion.client("location", region_name=region)

    def geocodificar(self, direccion, *, contexto=None):
        texto = direccion if not contexto else f"{direccion}, {contexto}"
        kwargs = {"IndexName": self.indice, "Text": texto, "MaxResults": 1}
        if self.sesgo_area:
            # FilterBBox: [lon_min, lat_min, lon_max, lat_max]
            a = self.sesgo_area
            kwargs["FilterBBox"] = [a[1], a[0], a[3], a[2]]
        try:
            r = self.cliente.search_place_index_for_text(**kwargs)
        except Exception as exc:  # noqa: BLE001 - degradación segura
            log.warning("AmazonLocation no disponible: %s", type(exc).__name__)
            return None
        resultados = r.get("Results") or []
        if not resultados:
            return None
        lugar = resultados[0].get("Place", {})
        punto = lugar.get("Geometry", {}).get("Point")  # [lon, lat]
        if not punto or len(punto) != 2:
            return None
        lon, lat = float(punto[0]), float(punto[1])
        rel = resultados[0].get("Relevance")
        return ResultadoGeocodificacion(
            lat=lat, lon=lon, etiqueta=str(lugar.get("Label", "")),
            confianza=float(rel) if rel is not None else 0.0, fuente=self.nombre,
        )


class Nominatim(Geocodificador):
    """OpenStreetMap Nominatim. Respeta 1 req/s, User-Agent propio y uso moderado.

    `transporte` permite inyectar una función de red para pruebas:
    `(url, params, headers) -> list[dict]` (ya parseado como JSON).
    """

    nombre = "nominatim"
    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, user_agent: str = "evrp-lab/0.2 (ingesta de pedidos; contacto: flota@evrp.local)",
                 *, intervalo_s: float = 1.0, sesgo_area: tuple[float, float, float, float] | None = AREA_MAPA,
                 transporte=None):
        self.user_agent = user_agent
        self.intervalo_s = intervalo_s
        self.sesgo_area = sesgo_area
        self._transporte = transporte
        self._ultimo = 0.0

    def _respetar_ritmo(self):
        delta = time.monotonic() - self._ultimo
        if delta < self.intervalo_s:
            time.sleep(self.intervalo_s - delta)
        self._ultimo = time.monotonic()

    def _buscar(self, params: dict) -> list:
        headers = {"User-Agent": self.user_agent, "Accept-Language": "en"}
        if self._transporte is not None:
            return self._transporte(self.URL, params, headers)
        import json
        import urllib.parse
        import urllib.request

        url = f"{self.URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (URL fija)
            return json.loads(resp.read().decode("utf-8"))

    def geocodificar(self, direccion, *, contexto=None):
        texto = direccion if not contexto else f"{direccion}, {contexto}"
        params = {"q": texto, "format": "jsonv2", "limit": 1, "addressdetails": 0}
        if self.sesgo_area:
            a = self.sesgo_area
            params["viewbox"] = f"{a[1]},{a[2]},{a[3]},{a[0]}"  # x1,y1,x2,y2
            params["bounded"] = 1
        try:
            self._respetar_ritmo()
            datos = self._buscar(params)
        except Exception as exc:  # noqa: BLE001 - degradación segura
            log.warning("Nominatim no disponible: %s", type(exc).__name__)
            return None
        if not datos:
            return None
        d = datos[0]
        try:
            lat, lon = float(d["lat"]), float(d["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        imp = d.get("importance")
        return ResultadoGeocodificacion(
            lat=lat, lon=lon, etiqueta=str(d.get("display_name", "")),
            confianza=float(imp) if imp is not None else 0.0, fuente=self.nombre,
        )
