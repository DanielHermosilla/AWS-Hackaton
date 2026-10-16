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
    "numeros, IDs ni rutas. Si un dato no esta, no lo menciones."
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
    return "\n".join(lineas)


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
