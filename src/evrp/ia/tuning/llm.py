"""Proponedor de parámetros estilo LLM4MIP sobre Amazon Bedrock.

Dado un `PerfilMILP`, construye un prompt compacto y fuerza una tool con el
esquema de la lista blanca para obtener una propuesta JSON ya estructurada. La
propuesta se vuelve a validar con `whitelist.validar_propuesta` antes de usarse.

Mide latencia y tokens (los expone el `ClienteBedrock`) para que el llamador los
contabilice dentro del presupuesto total de tiempo.
"""
from __future__ import annotations

from dataclasses import dataclass

from .perfil import PerfilMILP
from .whitelist import LISTA_BLANCA, validar_propuesta

SISTEMA = (
    "Eres un experto en ajuste de solvers MILP (HiGHS) para un problema de ruteo "
    "de vehículos eléctricos (E-VRP). Recibes un perfil estructural del modelo ya "
    "construido y debes proponer parámetros del solver que REDUZCAN la energía final "
    "y/o el gap dentro de un presupuesto de tiempo fijo y un hilo. NO cambias datos, "
    "objetivo ni tolerancias (gap y threads son fijos). Elige valores razonables "
    "según la estructura: modelos densos o con muchas binarias suelen beneficiarse de "
    "presolve 'on' y mayor esfuerzo heurístico; podar arcos (k_vecinos>0) acelera "
    "instancias grandes a costa de posible subóptimo. Responde SÓLO con la tool."
)


def _tool_spec() -> dict:
    """Construye el toolSpec Bedrock a partir de la lista blanca."""
    props: dict = {}
    for nombre, p in LISTA_BLANCA.items():
        if p.tipo == "categorico":
            props[nombre] = {"type": "string", "enum": list(p.dominio),
                             "description": f"Parámetro {nombre} (categórico)."}
        elif p.tipo == "entero":
            lo, hi = p.dominio
            props[nombre] = {"type": "integer", "minimum": lo, "maximum": hi,
                             "description": f"Parámetro {nombre} entero en [{lo},{hi}]."}
        else:
            lo, hi = p.dominio
            props[nombre] = {"type": "number", "minimum": lo, "maximum": hi,
                             "description": f"Parámetro {nombre} real en [{lo},{hi}]."}
    return {
        "toolSpec": {
            "name": "proponer_parametros",
            "description": ("Propón parámetros del solver HiGHS de la lista blanca. "
                            "Incluye sólo los que quieras cambiar respecto a la base."),
            "inputSchema": {"json": {"type": "object", "properties": props}},
        }
    }


@dataclass
class PropuestaLLM:
    propuesta: dict
    propuesta_cruda: dict | None
    latencia_s: float
    tokens_in: int
    tokens_out: int
    modelo: str
    error: str | None = None

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out


def proponer(cliente, perfil: PerfilMILP, *, modelo: str | None = None,
             temperatura: float = 0.2, max_tokens: int = 512) -> PropuestaLLM:
    """Pide una propuesta de parámetros al LLM. Devuelve `PropuestaLLM`.

    Nunca lanza por una respuesta mala: si el modelo falla o no devuelve algo
    válido, `propuesta` queda vacía (equivale a usar la base) y `error` se llena.
    """
    texto = (
        "Perfil estructural del MILP (una línea):\n"
        f"{perfil.compacto()}\n\n"
        "Propón parámetros del solver de la lista blanca para mejorar energía/gap "
        "en el mismo presupuesto de tiempo. Incluye sólo lo que cambie."
    )
    herramienta = _tool_spec()
    try:
        args, resp = cliente.usar_herramienta(
            texto, herramienta, sistema=SISTEMA,
            modelo=modelo, temperatura=temperatura, max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - degradamos a propuesta vacía
        return PropuestaLLM({}, None, 0.0, 0, 0, modelo or getattr(cliente, "modelo", "?"),
                            error=str(exc)[:300])
    saneada = validar_propuesta(args)
    return PropuestaLLM(
        propuesta=saneada,
        propuesta_cruda=args,
        latencia_s=round(resp.latencia_s, 3),
        tokens_in=resp.tokens_entrada,
        tokens_out=resp.tokens_salida,
        modelo=modelo or getattr(cliente, "modelo", "?"),
    )
