"""Verificador anti-alucinación.

Extrae del texto todos los **números** y los **IDs de nodo** (BASE, V1.., C1..) y
comprueba que cada uno exista en el conjunto de hechos citables del resultado, con
tolerancia de redondeo para los números. Lo que no case se reporta como error.

Diseño de la tolerancia:
- Un número del texto casa con un hecho si |texto − hecho| ≤ max(abs_tol, rel_tol·|hecho|).
- Además, para citas redondeadas ("11 kWh" por 11.22) se admite que el valor del texto
  sea el redondeo del hecho a los decimales que trae el texto (0, 1, 2 decimales).
- Enteros pequeños (0..~1000) que son conteos (entregas, recargas, nº de vehículos)
  se comparan de forma exacta tras la ronda.

El verificador es determinista y no usa red.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .hechos import Hecho

# IDs de nodo del dominio: BASE, V<entero>, C<entero>.
_RE_ID = re.compile(r"\b(BASE|[VC]\d{1,3})\b")
# Números: enteros o decimales, con signo opcional. Evita capturar los dígitos de un ID
# (V13) porque esos van pegados a una letra; usamos lookbehind de "no letra/dígito".
_RE_NUM = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")


@dataclass
class ResultadoVerificacion:
    """Resultado de verificar un texto contra los hechos."""

    ok: bool
    errores: list[str] = field(default_factory=list)
    numeros_texto: list[float] = field(default_factory=list)
    ids_texto: list[str] = field(default_factory=list)
    citados: list[Hecho] = field(default_factory=list)


def _parse_num(s: str) -> float:
    return float(s.replace(",", "."))


def _decimales(s: str) -> int:
    s = s.replace(",", ".")
    return len(s.split(".")[1]) if "." in s else 0


def _casa_numero(valor_texto: float, dec: int, valores_hecho: list[float],
                 abs_tol: float, rel_tol: float) -> bool:
    """¿`valor_texto` corresponde a algún hecho numérico (con redondeo/tolerancia)?"""
    for h in valores_hecho:
        # 1) Tolerancia absoluta/relativa directa.
        if abs(valor_texto - h) <= max(abs_tol, rel_tol * abs(h)):
            return True
        # 2) El texto es el redondeo del hecho a `dec` decimales.
        if round(h, dec) == valor_texto:
            return True
        # 3) El texto es el entero/floor del hecho (p. ej. "11 kWh" por 11.22).
        if dec == 0 and (int(h) == int(valor_texto) or round(h) == valor_texto):
            return True
    return False


def verificar_texto(
    texto: str,
    hechos: list[Hecho],
    *,
    abs_tol: float = 0.05,
    rel_tol: float = 0.01,
) -> ResultadoVerificacion:
    """Comprueba que todo número e ID del `texto` exista en `hechos`.

    `abs_tol`/`rel_tol` controlan el casado numérico. Devuelve un
    `ResultadoVerificacion` con `ok=False` y la lista de errores si algo no casa.
    """
    valores_hecho = [float(h.valor) for h in hechos
                     if isinstance(h.valor, (int, float)) and not isinstance(h.valor, bool)]
    ids_hecho = {str(h.valor) for h in hechos if isinstance(h.valor, str)}

    errores: list[str] = []
    nums_vistos: list[float] = []
    ids_vistos: list[str] = []
    citados: list[Hecho] = []

    # --- IDs ---
    for m in _RE_ID.finditer(texto):
        ident = m.group(1)
        ids_vistos.append(ident)
        if ident not in ids_hecho:
            errores.append(f"ID '{ident}' no aparece en el resultado (posible invención).")
        else:
            citados.append(Hecho("id", ident))

    for m in _RE_NUM.finditer(texto):
        bruto = m.group(0)
        try:
            val = _parse_num(bruto)
        except ValueError:
            continue
        nums_vistos.append(val)
        dec = _decimales(bruto)
        if _casa_numero(val, dec, valores_hecho, abs_tol, rel_tol):
            citados.append(Hecho("numero", val))
        else:
            errores.append(
                f"El número {bruto} no corresponde a ningún dato del resultado "
                f"(tolerancia abs={abs_tol}, rel={rel_tol})."
            )

    return ResultadoVerificacion(
        ok=not errores,
        errores=errores,
        numeros_texto=nums_vistos,
        ids_texto=ids_vistos,
        citados=citados,
    )


def hechos_citados_en(texto: str, hechos: list[Hecho],
                      **kw: Any) -> list[dict]:
    """Devuelve [{campo, valor}] de los hechos cuyo valor aparece en el texto.

    Útil para poblar `hechos_citados` del contrato: solo hechos efectivamente usados.
    """
    ver = verificar_texto(texto, hechos, **kw)
    nums = set(ver.numeros_texto)
    ids = set(ver.ids_texto)
    salida: list[dict] = []
    for h in hechos:
        if isinstance(h.valor, str) and h.valor in ids:
            salida.append(h.a_dict())
        elif isinstance(h.valor, (int, float)) and not isinstance(h.valor, bool):
            # ¿algún número del texto casa con este hecho?
            for n in nums:
                dec = len(str(n).split(".")[1]) if "." in str(n) else 0
                if _casa_numero(n, dec, [float(h.valor)], 0.05, 0.01):
                    salida.append(h.a_dict())
                    break
    # Deduplicar preservando orden.
    vistos = set()
    unicos = []
    for d in salida:
        clave = (d["campo"], str(d["valor"]))
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(d)
    return unicos
