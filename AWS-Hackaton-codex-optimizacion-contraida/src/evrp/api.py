"""Interfaz pública y abstracta del motor.

Uso como módulo:
    from evrp import resolver
    res = resolver("data/competition_routing_nodes.csv", perfiles=["ev_routing"])
    res.rutas        # {"1": ["BASE", "V3", ..., "BASE"], ...}
    res.kpis         # entregas, energía, tiempos, validación

Para comparar motores (arena) se usa el protocolo `Motor`: recibe un escenario
neutral (dict) y devuelve un dict con el esquema común `resultado_comun`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import config as cfgmod

VERSION_ESQUEMA = "1.0"


@dataclass
class Resultado:
    rutas: dict[str, list[str]]
    rutas_indices: dict[str, list[int]]
    kpis: dict[str, Any]
    detalle: dict[str, list[dict]]
    bitacora: list[dict] = field(default_factory=list)
    explicacion: str | None = None
    esquema: str = VERSION_ESQUEMA

    def a_dict(self) -> dict:
        return asdict(self)


def _cfg(config, perfiles):
    if isinstance(config, dict) or config is None:
        return cfgmod.cargar(None, config, perfiles)
    return cfgmod.cargar(config, None, perfiles)


def preparar(nodos: str | Path, config: dict | str | Path | None = None,
             perfiles: list[str] | None = None, geometria: bool = False):
    """ETAPA 1 (preprocesamiento). Red vial + caminos de mínima energía entre nodos clave.

    Devuelve `InstanciaPreparada` (guardar con `.guardar("x.json.gz")`, cargar con
    `InstanciaPreparada.cargar(...)`). Usa de la config solo: pipeline.red, pipeline.energia,
    red.* y el modelo de energía (consumo/masa/eficiencias) del primer tipo de vehículo.
    """
    from .preparacion import preparar_con_cfg

    return preparar_con_cfg(str(nodos), _cfg(config, perfiles), geometria)


def resolver_preparada(preparada, config: dict | str | Path | None = None,
                       perfiles: list[str] | None = None, salida: str | Path | None = None,
                       excluir: list[str] | None = None) -> Resultado:
    """ETAPA 2 (solver). Resuelve una InstanciaPreparada (objeto o ruta .json/.json.gz).

    Usa de la config: flota, tipos_vehiculo (batería, reserva, SoC, consumo), cargadores,
    escala, solver, asesor. `excluir`: ids de nodos a ignorar sin volver a preparar.
    """
    from .pipeline import ejecutar
    from .preparacion import InstanciaPreparada

    prep = preparada if isinstance(preparada, InstanciaPreparada) else InstanciaPreparada.cargar(preparada)
    r = ejecutar(None, _cfg(config, perfiles), salida, preparada=prep, excluir=excluir)
    return Resultado(r["rutas"], r["rutas_indices"], r["kpis"], r["detalle"], r["bitacora"],
                     r.get("explicacion"))


def resolver(nodos: str | Path, config: dict | str | Path | None = None,
             perfiles: list[str] | None = None, salida: str | Path | None = None) -> Resultado:
    """Atajo: ETAPA 1 + ETAPA 2 en una llamada (equivale a preparar → resolver_preparada)."""
    from .pipeline import ejecutar

    r = ejecutar(str(nodos), _cfg(config, perfiles), salida)
    return Resultado(r["rutas"], r["rutas_indices"], r["kpis"], r["detalle"], r["bitacora"],
                     r.get("explicacion"))


class Motor(ABC):
    """Contrato mínimo para que la arena compare implementaciones sin conocer su interior."""

    nombre: str = "abstracto"

    @abstractmethod
    def resolver(self, escenario: dict) -> dict:
        """escenario: {nodos_csv, supuestos{...}, flota{vehiculos}, presupuesto_s, hilos, solver}.

        Devuelve el resultado común: {motor, estado, rutas{veh: [node_id]}, energia_kwh,
        entregas, tiempo_s, solver, detalles{}}. Las rutas las valida la arena por separado.
        """


class MotorEvrp(Motor):
    nombre = "evrp"

    def resolver(self, escenario: dict) -> dict:
        import time

        s = escenario.get("supuestos", {})
        tipo = {k: v for k, v in {
            "bateria_kwh": s.get("bateria_kwh"), "soc_inicial": s.get("soc_inicial"),
            "reserva_kwh": s.get("reserva_kwh"), "consumo_kwh_km": s.get("consumo_kwh_km"),
        }.items() if v is not None}
        extra: dict = {"tipos_vehiculo": {"leaf2013": tipo},
                       "solver": {"tiempo_limite_s": float(escenario.get("presupuesto_s", 60)),
                                  "presupuesto_total_s": float(escenario.get("presupuesto_s", 60)),
                                  "hilos": int(escenario.get("hilos", 0))}}
        if escenario.get("flota", {}).get("vehiculos"):
            extra["flota"] = [{"tipo": "leaf2013", "cantidad": int(escenario["flota"]["vehiculos"])}]
        if s.get("red"):
            extra.setdefault("pipeline", {})["red"] = "osm" if s["red"].startswith("osm") else "haversine"
        if s.get("pendiente") is not None:
            extra.setdefault("pipeline", {})["energia"] = "pendiente" if s["pendiente"] else "plano"
        if s.get("max_acceso_m") is not None:
            extra.setdefault("red", {})["max_acceso_m"] = s["max_acceso_m"]
        t0 = time.perf_counter()
        try:
            r = resolver(escenario["nodos_csv"], extra, escenario.get("perfiles"))
        except Exception as exc:  # la arena registra el error y sigue
            return {"motor": self.nombre, "estado": "error", "error": str(exc)[:500],
                    "tiempo_s": round(time.perf_counter() - t0, 3)}
        k = r.kpis
        return {"motor": self.nombre, "estado": "ok" if k["factible"] else "infactible",
                "rutas": r.rutas, "energia_kwh": k["energia_total_kwh"], "entregas": k["entregas"],
                "tiempo_s": k["tiempo_computo_s"], "solver": "highs",
                "detalles": {"solver": k.get("solver"), "km": k.get("km_total"), "red": k.get("red")}}
