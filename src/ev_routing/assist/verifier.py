"""Verificador anti-alucinacion para las explicaciones (eje C).

Contrasta el texto generado por el LLM contra los ``Hechos`` extraidos del
solver. No pretende validar gramatica: busca afirmaciones numericas o de
identidad (IDs de cliente/vehiculo) que NO aparezcan en los hechos, para
marcarlas. Una explicacion con afirmaciones no respaldadas se considera no
confiable y la capa superior puede descartarla o degradar a plantilla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .facts import Hechos


@dataclass
class ReporteVerificacion:
    confiable: bool
    afirmaciones_no_respaldadas: list[str] = field(default_factory=list)
    ids_desconocidos: list[str] = field(default_factory=list)


_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def _ids_conocidos(hechos: Hechos) -> set[str]:
    ids: set[str] = set(hechos.entregados) | set(hechos.sin_atender)
    for r in hechos.rutas:
        ids.add(r.vehiculo)
        ids.update(r.entregas)
        ids.update(r.paradas_carga)
    return ids


def verificar(texto: str, hechos: Hechos) -> ReporteVerificacion:
    """Marca IDs mencionados que no existen en los hechos del solver.

    Heuristica conservadora: solo seniala identificadores con forma de ID
    (alfanumericos con digito o guion) ausentes de los hechos. Los numeros
    sueltos no se penalizan por si solos (pueden ser kWh redondeados), pero se
    exponen para auditoria.
    """
    conocidos = _ids_conocidos(hechos)
    tokens = re.findall(r"[A-Za-z]+[\w\-]*\d[\w\-]*|\b[CV]\d+\b", texto)
    ids_desconocidos = [t for t in dict.fromkeys(tokens) if t not in conocidos]

    no_respaldadas: list[str] = []
    # Si el texto afirma que no hay clientes sin atender pero si los hay (o
    # viceversa), es una contradiccion directa con los hechos.
    menciona_todos = re.search(r"todos? (los )?(clientes|entregas)", texto, re.I)
    if menciona_todos and hechos.sin_atender:
        no_respaldadas.append(
            "Afirma atender a todos, pero hay clientes sin atender: "
            + ", ".join(hechos.sin_atender)
        )

    confiable = not no_respaldadas and not ids_desconocidos
    return ReporteVerificacion(
        confiable=confiable,
        afirmaciones_no_respaldadas=no_respaldadas,
        ids_desconocidos=ids_desconocidos,
    )
