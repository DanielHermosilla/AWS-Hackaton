"""Extraccion de HECHOS numericos del resultado del solver (eje C).

Lee el ``dict`` que devuelve ``pipeline.run_instance`` (clave ``solve`` ->
``SolveResult`` serializado) y produce una estructura compacta de hechos que
luego (a) alimenta el prompt de explicacion y (b) sirve de referencia al
verificador anti-alucinacion. No llama a ningun LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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

    def a_dict(self) -> dict:
        return {
            "estado": self.estado,
            "optimo_lexicografico": self.optimo_lexicografico,
            "factible": self.factible,
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
        }


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
        optimo_lexicografico=bool(solve.get("lexicographic_optimal", False)),
        factible=validation.get("feasible"),
        entregados=solucion.get("served_visit_ids", []) or [],
        sin_atender=solucion.get("unserved_visit_ids", []) or [],
        energia_neta_kwh=solucion.get("net_energy_kwh"),
        rutas=rutas,
        gaps=gaps,
    )
