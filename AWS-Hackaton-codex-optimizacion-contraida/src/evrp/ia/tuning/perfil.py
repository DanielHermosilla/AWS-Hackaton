"""Perfil estructural compacto de un MILP de HiGHS (estilo LLM4MIP).

El perfil resume el modelo construido con cifras baratas de calcular desde el
objeto `highspy.Highs` (columnas, filas, no-ceros, binarias, densidad, rangos de
coeficientes) más el contexto de la instancia (clientes, vehículos) y, si se
dispone, el resultado de la corrida base (gap y tiempo). Es lo único que ve el
LLM: nunca recibe datos crudos ni el objetivo.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass
class PerfilMILP:
    columnas: int
    filas: int
    binarias: int
    enteras: int
    continuas: int
    no_ceros: int
    densidad: float            # no_ceros / (filas*columnas)
    coef_abs_min: float
    coef_abs_max: float
    rango_coef_log10: float    # log10(max/min) de |coef|
    clientes: int
    vehiculos: int
    cargadores_por_arco: int
    base_gap: float | None = None
    base_tiempo_s: float | None = None
    base_energia_kwh: float | None = None

    def a_dict(self) -> dict:
        return asdict(self)

    def compacto(self) -> str:
        """Representación de una línea para incrustar en el prompt."""
        g = "n/d" if self.base_gap is None else f"{self.base_gap:.4f}"
        t = "n/d" if self.base_tiempo_s is None else f"{self.base_tiempo_s:.1f}s"
        return (f"cols={self.columnas} filas={self.filas} binarias={self.binarias} "
                f"continuas={self.continuas} nnz={self.no_ceros} dens={self.densidad:.4f} "
                f"coef|min|={self.coef_abs_min:.3g} coef|max|={self.coef_abs_max:.3g} "
                f"rango_log10={self.rango_coef_log10:.2f} clientes={self.clientes} "
                f"vehiculos={self.vehiculos} carg/arco={self.cargadores_por_arco} "
                f"base_gap={g} base_tiempo={t}")


def perfil_desde_modelo(modelo, inst, cargadores_por_arco: int,
                        base_gap: float | None = None, base_tiempo_s: float | None = None,
                        base_energia_kwh: float | None = None) -> PerfilMILP:
    """Extrae el perfil de un `ModeloCompacto` ya construido.

    `modelo.h` es el objeto highspy.Highs. `inst` aporta clientes y vehículos.
    """
    h = modelo.h
    lp = h.getLp()
    ncol = int(h.getNumCol())
    nrow = int(h.getNumRow())
    nnz = int(h.getNumNz())

    integralidad = list(lp.integrality_)
    # highspy expone enteros/continuos; las binarias son enteras con [lb,ub]=[0,1].
    col_lo = list(lp.col_lower_)
    col_hi = list(lp.col_upper_)
    binarias = enteras = continuas = 0
    for k in range(ncol):
        es_entera = int(integralidad[k]) != 0 if k < len(integralidad) else False
        if es_entera:
            if col_lo[k] >= 0.0 and col_hi[k] <= 1.0:
                binarias += 1
            else:
                enteras += 1
        else:
            continuas += 1

    valores = [abs(v) for v in lp.a_matrix_.value_ if v != 0.0]
    coef_min = min(valores) if valores else 0.0
    coef_max = max(valores) if valores else 0.0
    rango = math.log10(coef_max / coef_min) if coef_min > 0 else 0.0
    densidad = nnz / (nrow * ncol) if nrow and ncol else 0.0

    return PerfilMILP(
        columnas=ncol, filas=nrow, binarias=binarias, enteras=enteras, continuas=continuas,
        no_ceros=nnz, densidad=round(densidad, 6),
        coef_abs_min=round(coef_min, 6), coef_abs_max=round(coef_max, 6),
        rango_coef_log10=round(rango, 4),
        clientes=len(inst.clientes),
        vehiculos=sum(dt.tipo.cantidad for dt in inst.tipos),
        cargadores_por_arco=int(cargadores_por_arco),
        base_gap=base_gap, base_tiempo_s=base_tiempo_s, base_energia_kwh=base_energia_kwh,
    )
