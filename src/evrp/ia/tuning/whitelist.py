"""Lista blanca de parámetros del solver y utilidades de validación/control.

La lista blanca es la ÚNICA superficie que el LLM (o el control aleatorio) puede
tocar. Cada entrada declara su dominio y dónde se aplica en la config:

- ruta "solver"  -> va a cfg["solver"][clave]
- ruta "escala"  -> va a cfg["solver"]["escala"][clave] (así lo lee ModeloCompacto)

Parámetros fijos por diseño (NO en la lista blanca): mip_rel_gap (gap_relativo),
threads (hilos), y cualquier dato/objetivo/tolerancia.

Nota de implementación: `mip_detect_symmetry` figura en la metodología de la idea,
pero la clase `ModeloCompacto` del motor base (no editable aquí) sólo consume
`mip_heuristic_effort` y `presolve` del bloque `escala`. Para no cambiar datos ni
tocar código ajeno, la lista blanca efectiva se limita a parámetros que el motor
ya aplica. La incorporación de `mip_detect_symmetry` queda como cambio solicitado.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    """Entrada de la lista blanca.

    nombre: clave expuesta al LLM.
    ruta: "solver" | "escala" (dónde se inyecta en la config).
    tipo: "categorico" | "entero" | "real".
    dominio: lista de categorías o (min, max) para numéricos.
    """

    nombre: str
    ruta: str
    tipo: str
    dominio: Any

    def valido(self, valor: Any) -> bool:
        if self.tipo == "categorico":
            return valor in self.dominio
        if valor is None:
            return False
        lo, hi = self.dominio
        if self.tipo == "entero":
            return isinstance(valor, int) and not isinstance(valor, bool) and lo <= valor <= hi
        # real
        return isinstance(valor, (int, float)) and not isinstance(valor, bool) and lo <= float(valor) <= hi

    def aleatorio(self, rng: random.Random) -> Any:
        if self.tipo == "categorico":
            return rng.choice(list(self.dominio))
        lo, hi = self.dominio
        if self.tipo == "entero":
            return rng.randint(lo, hi)
        return round(rng.uniform(lo, hi), 2)


# Lista blanca efectiva: parámetros que el motor base aplica sin cambios de código.
LISTA_BLANCA: dict[str, Param] = {
    p.nombre: p for p in [
        # Esfuerzo de heurísticas del MIP de HiGHS (0=desactiva, 1=máximo).
        Param("mip_heuristic_effort", "escala", "real", (0.0, 1.0)),
        # Presolve de HiGHS.
        Param("presolve", "escala", "categorico", ("on", "off", "choose")),
        # Poda de arcos cliente->cliente (0 = exacto/todos; >0 = k vecinos).
        Param("k_vecinos", "escala", "entero", (0, 20)),
        # Cargadores Pareto conservados por arco.
        Param("cargadores_por_arco", "solver", "entero", (1, 6)),
    ]
}


def validar_propuesta(propuesta: dict | None) -> dict:
    """Filtra una propuesta a sólo claves/valores válidos de la lista blanca.

    Descarta silenciosamente lo desconocido o fuera de dominio. Devuelve un dict
    plano {nombre: valor} saneado (nunca lanza por entradas inválidas).
    """
    salida: dict[str, Any] = {}
    for clave, valor in (propuesta or {}).items():
        p = LISTA_BLANCA.get(clave)
        if p is None:
            continue
        # Coerción suave de enteros expresados como float "entero" (p. ej. 3.0).
        if p.tipo == "entero" and isinstance(valor, float) and valor.is_integer():
            valor = int(valor)
        if p.valido(valor):
            salida[clave] = valor
    return salida


def aplicar_overrides(base_extra: dict, propuesta: dict) -> dict:
    """Inyecta una propuesta saneada en el dict de overrides de config.

    Respeta la ruta de cada parámetro (solver vs escala). No muta `base_extra`.
    """
    out = copy.deepcopy(base_extra)
    out.setdefault("solver", {})
    out["solver"].setdefault("escala", {})
    for clave, valor in validar_propuesta(propuesta).items():
        ruta = LISTA_BLANCA[clave].ruta
        if ruta == "solver":
            out["solver"][clave] = valor
        else:  # escala
            out["solver"]["escala"][clave] = valor
    return out


def muestra_aleatoria(rng: random.Random, claves: list[str] | None = None) -> dict:
    """Genera una propuesta aleatoria sobre la lista blanca (control)."""
    nombres = claves if claves is not None else list(LISTA_BLANCA)
    return {n: LISTA_BLANCA[n].aleatorio(rng) for n in nombres if n in LISTA_BLANCA}
