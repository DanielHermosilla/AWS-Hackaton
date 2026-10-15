"""Ingesta de pedidos desde texto e imagen hacia nodos del motor E-VRP.

API pública:
    extraer(texto=None, imagen=None, contexto=None, *, cliente=None, modelo=None)
        -> {pedidos:[...], advertencias:[...], uso:{...}}
    geocodificar_pedidos(pedidos, geocodificador=None, *, contexto=None) -> {...}
    a_nodos(pedidos, csv_base) -> {cabecera, filas, filas_nuevas, rechazados, ...}
    escribir_csv(resultado_nodos, ruta) -> Path

Geocodificadores (interfaz `Geocodificador`):
    AmazonLocation, Nominatim, GeocodificadorNulo

Todo es opcional: el motor E-VRP no depende de este subpaquete. Sin cliente
Bedrock, `extraer` degrada a un extractor heurístico (solo texto).
"""
from __future__ import annotations

from .extractor import (
    CABECERA_OFICIAL,
    CAMPOS_PEDIDO,
    HERRAMIENTA_PEDIDOS,
    a_nodos,
    escribir_csv,
    extraer,
    geocodificar_pedidos,
)
from .geocodificador import (
    AREA_MAPA,
    AmazonLocation,
    Geocodificador,
    GeocodificadorNulo,
    Nominatim,
    ResultadoGeocodificacion,
    en_area,
)

__all__ = [
    "extraer",
    "geocodificar_pedidos",
    "a_nodos",
    "escribir_csv",
    "CABECERA_OFICIAL",
    "CAMPOS_PEDIDO",
    "HERRAMIENTA_PEDIDOS",
    "Geocodificador",
    "GeocodificadorNulo",
    "AmazonLocation",
    "Nominatim",
    "ResultadoGeocodificacion",
    "AREA_MAPA",
    "en_area",
]
