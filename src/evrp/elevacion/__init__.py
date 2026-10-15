"""Fuentes de elevación por nodo vial para el modelo de energía con pendiente.

El motor de energía usa `G.nodes[v]['elevation']` (metros) para calcular el
desnivel Δh de cada arco (ver energia.py y red.py). Este subpaquete define una
interfaz común `FuenteElevacion` que, dada un grafo OSM, devuelve una altura por
nodo más metadatos de cobertura. Así se pueden comparar fuentes distintas
(eVED, Copernicus, USGS) con la misma interfaz y métricas.

Contrato::

    fuente = FuenteEved("data/eVED_EV.csv")
    alturas, meta = fuente.elevar(G)   # alturas: {nodo_osm -> altura_m}
    # meta: {'fuente', 'nodos', 'directos', 'cobertura_directa', ...}

La fuente NO modifica el grafo; solo devuelve el mapa de alturas. Quien prepara
la red decide cómo inyectarlo (ver docs/experimentos/elevacion_eved.md para la
propuesta de integración en RedOSM mediante `config.red.elevacion`).

El motor nunca depende de una fuente concreta ni de que haya datos: si una fuente
no cubre nada, devuelve alturas 0.0 y lo reporta en los metadatos (degradación
segura equivalente al perfil plano).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FuenteElevacion(ABC):
    """Interfaz común: convierte un grafo OSM en alturas por nodo + cobertura."""

    nombre: str = "abstracta"

    @abstractmethod
    def elevar(self, G) -> tuple[dict[int, float], dict[str, Any]]:
        """Devuelve ``(alturas, metadatos)``.

        - ``alturas``: ``{nodo_osm -> altura_m}`` para TODOS los nodos de ``G``.
        - ``metadatos``: diccionario con, al menos, ``fuente``, ``nodos`` (total),
          ``directos`` (nodos con dato observado), ``cobertura_directa`` (fracción)
          y, si hubo interpolación, estadísticas de distancia de interpolación.
        """

    def aplicar(self, G) -> dict[str, Any]:
        """Escribe las alturas en ``G.nodes[v]['elevation']`` y devuelve los metadatos.

        Utilidad de conveniencia para experimentos; RedOSM podría llamar a `elevar`
        directamente. No forma parte del contrato mínimo de la interfaz.
        """
        alturas, meta = self.elevar(G)
        for v, h in alturas.items():
            G.nodes[v]["elevation"] = float(h)
        return meta


__all__ = ["FuenteElevacion"]
