"""Extraccion de HECHOS numericos del resultado del solver (eje C).

Lee el ``dict`` que devuelve ``pipeline.run_instance`` (clave ``solve`` ->
``SolveResult`` serializado) y produce una estructura compacta de hechos que
luego (a) alimenta el prompt de explicacion y (b) sirve de referencia al
verificador anti-alucinacion. No llama a ningun LLM.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _num(valor) -> float | None:
    """Numero finito o None (nunca bool, NaN ni infinito)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor) if math.isfinite(valor) else None


@dataclass
class HechosFase:
    """Certificado de UNA fase lexicografica; los gaps no se combinan entre fases."""

    nombre: str
    sentido: str | None = None
    estado: str | None = None
    terminacion: str | None = None
    optima_probada: bool | None = None
    incumbente: float | None = None
    cota: float | None = None
    gap_absoluto: float | None = None
    gap_relativo: float | None = None
    tiempo_s: float | None = None

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "sentido": self.sentido,
            "estado": self.estado,
            "terminacion": self.terminacion,
            "optima_probada": self.optima_probada,
            "incumbente": self.incumbente,
            "cota": self.cota,
            "gap_absoluto": self.gap_absoluto,
            "gap_relativo": self.gap_relativo,
            "tiempo_s": self.tiempo_s,
        }


@dataclass
class HechosRuta:
    vehiculo: str
    entregas: list[str] = field(default_factory=list)
    paradas_carga: list[str] = field(default_factory=list)
    energia_neta_kwh: float | None = None
    duracion_s: float | None = None


@dataclass
class Hechos:
    """Hechos verificables de una solucion; todos provienen del solver."""

    estado: str
    optimo_lexicografico: bool
    factible: bool | None
    entregados: list[str] = field(default_factory=list)
    sin_atender: list[str] = field(default_factory=list)
    energia_neta_kwh: float | None = None
    rutas: list[HechosRuta] = field(default_factory=list)
    gaps: dict[str, float | None] = field(default_factory=dict)
    # Datos adicionales (todos opcionales: ausentes -> None/vacio, nunca inventados).
    fases: list[HechosFase] = field(default_factory=list)
    tiempos: dict[str, float | None] = field(default_factory=dict)
    solver: dict[str, object] = field(default_factory=dict)
    kpis: dict[str, float | None] = field(default_factory=dict)
    hay_solucion: bool = False

    def a_dict(self) -> dict:
        return {
            "estado": self.estado,
            "optimo_lexicografico": self.optimo_lexicografico,
            "factible": self.factible,
            "hay_solucion": self.hay_solucion,
            "entregados": self.entregados,
            "sin_atender": self.sin_atender,
            "energia_neta_kwh": self.energia_neta_kwh,
            "rutas": [
                {
                    "vehiculo": r.vehiculo,
                    "entregas": r.entregas,
                    "paradas_carga": r.paradas_carga,
                    "energia_neta_kwh": r.energia_neta_kwh,
                    "duracion_s": r.duracion_s,
                }
                for r in self.rutas
            ],
            "gaps": self.gaps,
            "fases": [f.a_dict() for f in self.fases],
            "tiempos": self.tiempos,
            "solver": self.solver,
            "kpis": self.kpis,
        }


def _extraer_fases(solve: dict) -> list[HechosFase]:
    fases: list[HechosFase] = []
    for fase in solve.get("phases", []) or []:
        proven = fase.get("proven_optimal")
        fases.append(
            HechosFase(
                nombre=fase.get("name", "?"),
                sentido=fase.get("sense"),
                estado=fase.get("status"),
                terminacion=fase.get("termination_condition"),
                optima_probada=proven if isinstance(proven, bool) else None,
                incumbente=_num(fase.get("incumbent")),
                cota=_num(fase.get("best_bound")),
                gap_absoluto=_num(fase.get("absolute_gap")),
                gap_relativo=_num(fase.get("relative_gap")),
                tiempo_s=_num(fase.get("runtime_seconds")),
            )
        )
    return fases


