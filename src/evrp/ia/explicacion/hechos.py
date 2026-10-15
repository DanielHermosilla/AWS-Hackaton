"""Extracción de hechos verificables desde un `Resultado` del motor.

Un *hecho* es un par (campo, valor) donde `valor` es un número o un ID de nodo que
el verificador considerará "citable". El conjunto de hechos es la única fuente de
verdad: cualquier número o ID que aparezca en el texto y no esté aquí se marca como
inventado.

El resultado puede ser un `evrp.Resultado` (dataclass con `.kpis`/`.rutas`/...) o un
`dict` equivalente (p. ej. `Resultado.a_dict()`). `normalizar_resultado` unifica ambos.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Hecho:
    """Un dato citable: `campo` lo identifica, `valor` es número o ID."""

    campo: str
    valor: Any

    def a_dict(self) -> dict:
        return {"campo": self.campo, "valor": self.valor}


def normalizar_resultado(resultado: Any) -> dict:
    """Acepta un `evrp.Resultado`, su `.a_dict()` o un dict con kpis/rutas/detalle."""
    if hasattr(resultado, "a_dict"):
        return resultado.a_dict()
    if isinstance(resultado, dict):
        return resultado
    # dataclass sin a_dict: intentar atributos conocidos.
    return {
        "rutas": getattr(resultado, "rutas", {}),
        "kpis": getattr(resultado, "kpis", {}),
        "detalle": getattr(resultado, "detalle", {}),
    }


def _num(x: Any) -> float | int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return x
    return None


def extraer_hechos(resultado: Any) -> list[Hecho]:
    """Lista plana de hechos citables (números e IDs) presentes en el resultado.

    Cubre: KPIs globales (entregas, clientes, energía, km, no atendidos), por vehículo
    (energía, km, batería mínima/final, recargas) e IDs de nodos de las rutas.
    """
    r = normalizar_resultado(resultado)
    kpis = r.get("kpis", {}) or {}
    rutas = r.get("rutas", {}) or {}

    hechos: list[Hecho] = []

    def agregar(campo: str, valor: Any) -> None:
        v = _num(valor)
        if v is not None:
            hechos.append(Hecho(campo, v))

    # --- KPIs globales ---
    agregar("kpis.entregas", kpis.get("entregas"))
    agregar("kpis.clientes", kpis.get("clientes"))
    agregar("kpis.energia_total_kwh", kpis.get("energia_total_kwh"))
    agregar("kpis.energia_efectiva_kwh", kpis.get("energia_efectiva_kwh"))
    agregar("kpis.km_total", kpis.get("km_total"))
    agregar("kpis.tiempo_computo_s", kpis.get("tiempo_computo_s"))

    no_atendidos = kpis.get("no_atendidos") or []
    agregar("kpis.n_no_atendidos", len(no_atendidos))
    for c in no_atendidos:
        hechos.append(Hecho("kpis.no_atendidos[]", c))

    # Número de vehículos realmente usados (ruta con al menos un cliente/parada).
    por_veh = kpis.get("por_vehiculo", {}) or {}
    usados = [v for v, d in por_veh.items() if (d or {}).get("km", 0) > 0]
    agregar("kpis.vehiculos_usados", len(usados))
    agregar("kpis.vehiculos_total", len(por_veh))

    # --- Por vehículo ---
    for veh, d in por_veh.items():
        d = d or {}
        agregar(f"por_vehiculo.{veh}.energia_kwh", d.get("energia_kwh"))
        agregar(f"por_vehiculo.{veh}.km", d.get("km"))
        agregar(f"por_vehiculo.{veh}.bateria_min_kwh", d.get("bateria_min_kwh"))
        agregar(f"por_vehiculo.{veh}.bateria_final_kwh", d.get("bateria_final_kwh"))
        agregar(f"por_vehiculo.{veh}.recargas", d.get("recargas"))
        # El identificador del vehículo también es citable.
        try:
            hechos.append(Hecho(f"por_vehiculo.{veh}.id", int(veh)))
        except (ValueError, TypeError):
            hechos.append(Hecho(f"por_vehiculo.{veh}.id", veh))

    # --- IDs de nodos de las rutas (clientes, cargadores, base) ---
    for veh, ruta in rutas.items():
        for nodo in ruta or []:
            hechos.append(Hecho(f"rutas.{veh}.nodo", nodo))

    return hechos


def resumen_para_llm(resultado: Any) -> dict:
    """Vista compacta y segura del resultado para pasar al LLM (solo hechos citables)."""
    r = normalizar_resultado(resultado)
    kpis = r.get("kpis", {}) or {}
    rutas = r.get("rutas", {}) or {}
    por_veh = kpis.get("por_vehiculo", {}) or {}

    vehiculos = {}
    for veh, d in por_veh.items():
        d = d or {}
        if (d.get("km", 0) or 0) <= 0:
            continue  # vehículos sin usar no aportan a la explicación
        ruta = rutas.get(veh, [])
        recargas_ids = [n for n in ruta if str(n).startswith("C")]
        vehiculos[veh] = {
            "energia_kwh": d.get("energia_kwh"),
            "km": d.get("km"),
            "bateria_min_kwh": d.get("bateria_min_kwh"),
            "bateria_final_kwh": d.get("bateria_final_kwh"),
            "recargas": d.get("recargas"),
            "cargadores_usados": recargas_ids,
            "ruta": ruta,
        }

    return {
        "entregas": kpis.get("entregas"),
        "clientes": kpis.get("clientes"),
        "no_atendidos": kpis.get("no_atendidos") or [],
        "energia_total_kwh": kpis.get("energia_total_kwh"),
        "km_total": kpis.get("km_total"),
        "vehiculos": vehiculos,
    }
