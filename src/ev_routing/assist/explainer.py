"""Explicacion en lenguaje natural de la solucion, verificada (eje C).

Flujo: hechos -> Bedrock redacta en espaniol -> verificador contrasta contra los
hechos. Si Bedrock no esta disponible o la explicacion no es confiable, se
degrada a una plantilla deterministica construida solo con los hechos (nunca
inventa).
"""

from __future__ import annotations

from dataclasses import dataclass

from .bedrock_chat import ClienteBedrock, ErrorBedrock
from .facts import Hechos, extraer_hechos
from .verifier import ReporteVerificacion, verificar

SISTEMA = (
    "Eres el asistente de una jefa de flota de vehiculos electricos. Explica en "
    "espaniol, breve y claro, que hace cada vehiculo, donde recarga y por que, y "
    "que entregas quedan pendientes. Usa SOLO los datos que te doy; no inventes "
    "numeros, IDs ni rutas. Si un dato no esta, no lo menciones. Si hay tiempos, gaps "
    "o indicadores, menciona los relevantes tal cual; cada fase tiene su propio gap y no "
    "llames optima a una fase cuyo 'optima_probada' no sea verdadero."
)


@dataclass
class Explicacion:
    texto: str
    fuente: str  # "bedrock" | "plantilla"
    verificacion: ReporteVerificacion


def _plantilla(hechos: Hechos) -> str:
    """Explicacion deterministica a partir de los hechos (sin LLM)."""
    lineas = []
    estado = "optima (lexicografica)" if hechos.optimo_lexicografico else hechos.estado
    lineas.append(f"Estado de la solucion: {estado}.")
    lineas.append(
        f"Se atendieron {len(hechos.entregados)} entregas"
        + (
            f"; quedaron {len(hechos.sin_atender)} sin atender."
            if hechos.sin_atender
            else "; no quedaron entregas pendientes."
        )
    )
    for r in hechos.rutas:
        carga = (
            f" Recarga en: {', '.join(r.paradas_carga)}."
            if r.paradas_carga
            else " Sin recargas."
        )
        lineas.append(
            f"Vehiculo {r.vehiculo}: {len(r.entregas)} entregas.{carga}"
        )
    lineas.extend(_lineas_certificado(hechos))
    return "\n".join(lineas)


_NOMBRE_FASE = {"deliveries": "entregas", "energy": "energia"}


def _lineas_certificado(hechos: Hechos) -> list[str]:
    """Tiempo, certificado por fase y KPIs, solo con los datos que existan.

    Cada fase se reporta por separado (no se combinan gaps de objetivos distintos)
    y un gap pequeno no se presenta como optimalidad exacta.
    """
    lineas: list[str] = []
    t = hechos.tiempos
    if t.get("resolucion_s") is not None:
        texto = f"Tiempo de resolucion: {t['resolucion_s']:.1f} s"
        if t.get("total_s") is not None:
            texto += f" (pipeline completo: {t['total_s']:.1f} s)"
        lineas.append(texto + ".")
    for fase in hechos.fases:
        partes = [f"estado {fase.estado}"] if fase.estado else []
        if fase.gap_relativo is not None:
            partes.append(f"gap relativo reportado {fase.gap_relativo * 100:.2f} %")
        if fase.optima_probada is not None:
            partes.append("optimalidad " + ("probada" if fase.optima_probada else "no probada"))
        if fase.tiempo_s is not None:
            partes.append(f"{fase.tiempo_s:.1f} s")
        if partes:
            nombre = _NOMBRE_FASE.get(fase.nombre, fase.nombre)
            lineas.append(f"Fase de {nombre}: " + ", ".join(partes) + ".")
    k = hechos.kpis
    kpis = []
    if k.get("distancia_km") is not None:
        kpis.append(f"distancia total {k['distancia_km']:.1f} km")
    if k.get("energia_cargada_kwh") is not None:
        kpis.append(f"energia recargada {k['energia_cargada_kwh']:.1f} kWh")
    if k.get("bateria_minima_kwh") is not None:
        kpis.append(f"bateria minima {k['bateria_minima_kwh']:.1f} kWh")
    if k.get("duracion_operacional_s") is not None:
        kpis.append(f"duracion operacional {k['duracion_operacional_s'] / 60:.0f} min")
    if kpis:
        lineas.append("Indicadores: " + ", ".join(kpis) + ".")
    return lineas


def explicar(resultado: dict, cliente: ClienteBedrock | None = None) -> Explicacion:
    """Genera la explicacion verificada del resultado del solver."""
    hechos = extraer_hechos(resultado)
    plantilla = _plantilla(hechos)

    if cliente is None:
        rep = verificar(plantilla, hechos)
        return Explicacion(plantilla, "plantilla", rep)

    mensaje = {
        "role": "user",
        "content": [{"text": "Explica esta solucion:\n" + str(hechos.a_dict())}],
    }
    try:
        resp = cliente.conversar([mensaje], sistema=SISTEMA)
        bloques = resp.get("output", {}).get("message", {}).get("content", [])
        texto = " ".join(b.get("text", "") for b in bloques).strip()
    except ErrorBedrock:
        rep = verificar(plantilla, hechos)
        return Explicacion(plantilla, "plantilla", rep)

    rep = verificar(texto, hechos)
    if not rep.confiable or not texto:
        # Degradar: la explicacion del LLM no paso la verificacion.
        return Explicacion(plantilla, "plantilla", verificar(plantilla, hechos))
    return Explicacion(texto, "bedrock", rep)