def _extraer_tiempos(resultado: dict, solve: dict) -> dict[str, float | None]:
    """Tiempos de computo del pipeline; la preparacion de la instancia no se incluye."""
    runtime = resultado.get("runtime_seconds")
    runtime = runtime if isinstance(runtime, dict) else {}
    tiempos = {
        "resolucion_s": _num(runtime.get("resolution_including_model")),
        "validacion_s": _num(runtime.get("validation")),
        "total_s": _num(runtime.get("total")),
        "llm_s": _num(runtime.get("llm")),
    }
    if tiempos["resolucion_s"] is None:
        tiempos["resolucion_s"] = _num(solve.get("runtime_seconds"))
    return {k: v for k, v in tiempos.items() if v is not None}


def _extraer_solver(resultado: dict, solve: dict) -> dict[str, object]:
    config = resultado.get("solver_config")
    config = config if isinstance(config, dict) else {}
    datos = {
        "usado": solve.get("used_solver"),
        "solicitado": solve.get("requested_solver"),
        "respaldo": solve.get("fallback_reason"),
        "origen_solucion": solve.get("solution_source"),
        "limite_tiempo_s": _num(config.get("time_limit_seconds")),
        "gap_energia_objetivo": _num(config.get("energy_relative_gap")),
    }
    return {k: v for k, v in datos.items() if v is not None}


_KPIS = {
    "distancia_km": "distance_km",
    "energia_cargada_kwh": "charged_to_battery_kwh",
    "paradas_carga": "charging_stops",
    "bateria_minima_kwh": "minimum_battery_kwh",
    "duracion_operacional_s": "operational_duration_seconds",
    "energia_red_kwh": "grid_energy_kwh",
}


def _extraer_kpis(resultado: dict) -> dict[str, float | None]:
    kpis = resultado.get("kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    datos = {clave: _num(kpis.get(origen)) for clave, origen in _KPIS.items()}
    return {k: v for k, v in datos.items() if v is not None}


def extraer_hechos(resultado: dict) -> Hechos:
    """Mapea el dict de ``run_instance`` a ``Hechos``.

    Tolera ausencias (solucion vacia, infactible) sin romper: lo que no exista
    queda en None/listas vacias, nunca inventado.
    """
    solve = resultado.get("solve") or {}
    solucion = solve.get("solution") or {}
    validation = resultado.get("validation") or {}

    rutas: list[HechosRuta] = []
    for ruta in solucion.get("routes", []) or []:
        entregas: list[str] = []
        paradas: list[str] = []
        for paso in ruta.get("steps", []) or []:
            entregas.extend(paso.get("delivered_visit_ids", []) or [])
            if (paso.get("charged_to_battery_kwh") or 0) > 0:
                paradas.append(paso.get("node_id", "?"))
        rutas.append(
            HechosRuta(
                vehiculo=ruta.get("vehicle_id", "?"),
                entregas=entregas,
                paradas_carga=paradas,
                energia_neta_kwh=ruta.get("net_energy_kwh"),
                duracion_s=ruta.get("duration_seconds"),
            )
        )

    gaps: dict[str, float | None] = {}
    for fase in solve.get("phases", []) or []:
        gaps[fase.get("name", "?")] = fase.get("relative_gap")

    return Hechos(
        estado=solve.get("status", resultado.get("status", "desconocido")),
        optimo_lexicografico=(
            bool(solucion) and validation.get("feasible") is True
            and solve.get("lexicographic_optimal") is True
        ),
        factible=validation.get("feasible"),
        hay_solucion=bool(solucion),
        entregados=solucion.get("served_visit_ids", []) or [],
        sin_atender=solucion.get("unserved_visit_ids", []) or [],
        energia_neta_kwh=solucion.get("net_energy_kwh"),
        rutas=rutas,
        gaps=gaps,
        fases=_extraer_fases(solve),
        tiempos=_extraer_tiempos(resultado, solve),
        solver=_extraer_solver(resultado, solve),
        kpis=_extraer_kpis(resultado),
    )
