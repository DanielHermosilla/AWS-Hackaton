"""Motor de ruteo E-VRP (hackatón AWS Breaking Barriers 2026, desafío CASE FCFM).

Etapa 1 (preprocesamiento): evrp.preparar(...) -> InstanciaPreparada
Etapa 2 (solver):           evrp.resolver_preparada(preparada, ...) -> Resultado
Atajo (1+2):                evrp.resolver(nodos_csv, ...) -> Resultado
"""
__version__ = "0.3.0"

from .api import Motor, MotorEvrp, Resultado, preparar, resolver, resolver_preparada  # noqa: E402,F401
from .preparacion import InstanciaPreparada  # noqa: E402,F401
