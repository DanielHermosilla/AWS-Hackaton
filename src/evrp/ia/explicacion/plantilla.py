"""Explicación por plantilla determinista (sin LLM).

Sirve de dos formas:
1. Línea base para comparar con la versión LLM (misma información, cero riesgo).
2. Red de seguridad: si el LLM falla el verificador dos veces, se devuelve esto.

Toda cifra proviene directamente del resultado, así que por construcción pasa el
verificador. Dos estilos: `operador` (accionable, por vehículo) y `gerencia`
(resumen de alto nivel). Solo idioma español (el contrato permite otros a futuro).
"""
from __future__ import annotations

from typing import Any

from .hechos import normalizar_resultado


def _fmt(x: Any, dec: int = 2) -> str:
    if isinstance(x, float):
        return f"{x:.{dec}f}"
    return str(x)


def _vehiculos_usados(kpis: dict) -> dict:
    por = kpis.get("por_vehiculo", {}) or {}
    return {v: d for v, d in por.items() if (d or {}).get("km", 0) > 0}


def explicar_plantilla(resultado: Any, estilo: str = "operador",
                       idioma: str = "es") -> str:
    """Genera la explicación determinista. `estilo`: 'operador' | 'gerencia'."""
    r = normalizar_resultado(resultado)
    kpis = r.get("kpis", {}) or {}
    rutas = r.get("rutas", {}) or {}

    entregas = kpis.get("entregas", 0)
    clientes = kpis.get("clientes", 0)
    energia = kpis.get("energia_total_kwh", 0.0)
    km = kpis.get("km_total", 0.0)
    no_atendidos = kpis.get("no_atendidos") or []
    usados = _vehiculos_usados(kpis)
    n_usados = len(usados)

    if estilo == "gerencia":
        return _gerencia(entregas, clientes, energia, km, no_atendidos, n_usados)
    return _operador(entregas, clientes, energia, km, no_atendidos, usados, rutas)


def _gerencia(entregas, clientes, energia, km, no_atendidos, n_usados) -> str:
    lineas = [
        f"Resumen de la jornada: se completaron {entregas} de {clientes} entregas "
        f"usando {n_usados} vehículo(s).",
        f"Consumo energético total: {_fmt(energia)} kWh en {_fmt(km, 1)} km recorridos.",
    ]
    if no_atendidos:
        lineas.append(
            f"Quedaron {len(no_atendidos)} entrega(s) pendiente(s): "
            f"{', '.join(no_atendidos)}. Conviene revisar autonomía o sumar un vehículo."
        )
    else:
        lineas.append("No quedaron entregas pendientes.")
    return " ".join(lineas)


def _operador(entregas, clientes, energia, km, no_atendidos, usados, rutas) -> str:
    partes = [
        f"Plan de ruteo: {entregas} de {clientes} clientes atendidos, "
        f"{_fmt(energia)} kWh y {_fmt(km, 1)} km en total.",
    ]
    for veh, d in usados.items():
        d = d or {}
        ruta = rutas.get(veh, [])
        cargadores = [n for n in ruta if str(n).startswith("C")]
        recargas = d.get("recargas", 0)
        bmin = d.get("bateria_min_kwh", 0.0)
        linea = (
            f"Vehículo {veh}: {_fmt(d.get('km', 0.0), 1)} km, "
            f"{_fmt(d.get('energia_kwh', 0.0))} kWh. "
        )
        if recargas and cargadores:
            linea += (
                f"Recarga {recargas} vez(ces) en {', '.join(cargadores)} "
                f"para no agotar la batería (mínimo {_fmt(bmin)} kWh en ruta). "
            )
        else:
            linea += f"Sin recargas; batería mínima en ruta {_fmt(bmin)} kWh. "
        linea += f"Termina con {_fmt(d.get('bateria_final_kwh', 0.0))} kWh."
        partes.append(linea)
    if no_atendidos:
        partes.append(
            f"Pendientes: {', '.join(no_atendidos)} "
            f"({len(no_atendidos)} sin atender por límite de batería o flota)."
        )
    else:
        partes.append("Todas las entregas quedaron cubiertas.")
    return " ".join(partes)
